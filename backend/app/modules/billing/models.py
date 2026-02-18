import time
from typing import Optional

from sqlmodel import Field, SQLModel


class LLMUsageEvent(SQLModel, table=True):
    __tablename__ = "llm_usage_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)
    conversation_id: str = Field(index=True)
    provider: str = Field(index=True)
    model: str = Field(index=True)

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    input_cost_usd: float = 0.0
    output_cost_usd: float = 0.0
    total_cost_usd: float = 0.0
    pricing_source: str = "provider_default"

    created_at: float = Field(default_factory=time.time, index=True)

