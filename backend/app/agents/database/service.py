import json
from collections.abc import Generator

from app.agents.database import create_database_agent
from app.agents.database.api_schemas import QueryRequest, QueryResponse
from app.core.llm import create_llm


def query(request: QueryRequest) -> QueryResponse:
    agent = create_database_agent()
    result = agent.execute(request.question)

    return QueryResponse(
        status="success",
        response=result.output,
        sql=result.metadata.get("sql", ""),
        row_count=result.metadata.get("row_count", 0),
    )


def query_stream(request: QueryRequest) -> Generator[str, None, None]:
    from app.agents.planner.streaming import parse_think_tags
    from app.modules.admin.service import resolve_prompt

    llm = create_llm(config_group="llm_database")
    agent = create_database_agent(llm=llm)

    # Stream step-by-step thinking from DatabaseAgent.
    db_result = None
    for event in agent.execute_stream(request.question):
        if event.get("type") == "_result":
            db_result = event["data"]
        else:
            yield f"data: {json.dumps(event)}\n\n"

    if db_result is None:
        yield f"data: {json.dumps({'type': 'content', 'content': 'Error: Database agent returned no result.'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    # Stream synthesis.
    messages = [
        {"role": "system", "content": resolve_prompt("synthesis_system")},
        {"role": "user", "content": resolve_prompt("synthesis_user").format(
            question=request.question,
            results=db_result.output,
        )},
    ]
    chunks = llm.generate_stream(messages=messages)
    for event in parse_think_tags(chunks):
        yield f"data: {json.dumps(event)}\n\n"

    yield f"data: {json.dumps({'type': 'done'})}\n\n"
