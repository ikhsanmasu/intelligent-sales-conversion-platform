from app.agents.compare.agent import CompareAgent
from app.agents.database import DatabaseAgent, create_database_agent
from app.core.llm import create_llm
from app.core.llm.base import BaseLLM


def create_compare_agent(
    llm: BaseLLM | None = None,
    database_agent: DatabaseAgent | None = None,
) -> CompareAgent:
    cmp_llm = llm or create_llm(config_group="llm_compare")
    cmp_db_agent = database_agent or create_database_agent()
    return CompareAgent(llm=cmp_llm, database_agent=cmp_db_agent)


__all__ = ["CompareAgent", "create_compare_agent"]
