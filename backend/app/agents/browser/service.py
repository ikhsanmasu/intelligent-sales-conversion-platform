import json
from collections.abc import Generator

from app.agents.browser import create_browser_agent
from app.agents.browser.api_schemas import BrowseRequest, BrowseResponse, BrowseSource


def _build_context(request: BrowseRequest) -> dict:
    context: dict = {}
    if request.max_results:
        context["max_results"] = request.max_results
    if request.max_pages:
        context["max_pages"] = request.max_pages
    return context


def browse(request: BrowseRequest) -> BrowseResponse:
    agent = create_browser_agent()
    context = _build_context(request)
    result = agent.execute(request.query, context=context)

    sources = result.metadata.get("sources", []) or []
    return BrowseResponse(
        status="success",
        summary=result.output,
        sources=[BrowseSource(**source) for source in sources],
        count=result.metadata.get("count", len(sources)),
    )


def browse_stream(request: BrowseRequest) -> Generator[str, None, None]:
    agent = create_browser_agent()
    context = _build_context(request)

    browser_result = None
    for event in agent.execute_stream(request.query, context=context):
        if event.get("type") == "_result":
            browser_result = event["data"]
        else:
            yield f"data: {json.dumps(event)}\n\n"

    if browser_result is None:
        yield (
            "data: "
            + json.dumps({"type": "content", "content": "Error: Browser agent returned no result."})
            + "\n\n"
        )
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    yield f"data: {json.dumps({'type': 'content', 'content': browser_result.output})}\n\n"
    yield f"data: {json.dumps({'type': 'done'})}\n\n"
