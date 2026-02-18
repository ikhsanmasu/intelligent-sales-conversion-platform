from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agents.timeseries.api_schemas import AnalyzeRequest, AnalyzeResponse
from app.agents.timeseries.service import analyze, analyze_stream

router = APIRouter(tags=["TimeSeries"], prefix="/v1/timeseries")


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_endpoint(request: AnalyzeRequest):
    return analyze(request=request)


@router.post("/analyze/stream")
async def analyze_stream_endpoint(request: AnalyzeRequest):
    return StreamingResponse(
        analyze_stream(request),
        media_type="text/event-stream",
    )
