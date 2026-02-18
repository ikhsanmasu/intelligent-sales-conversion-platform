from app.agents.database.agent import DatabaseAgent


def create_database_agent() -> DatabaseAgent:
    return DatabaseAgent()


__all__ = ["DatabaseAgent", "create_database_agent"]
