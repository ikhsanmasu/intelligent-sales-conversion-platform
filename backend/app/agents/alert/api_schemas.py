from typing import Any

from pydantic import BaseModel


class AlertRequest(BaseModel):
    question: str


class AlertResponse(BaseModel):
    status: str
    response: str
    alerts: list[dict[str, Any]]
