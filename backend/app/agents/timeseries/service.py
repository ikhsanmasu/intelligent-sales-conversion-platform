import json
from collections.abc import Generator

from app.agents.timeseries import create_timeseries_agent
from app.agents.timeseries.api_schemas import AnalyzeRequest, AnalyzeResponse


def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    agent = create_timeseries_agent()
    result = agent.execute(request.question)

    return AnalyzeResponse(
        status="error" if result.metadata.get("error") else "success",
        response=result.output,
        code=result.metadata.get("code", ""),
        computation_result=result.metadata.get("computation_result") or {},
    )


def analyze_stream(request: AnalyzeRequest) -> Generator[str, None, None]:
    agent = create_timeseries_agent()

    for event in agent.execute_stream(request.question):
        if event.get("type") == "_result":
            continue  # internal marker, don't send to client
        yield f"data: {json.dumps(event)}\n\n"

    yield f"data: {json.dumps({'type': 'done'})}\n\n"
