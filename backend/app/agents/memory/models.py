import time
from typing import Optional

from sqlmodel import Field, SQLModel


class AgentMemory(SQLModel, table=True):
    __tablename__ = "agent_memory_entries"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)
    conversation_id: Optional[str] = Field(default=None, index=True)
    agent: str = Field(default="planner", index=True)
    summary: str
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
