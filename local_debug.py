import os
import sys
from langchain_community.llms import Ollama
from core.orchestrator_v2 import node_handler, tool_node
from langchain_core.messages import HumanMessage
import sqlite3

# Настраиваем модель для локального теста
os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"

def test_local_agent():
    print("--- ЗАПУСК ЛОКАЛЬНОЙ ОТЛАДКИ (Local Admin) ---")
    user_id = 12345
    agent_type = "local_admin"  # Тестируем на локальном
    
    # 1. Запрос от пользователя
    user_input = "Покажи параметры моей видеокарты P4000"
    print(f"\n[USER]: {user_input}")
    
    # Имитируем работу оркестратора (шаг 1: Агент должен спросить разрешение)
    state = {
        "messages": [HumanMessage(content=user_input)],
        "user_id": user_id,
        "agent_type": agent_type
    }
    
    # Прямой вызов обработчика (без сети, без UI)
    result = node_handler(state)
    ai_msg = result['messages'][-1]
    
    print(f"\n[AI]: {ai_msg.content}")
    if hasattr(ai_msg, 'tool_calls') and ai_msg.tool_calls:
        print(f"DEBUG: Обнаружен вызов инструмента: {ai_msg.tool_calls}")

if __name__ == "__main__":
    test_local_agent()
