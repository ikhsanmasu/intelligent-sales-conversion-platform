from app.agents.planner.agent import PlannerAgent
from app.core.llm import create_llm
from app.core.llm.base import BaseLLM


def create_planner_agent(
    llm: BaseLLM | None = None,
) -> PlannerAgent:
    planner_llm = llm or create_llm(config_group="llm_planner")
    return PlannerAgent(
        llm=planner_llm,
    )


__all__ = ["PlannerAgent", "create_planner_agent"]
