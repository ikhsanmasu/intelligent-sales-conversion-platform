from app.agents.alert.agent import AlertAgent
from app.agents.database import DatabaseAgent, create_database_agent
from app.core.llm import create_llm
from app.core.llm.base import BaseLLM


def create_alert_agent(
    llm: BaseLLM | None = None,
    database_agent: DatabaseAgent | None = None,
) -> AlertAgent:
    alert_llm = llm or create_llm(config_group="llm_alert")
    alert_db_agent = database_agent or create_database_agent()
    return AlertAgent(llm=alert_llm, database_agent=alert_db_agent)


__all__ = ["AlertAgent", "create_alert_agent"]
