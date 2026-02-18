import json
from collections.abc import Generator

from app.agents.vector import create_vector_agent
from app.agents.vector.api_schemas import VectorSearchRequest, VectorSearchResponse


def search(request: VectorSearchRequest) -> VectorSearchResponse:
    agent = create_vector_agent()
    result = agent.execute(request.question, context={"top_k": request.top_k})

    return VectorSearchResponse(
        status="success" if not result.metadata.get("error") else "error",
        response=result.output,
        count=int(result.metadata.get("count") or 0),
        matches=list(result.metadata.get("matches") or []),
    )


def search_stream(request: VectorSearchRequest) -> Generator[str, None, None]:
    agent = create_vector_agent()

    final_result = None
    for event in agent.execute_stream(request.question, context={"top_k": request.top_k}):
        if event.get("type") == "_result":
            final_result = event.get("data")
            continue
        yield f"data: {json.dumps(event)}\n\n"

    if final_result is None:
        yield f"data: {json.dumps({'type': 'content', 'content': 'Error: vector agent gagal merespons.'})}\n\n"
    else:
        yield f"data: {json.dumps({'type': 'content', 'content': final_result.output})}\n\n"
        yield (
            "data: "
            + json.dumps(
                {
                    "type": "meta",
                    "metadata": {
                        "count": final_result.metadata.get("count"),
                        "top_k": final_result.metadata.get("top_k"),
                        "source": final_result.metadata.get("source"),
                    },
                }
            )
            + "\n\n"
        )

    yield f"data: {json.dumps({'type': 'done'})}\n\n"
