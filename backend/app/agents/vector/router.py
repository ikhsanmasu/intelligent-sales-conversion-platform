from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agents.vector.api_schemas import VectorSearchRequest, VectorSearchResponse
from app.agents.vector.service import search, search_stream

router = APIRouter(tags=["Vector"], prefix="/v1/vector")


@router.post("/search", response_model=VectorSearchResponse)
async def search_endpoint(request: VectorSearchRequest):
    return search(request=request)


@router.post("/search/stream")
async def search_stream_endpoint(request: VectorSearchRequest):
    return StreamingResponse(
        search_stream(request),
        media_type="text/event-stream",
    )
