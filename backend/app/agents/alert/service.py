import json
from collections.abc import Generator

from app.agents.alert import create_alert_agent
from app.agents.alert.api_schemas import AlertRequest, AlertResponse


def check_alerts(request: AlertRequest) -> AlertResponse:
    agent = create_alert_agent()
    result = agent.execute(request.question)

    return AlertResponse(
        status="error" if result.metadata.get("error") else "success",
        response=result.output,
        alerts=result.metadata.get("checks") or [],
    )


def check_alerts_stream(request: AlertRequest) -> Generator[str, None, None]:
    agent = create_alert_agent()

    for event in agent.execute_stream(request.question):
        if event.get("type") == "_result":
            continue
        yield f"data: {json.dumps(event)}\n\n"

    yield f"data: {json.dumps({'type': 'done'})}\n\n"
