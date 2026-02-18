from app.agents.alert import AlertAgent, create_alert_agent
from app.agents.browser import BrowserAgent, create_browser_agent
from app.agents.chart import ChartAgent, create_chart_agent
from app.agents.compare import CompareAgent, create_compare_agent
from app.agents.database import DatabaseAgent, create_database_agent
from app.agents.report import ReportAgent, create_report_agent
from app.agents.timeseries import TimeSeriesAgent, create_timeseries_agent
from app.agents.vector import VectorAgent, create_vector_agent
from app.agents.planner.agent import PlannerAgent
from app.core.llm import create_llm
from app.core.llm.base import BaseLLM


def create_planner_agent(
    llm: BaseLLM | None = None,
    database_agent: DatabaseAgent | None = None,
    vector_agent: VectorAgent | None = None,
    browser_agent: BrowserAgent | None = None,
    chart_agent: ChartAgent | None = None,
    report_agent: ReportAgent | None = None,
    timeseries_agent: TimeSeriesAgent | None = None,
    compare_agent: CompareAgent | None = None,
    alert_agent: AlertAgent | None = None,
) -> PlannerAgent:
    planner_llm = llm or create_llm(config_group="llm_planner")
    planner_database_agent = database_agent or create_database_agent()
    planner_vector_agent = vector_agent or create_vector_agent()
    planner_browser_agent = browser_agent or create_browser_agent()
    planner_chart_agent = chart_agent or create_chart_agent()
    planner_report_agent = report_agent or create_report_agent()
    planner_timeseries_agent = timeseries_agent or create_timeseries_agent()
    planner_compare_agent = compare_agent or create_compare_agent()
    planner_alert_agent = alert_agent or create_alert_agent()
    return PlannerAgent(
        llm=planner_llm,
        database_agent=planner_database_agent,
        vector_agent=planner_vector_agent,
        browser_agent=planner_browser_agent,
        chart_agent=planner_chart_agent,
        report_agent=planner_report_agent,
        timeseries_agent=planner_timeseries_agent,
        compare_agent=planner_compare_agent,
        alert_agent=planner_alert_agent,
    )


__all__ = ["PlannerAgent", "create_planner_agent"]
