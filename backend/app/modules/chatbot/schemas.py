from typing import Any, Optional

from pydantic import BaseModel, Field


class HistoryMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[HistoryMessage] = Field(default_factory=list)
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    status: str
    response: str
    usage: dict

# ── Conversation schemas ──

class MessageSchema(BaseModel):
    role: str
    content: str
    thinking: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    created_at: Optional[float] = None


class ConversationSummary(BaseModel):
    id: str
    user_id: str
    title: str
    created_at: float
    updated_at: float


class ConversationDetail(BaseModel):
    id: str
    user_id: str
    title: str
    created_at: float
    updated_at: float
    messages: list[MessageSchema]


class CreateConversationRequest(BaseModel):
    title: str = "New Chat"


class UpdateConversationTitleRequest(BaseModel):
    title: str


class SaveMessagesRequest(BaseModel):
    user_message: str
    assistant_content: str
    assistant_thinking: Optional[str] = None
    assistant_metadata: dict[str, Any] | None = None


class HistoryEntry(BaseModel):
    id: int
    user_id: str
    conversation_id: str
    user_message: str
    assistant_content: str
    assistant_thinking: Optional[str] = None
    created_at: float


class MonitorConversationSummary(BaseModel):
    id: str
    user_id: str
    channel: str
    external_user_id: str
    title: str
    created_at: float
    updated_at: float
    message_count: int
    lead_status: str
    summary: str
    last_user_message: str = ""
    last_assistant_message: str = ""


class MonitorConversationDetail(BaseModel):
    id: str
    user_id: str
    channel: str
    external_user_id: str
    title: str
    created_at: float
    updated_at: float
    message_count: int
    lead_status: str
    summary: str
    last_user_message: str = ""
    last_assistant_message: str = ""
    messages: list[MessageSchema] = Field(default_factory=list)
