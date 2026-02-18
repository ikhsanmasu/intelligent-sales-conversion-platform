from app.agents.database.agent import DatabaseAgent
from app.core.llm import create_llm
from app.core.llm.base import BaseLLM


def create_database_agent(llm: BaseLLM | None = None) -> DatabaseAgent:
    return DatabaseAgent(llm=llm or create_llm(config_group="llm_database"))


__all__ = ["DatabaseAgent", "create_database_agent"]
