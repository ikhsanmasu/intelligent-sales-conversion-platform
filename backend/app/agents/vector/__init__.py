from app.agents.vector.agent import VectorAgent
from app.core.llm import create_llm
from app.core.llm.base import BaseLLM


def create_vector_agent(llm: BaseLLM | None = None) -> VectorAgent:
    return VectorAgent(llm=llm or create_llm(config_group="llm_planner"))


__all__ = ["VectorAgent", "create_vector_agent"]
