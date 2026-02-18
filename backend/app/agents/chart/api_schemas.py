from pydantic import BaseModel


class ChartRequest(BaseModel):
    query: str


class ChartResponse(BaseModel):
    status: str
    chart: dict | None = None
    error: str | None = None
