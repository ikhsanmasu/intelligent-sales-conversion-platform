from typing import Optional

from pydantic import BaseModel, Field


class MemoryMessage(BaseModel):
    role: str
    content: str


class MemoryRequest(BaseModel):
    action: str = Field(default="get")
    user_id: str
    conversation_id: Optional[str] = None
    agent: str = Field(default="planner")
    messages: list[MemoryMessage] = Field(default_factory=list)


class MemoryResponse(BaseModel):
    status: str
    summary: str
    count: int = 0
