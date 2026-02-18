from pydantic import BaseModel
from pydantic import Field


class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    status: str
    response: str
    sql: str = ""
    row_count: int
    intent: str = ""
    rows: list[dict] = Field(default_factory=list)
