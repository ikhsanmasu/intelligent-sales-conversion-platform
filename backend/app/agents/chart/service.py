import json
from collections.abc import Generator

from app.agents.chart import create_chart_agent
from app.agents.chart.api_schemas import ChartRequest, ChartResponse


def _parse_chart_output(raw: str) -> tuple[dict | None, str | None]:
    raw = (raw or "").strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None, "Invalid chart payload."
    if isinstance(payload, dict) and payload.get("error"):
        return None, str(payload.get("error"))
    if isinstance(payload, dict) and (payload.get("chart") or payload.get("type")):
        return payload.get("chart") or payload, None
    return None, "Chart payload missing."


def generate_chart(request: ChartRequest) -> ChartResponse:
    agent = create_chart_agent()
    result = agent.execute(request.query)
    chart, error = _parse_chart_output(result.output)
    status = "success" if chart and not error else "error"
    return ChartResponse(status=status, chart=chart, error=error)


def generate_chart_stream(request: ChartRequest) -> Generator[str, None, None]:
    agent = create_chart_agent()
    chart_result = None
    for event in agent.execute_stream(request.query):
        if event.get("type") == "_result":
            chart_result = event["data"]
        else:
            yield f"data: {json.dumps(event)}\n\n"

    if chart_result is None:
        yield f"data: {json.dumps({'type': 'content', 'content': 'Error: Chart agent returned no result.'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    yield f"data: {json.dumps({'type': 'content', 'content': chart_result.output})}\n\n"
    yield f"data: {json.dumps({'type': 'done'})}\n\n"
