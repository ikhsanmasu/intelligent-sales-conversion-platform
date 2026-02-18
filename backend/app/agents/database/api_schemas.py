from pydantic import BaseModel


class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    status: str
    response: str
    sql: str
    row_count: int
