from app.agents.chart.agent import ChartAgent
from app.agents.database import DatabaseAgent, create_database_agent
from app.core.llm import create_llm
from app.core.llm.base import BaseLLM


def create_chart_agent(
    llm: BaseLLM | None = None,
    database_agent: DatabaseAgent | None = None,
) -> ChartAgent:
    chart_llm = llm or create_llm(config_group="llm_chart")
    chart_db_agent = database_agent or create_database_agent()
    return ChartAgent(llm=chart_llm, database_agent=chart_db_agent)


__all__ = ["ChartAgent", "create_chart_agent"]
