import json
from collections.abc import Generator

from app.agents.database import create_database_agent
from app.agents.database.api_schemas import QueryRequest, QueryResponse


def query(request: QueryRequest) -> QueryResponse:
    agent = create_database_agent()
    result = agent.execute(request.question)

    return QueryResponse(
        status="success" if not result.metadata.get("error") else "error",
        response=result.output,
        sql="N/A",
        row_count=int(result.metadata.get("row_count") or 0),
        intent=str(result.metadata.get("intent") or ""),
        rows=list(result.metadata.get("rows") or []),
    )


def query_stream(request: QueryRequest) -> Generator[str, None, None]:
    agent = create_database_agent()

    final_result = None
    for event in agent.execute_stream(request.question):
        if event.get("type") == "_result":
            final_result = event.get("data")
            continue
        yield f"data: {json.dumps(event)}\n\n"

    if final_result is None:
        yield f"data: {json.dumps({'type': 'content', 'content': 'Error: database agent gagal merespons.'})}\n\n"
    else:
        yield f"data: {json.dumps({'type': 'content', 'content': final_result.output})}\n\n"
        yield (
            "data: "
            + json.dumps(
                {
                    "type": "meta",
                    "metadata": {
                        "intent": final_result.metadata.get("intent"),
                        "row_count": final_result.metadata.get("row_count"),
                        "source": final_result.metadata.get("source"),
                    },
                }
            )
            + "\n\n"
        )

    yield f"data: {json.dumps({'type': 'done'})}\n\n"
