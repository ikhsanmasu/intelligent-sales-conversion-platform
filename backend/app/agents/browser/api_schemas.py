from pydantic import BaseModel


class BrowseRequest(BaseModel):
    query: str
    max_results: int | None = None
    max_pages: int | None = None


class BrowseSource(BaseModel):
    title: str | None = None
    url: str | None = None
    snippet: str | None = None
    content: str | None = None


class BrowseResponse(BaseModel):
    status: str
    summary: str
    sources: list[BrowseSource]
    count: int
