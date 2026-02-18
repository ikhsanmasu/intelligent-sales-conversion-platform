from app.agents.database import DatabaseAgent, create_database_agent
from app.agents.report.agent import ReportAgent
from app.core.llm import create_llm
from app.core.llm.base import BaseLLM


def create_report_agent(
    llm: BaseLLM | None = None,
    database_agent: DatabaseAgent | None = None,
) -> ReportAgent:
    report_llm = llm or create_llm(config_group="llm_report")
    report_db_agent = database_agent or create_database_agent()
    return ReportAgent(llm=report_llm, database_agent=report_db_agent)


__all__ = ["ReportAgent", "create_report_agent"]
