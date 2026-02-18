from app.agents.vector.agent import VectorAgent


def create_vector_agent() -> VectorAgent:
    return VectorAgent()


__all__ = ["VectorAgent", "create_vector_agent"]
