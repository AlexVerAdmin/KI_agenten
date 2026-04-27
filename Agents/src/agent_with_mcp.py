import asyncio
import os
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.ui import Console
from autogen_ext.models.openai import OpenAIChatCompletionClient
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from Agents.src.memory import new_session, save_message, save_session_summary, get_recent_history

# Настройки
MODEL_URL = "http://127.0.0.1:8000/v1"
VENV_PATH = "/home/alex/Документи/ICH/SysVSC/Agents/venv/bin/"

async def main():
    # --- Память: создаём новую сессию ---
    session_id = new_session()
    history_context = get_recent_history(n_sessions=3)
    print(f"--- Сессия {session_id[:8]} ---")
    print(history_context)

    # 1. Настройка MCP клиента для NotebookLM
    # Мы запускаем сервер через stdio
    server_params = StdioServerParameters(
        command=os.path.join(VENV_PATH, "notebooklm-mcp"),
        args=[],
        env=os.environ.copy()
    )

    print("--- Подключение к NotebookLM MCP ---")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # Получаем список доступных инструментов от NotebookLM
            tools_list = await session.list_tools()
            print(f"Доступные инструменты MCP: {[t.name for t in tools_list.tools]}")

            # Обертка для вызова MCP инструмента внутри AutoGen
            async def ask_notebooklm(query: str) -> str:
                print(f"  [MCP] Запрос к NotebookLM: {query}")
                result = await session.call_tool("ask", arguments={"query": query})
                return str(result.content[0].text if result.content else "Нет ответа")

            # 2. Настройка клиента Gemma 4
            model_client = OpenAIChatCompletionClient(
                model="gemma-4",
                base_url=MODEL_URL,
                api_key="none",
                model_info={
                    "vision": False,
                    "function_calling": True,
                    "json_output": True,
                    "family": "unknown"
                }
            )

            # 3. Создаем агента с доступом к NotebookLM и историей сессий
            agent = AssistantAgent(
                name="GemmaKnowledgeDispatcher",
                model_client=model_client,
                tools=[ask_notebooklm],
                system_message=(
                    "Ты - интеллектуальный диспетчер системы Agents. "
                    "У тебя есть доступ к базе знаний Obsidian через инструмент 'ask_notebooklm'. "
                    "Если тебя спрашивают о планах, архитектуре или деталях проекта, "
                    "ОБЯЗАТЕЛЬНО используй этот инструмент перед ответом.\n\n"
                    f"{history_context}"
                )
            )

            print("--- Система готова. Ожидание вопроса... ---")

            task = "Какие ключевые архитектурные решения приняты в проекте Agents согласно Obsidian?"

            # --- Память: сохраняем вопрос ---
            save_message(session_id, "user", "user", task)

            result = await agent.run(task=task)

            # --- Память: сохраняем ответ и резюме сессии ---
            final_answer = result.messages[-1].content if result.messages else ""
            save_message(session_id, "GemmaKnowledgeDispatcher", "assistant", final_answer)
            save_session_summary(session_id, final_answer[:300])

            print("\n--- Ответ агента ---")
            print(final_answer)

if __name__ == "__main__":
    # Убедитесь, что сервер llama-cpp запущен (python/src/model_manager.py)
    asyncio.run(main())
