import json
from collections.abc import Generator

from app.agents.compare import create_compare_agent
from app.agents.compare.api_schemas import CompareRequest, CompareResponse


def compare(request: CompareRequest) -> CompareResponse:
    agent = create_compare_agent()
    result = agent.execute(request.question)

    return CompareResponse(
        status="error" if result.metadata.get("error") else "success",
        response=result.output,
        code=result.metadata.get("code", ""),
        computation_result=result.metadata.get("computation_result") or {},
    )


def compare_stream(request: CompareRequest) -> Generator[str, None, None]:
    agent = create_compare_agent()

    for event in agent.execute_stream(request.question):
        if event.get("type") == "_result":
            continue
        yield f"data: {json.dumps(event)}\n\n"

    yield f"data: {json.dumps({'type': 'done'})}\n\n"
