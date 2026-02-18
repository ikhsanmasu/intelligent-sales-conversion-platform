from app.agents.memory.agent import MemoryAgent
from app.core.llm import create_llm
from app.core.llm.base import BaseLLM


def create_memory_agent(llm: BaseLLM | None = None) -> MemoryAgent:
    return MemoryAgent(llm=llm or create_llm(config_group="llm_memory"))


__all__ = ["MemoryAgent", "create_memory_agent"]
