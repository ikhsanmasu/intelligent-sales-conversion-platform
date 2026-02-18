from typing import Any

from pydantic import BaseModel


class CompareRequest(BaseModel):
    question: str


class CompareResponse(BaseModel):
    status: str
    response: str
    code: str
    computation_result: dict[str, Any]
