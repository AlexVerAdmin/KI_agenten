"""
Агент: Карьерный коуч.
Регистрируется в router через @register("career").
Помогает с поиском работы, подготовкой к интервью, развитием карьеры.
Отвечает на русском языке.
"""

import logging
from src.llm import chat_completion

from src.gateway.router import register
from src.db.conversations import get_history_text
from src.config import get_effective_settings
from src.agents.base_agent import AgentWithObsidian

logger = logging.getLogger(__name__)

AGENT_NAME = "career"

class CareerAgent(AgentWithObsidian):
    agent_name = "career"
    memory_files = {
        "profile": "agents/career/profile.md",
        "job_search_log": "agents/career/job_search_log.md",
    }

_career_agent = CareerAgent()


@register("career")
async def process(user_input: str, voice_path: str = None, user_id: str = "alex", **kwargs) -> dict:
    cfg = get_effective_settings(AGENT_NAME, user_id)
    model_key = cfg["model"]
    system_prompt = cfg.get("system_prompt", "")
    temperature   = float(cfg.get("temperature", 0.7))
    max_tokens    = int(cfg.get("max_tokens", 8192))

    history_text = get_history_text(AGENT_NAME, limit=20)

    # Load context from Obsidian
    _career_agent._load_memory()
    obsidian_context = _career_agent.get_context_for_prompt()

    full_system_prompt = system_prompt
    if obsidian_context:
        full_system_prompt += f"\n\nКонтекст из Obsidian:\n{obsidian_context}"

    messages = [{"role": "system", "content": full_system_prompt}]

    if history_text:
        messages.append({
            "role": "system",
            "content": f"История разговора:\n{history_text}",
        })

    messages.append({"role": "user", "content": user_input})

    response = await chat_completion(
        model=model_key,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    text = (response.choices[0].message.content or "").strip()
    return {"text": text, "audio_path": None}
