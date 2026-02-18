from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agents.chart.api_schemas import ChartRequest, ChartResponse
from app.agents.chart.service import generate_chart, generate_chart_stream

router = APIRouter(tags=["Chart"], prefix="/v1/chart")


@router.post("/generate", response_model=ChartResponse)
async def generate_chart_endpoint(request: ChartRequest):
    return generate_chart(request=request)


@router.post("/generate/stream")
async def generate_chart_stream_endpoint(request: ChartRequest):
    return StreamingResponse(
        generate_chart_stream(request),
        media_type="text/event-stream",
    )
