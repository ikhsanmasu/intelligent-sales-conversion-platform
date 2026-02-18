from pydantic import BaseModel, Field


class VectorSearchRequest(BaseModel):
    question: str
    top_k: int = 3


class VectorSearchResponse(BaseModel):
    status: str
    response: str
    count: int
    matches: list[dict] = Field(default_factory=list)
