from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agents.browser.api_schemas import BrowseRequest, BrowseResponse
from app.agents.browser.service import browse, browse_stream

router = APIRouter(tags=["Browser"], prefix="/v1/browser")


@router.post("/browse", response_model=BrowseResponse)
async def browse_endpoint(request: BrowseRequest):
    return browse(request=request)


@router.post("/browse/stream")
async def browse_stream_endpoint(request: BrowseRequest):
    return StreamingResponse(
        browse_stream(request),
        media_type="text/event-stream",
    )
