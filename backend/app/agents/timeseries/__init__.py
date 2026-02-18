from app.agents.timeseries.agent import TimeSeriesAgent
from app.agents.database import DatabaseAgent, create_database_agent
from app.core.llm import create_llm
from app.core.llm.base import BaseLLM


def create_timeseries_agent(
    llm: BaseLLM | None = None,
    database_agent: DatabaseAgent | None = None,
) -> TimeSeriesAgent:
    ts_llm = llm or create_llm(config_group="llm_timeseries")
    ts_db_agent = database_agent or create_database_agent()
    return TimeSeriesAgent(llm=ts_llm, database_agent=ts_db_agent)


__all__ = ["TimeSeriesAgent", "create_timeseries_agent"]
