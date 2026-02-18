import time
from typing import Optional

from sqlmodel import Session, select, delete

from app.core.database import app_engine
from app.agents.memory.models import AgentMemory


def get_memory_summary(
    user_id: str,
    agent: str = "planner",
    conversation_id: Optional[str] = None,
) -> Optional[str]:
    with Session(app_engine) as session:
        query = (
            select(AgentMemory)
            .where(AgentMemory.user_id == user_id)
            .where(AgentMemory.agent == agent)
            .order_by(AgentMemory.updated_at.desc(), AgentMemory.id.desc())
        )
        if conversation_id:
            query = query.where(AgentMemory.conversation_id == conversation_id)
        memory = session.exec(query).first()
        return memory.summary if memory else None


def upsert_memory_summary(
    user_id: str,
    summary: str,
    agent: str = "planner",
    conversation_id: Optional[str] = None,
) -> AgentMemory:
    now = time.time()
    with Session(app_engine) as session:
        query = (
            select(AgentMemory)
            .where(AgentMemory.user_id == user_id)
            .where(AgentMemory.agent == agent)
        )
        if conversation_id:
            query = query.where(AgentMemory.conversation_id == conversation_id)

        memory = session.exec(query).first()
        if memory:
            memory.summary = summary
            memory.updated_at = now
        else:
            memory = AgentMemory(
                user_id=user_id,
                conversation_id=conversation_id,
                agent=agent,
                summary=summary,
                created_at=now,
                updated_at=now,
            )
        session.add(memory)
        session.commit()
        session.refresh(memory)
        return memory


def clear_memory(
    user_id: str,
    agent: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> int:
    with Session(app_engine) as session:
        query = delete(AgentMemory).where(AgentMemory.user_id == user_id)
        if agent:
            query = query.where(AgentMemory.agent == agent)
        if conversation_id:
            query = query.where(AgentMemory.conversation_id == conversation_id)
        result = session.exec(query)
        session.commit()
        return result.rowcount or 0
