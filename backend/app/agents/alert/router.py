from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agents.alert.api_schemas import AlertRequest, AlertResponse
from app.agents.alert.service import check_alerts, check_alerts_stream

router = APIRouter(tags=["Alert"], prefix="/v1/alert")


@router.post("/check", response_model=AlertResponse)
async def alert_check_endpoint(request: AlertRequest):
    return check_alerts(request=request)


@router.post("/check/stream")
async def alert_check_stream_endpoint(request: AlertRequest):
    return StreamingResponse(
        check_alerts_stream(request),
        media_type="text/event-stream",
    )
