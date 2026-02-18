from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agents.memory.api_schemas import MemoryRequest, MemoryResponse
from app.agents.memory.service import execute_memory, execute_memory_stream

router = APIRouter(tags=["Memory"], prefix="/v1/memory")


@router.post("/execute", response_model=MemoryResponse)
async def execute_memory_endpoint(request: MemoryRequest):
    return execute_memory(request=request)


@router.post("/execute/stream")
async def execute_memory_stream_endpoint(request: MemoryRequest):
    return StreamingResponse(
        execute_memory_stream(request),
        media_type="text/event-stream",
    )
