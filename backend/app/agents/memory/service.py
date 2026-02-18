import json
from collections.abc import Generator

from app.agents.memory import create_memory_agent
from app.agents.memory.api_schemas import MemoryRequest, MemoryResponse


def execute_memory(request: MemoryRequest) -> MemoryResponse:
    agent = create_memory_agent()
    payload = {
        "action": request.action,
        "user_id": request.user_id,
        "conversation_id": request.conversation_id,
        "agent": request.agent,
        "messages": [m.model_dump() for m in request.messages],
    }
    result = agent.execute(json.dumps(payload, ensure_ascii=True))
    summary = result.output
    count = result.metadata.get("count", 0)
    status = "success" if not result.metadata.get("error") else "error"
    return MemoryResponse(status=status, summary=summary, count=count)


def execute_memory_stream(request: MemoryRequest) -> Generator[str, None, None]:
    agent = create_memory_agent()
    payload = {
        "action": request.action,
        "user_id": request.user_id,
        "conversation_id": request.conversation_id,
        "agent": request.agent,
        "messages": [m.model_dump() for m in request.messages],
    }
    memory_result = None
    for event in agent.execute_stream(json.dumps(payload, ensure_ascii=True)):
        if event.get("type") == "_result":
            memory_result = event["data"]
        else:
            yield f"data: {json.dumps(event)}\n\n"

    if memory_result is None:
        yield f"data: {json.dumps({'type': 'content', 'content': 'Error: Memory agent returned no result.'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    yield f"data: {json.dumps({'type': 'content', 'content': memory_result.output})}\n\n"
    yield f"data: {json.dumps({'type': 'done'})}\n\n"
