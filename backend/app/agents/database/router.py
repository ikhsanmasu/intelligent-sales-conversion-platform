from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agents.database.api_schemas import QueryRequest, QueryResponse
from app.agents.database.service import query, query_stream

router = APIRouter(tags=["Database"], prefix="/v1/database")


@router.post("/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest):
    return query(request=request)


@router.post("/query/stream")
async def query_stream_endpoint(request: QueryRequest):
    return StreamingResponse(
        query_stream(request),
        media_type="text/event-stream",
    )
