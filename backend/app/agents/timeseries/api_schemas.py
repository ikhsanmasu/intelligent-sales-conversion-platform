from typing import Any

from pydantic import BaseModel


class AnalyzeRequest(BaseModel):
    question: str


class AnalyzeResponse(BaseModel):
    status: str
    response: str
    code: str
    computation_result: dict[str, Any]
