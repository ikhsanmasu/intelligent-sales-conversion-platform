from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agents.compare.api_schemas import CompareRequest, CompareResponse
from app.agents.compare.service import compare, compare_stream

router = APIRouter(tags=["Compare"], prefix="/v1/compare")


@router.post("/analyze", response_model=CompareResponse)
async def compare_endpoint(request: CompareRequest):
    return compare(request=request)


@router.post("/analyze/stream")
async def compare_stream_endpoint(request: CompareRequest):
    return StreamingResponse(
        compare_stream(request),
        media_type="text/event-stream",
    )
