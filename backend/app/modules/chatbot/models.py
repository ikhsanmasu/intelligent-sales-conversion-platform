import time
import uuid
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel


class Conversation(SQLModel, table=True):
    __tablename__ = "chat_conversations"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: str = Field(index=True)
    title: str = Field(default="New Chat")
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    messages: list["ConversationMessage"] = Relationship(
        back_populates="conversation",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class ConversationMessage(SQLModel, table=True):
    __tablename__ = "chat_messages"

    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: str = Field(foreign_key="chat_conversations.id", index=True)
    role: str
    content: str
    thinking: Optional[str] = None
    llm_metadata: Optional[str] = None  # JSON-encoded assistant metadata (tokens, cost, model)
    created_at: float = Field(default_factory=time.time)

    conversation: Optional[Conversation] = Relationship(back_populates="messages")


class ConversationHistory(SQLModel, table=True):
    __tablename__ = "chat_history_entries"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)
    conversation_id: str = Field(foreign_key="chat_conversations.id", index=True)
    user_message: str
    assistant_content: str
    assistant_thinking: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
