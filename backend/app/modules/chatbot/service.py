import json
from collections.abc import Generator

from app.agents.database import create_database_agent
from app.agents.memory import create_memory_agent
from app.agents.memory.store import get_memory_summary
from app.agents.planner import create_planner_agent
from app.agents.vector import create_vector_agent
from app.modules.billing.service import record_usage_event
from app.modules.admin.service import resolve_config
from app.modules.chatbot.repository import ChatRepository
from app.modules.chatbot.schemas import ChatRequest, ChatResponse


_FALSE_VALUES = {"0", "false", "off", "no", "disabled"}


def _build_history(request: ChatRequest) -> list[dict]:
    return [{"role": m.role, "content": m.content} for m in request.history]


def _is_agent_enabled(agent_key: str, default: bool = True) -> bool:
    try:
        value = resolve_config("agents", agent_key)
    except Exception:
        return default

    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() not in _FALSE_VALUES


_KNOWLEDGE_SKIP_STAGES = {
    "greeting",
    "opening",
    "testimony",
    "promo",
    "closing",
    "farewell",
}

_KNOWLEDGE_NEEDLE_KEYWORDS = {
    "kandungan",
    "ingredient",
    "komposisi",
    "bha",
    "sulphur",
    "bpom",
    "halal",
    "exp",
    "cara pakai",
    "pakainya",
    "bahan",
    "fungsi",
}


def _detect_stage_for_context(message: str, history: list[dict]) -> str:
    """Lightweight stage detection to decide whether to call knowledge agents."""
    from app.agents.planner.agent import PlannerAgent
    intent = PlannerAgent._detect_intent(message)
    state = PlannerAgent._build_state(history)
    return PlannerAgent._resolve_stage(intent, state)


def _collect_knowledge_context(
    question: str, history: list[dict] | None = None,
) -> dict[str, str]:
    context: dict[str, str] = {}

    # Skip expensive agent calls except when consultation really needs extra facts.
    stage = _detect_stage_for_context(question, history or [])
    if stage in _KNOWLEDGE_SKIP_STAGES:
        return context
    lowered = (question or "").lower()
    if not any(keyword in lowered for keyword in _KNOWLEDGE_NEEDLE_KEYWORDS):
        return context

    if _is_agent_enabled("database", default=True):
        try:
            db_result = create_database_agent().execute(question)
            if not db_result.metadata.get("error"):
                context["database_context"] = db_result.output[:1400]
        except Exception:
            pass

    if _is_agent_enabled("vector", default=True):
        try:
            vector_result = create_vector_agent().execute(question, context={"top_k": 3})
            if not vector_result.metadata.get("error"):
                context["vector_context"] = vector_result.output[:1600]
        except Exception:
            pass

    return context


def chat(request: ChatRequest) -> ChatResponse:
    planner = create_planner_agent()
    history = _build_history(request)
    memory_summary = None
    if request.user_id:
        memory_summary = get_memory_summary(
            user_id=request.user_id,
            agent="planner",
            conversation_id=request.conversation_id,
        )

    context = {
        "user_id": request.user_id,
        "conversation_id": request.conversation_id,
        "memory_summary": memory_summary,
    }
    context.update(_collect_knowledge_context(request.message, history=history))
    result = planner.execute(request.message, history=history, context=context)

    if request.user_id:
        try:
            memory_agent = create_memory_agent()
            messages = history + [
                {"role": "user", "content": request.message},
                {"role": "assistant", "content": result.output},
            ]
            payload = {
                "action": "summarize",
                "user_id": request.user_id,
                "conversation_id": request.conversation_id,
                "agent": "planner",
                "messages": messages,
            }
            memory_agent.execute(json.dumps(payload, ensure_ascii=True))
        except Exception:
            pass

    return ChatResponse(
        status="success",
        response=result.output,
        usage=result.metadata,
    )


def chat_stream(request: ChatRequest) -> Generator[str, None, None]:
    planner = create_planner_agent()
    history = _build_history(request)
    memory_summary = None
    if request.user_id:
        memory_summary = get_memory_summary(
            user_id=request.user_id,
            agent="planner",
            conversation_id=request.conversation_id,
        )

    context = {
        "user_id": request.user_id,
        "conversation_id": request.conversation_id,
        "memory_summary": memory_summary,
    }
    context.update(_collect_knowledge_context(request.message, history=history))
    full_content = ""
    last_metadata = None

    for event in planner.execute_stream(request.message, history=history, context=context):
        if event.get("type") == "content":
            full_content += event.get("content", "")
        if event.get("type") == "meta":
            last_metadata = event.get("metadata")
        yield f"data: {json.dumps(event)}\n\n"

    yield f"data: {json.dumps({'type': 'done'})}\n\n"

    # Record billing for streaming path
    if request.user_id and last_metadata:
        try:
            record_usage_event(
                user_id=request.user_id,
                conversation_id=request.conversation_id,
                assistant_metadata=last_metadata,
            )
        except Exception:
            pass

    if request.user_id and full_content:
        try:
            memory_agent = create_memory_agent()
            messages = history + [
                {"role": "user", "content": request.message},
                {"role": "assistant", "content": full_content},
            ]
            payload = {
                "action": "summarize",
                "user_id": request.user_id,
                "conversation_id": request.conversation_id,
                "agent": "planner",
                "messages": messages,
            }
            memory_agent.execute(json.dumps(payload, ensure_ascii=True))
        except Exception:
            pass


# Conversation services.
def create_conversation(user_id: str, title: str = "New Chat") -> dict:
    return ChatRepository().create_conversation(user_id, title)


def list_conversations(user_id: str) -> list[dict]:
    return ChatRepository().list_conversations(user_id)


def get_conversation(user_id: str, conversation_id: str) -> dict | None:
    return ChatRepository().get_conversation(user_id, conversation_id)


def delete_conversation(user_id: str, conversation_id: str) -> bool:
    return ChatRepository().delete_conversation(user_id, conversation_id)


def update_conversation_title(user_id: str, conversation_id: str, title: str) -> bool:
    return ChatRepository().update_conversation_title(user_id, conversation_id, title)


def save_messages(
    user_id: str,
    conversation_id: str,
    user_message: str,
    assistant_content: str,
    assistant_thinking: str | None = None,
    assistant_metadata: dict | None = None,
) -> bool:
    saved = ChatRepository().save_messages(
        user_id,
        conversation_id,
        user_message,
        assistant_content,
        assistant_thinking,
        assistant_metadata,
    )
    if saved and assistant_metadata:
        try:
            record_usage_event(
                user_id=user_id,
                conversation_id=conversation_id,
                assistant_metadata=assistant_metadata,
            )
        except Exception:
            pass
    return saved


def list_history(
    user_id: str,
    conversation_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    return ChatRepository().list_history(
        user_id=user_id,
        conversation_id=conversation_id,
        limit=limit,
    )


def clear_history(user_id: str, conversation_id: str | None = None) -> int:
    return ChatRepository().clear_history(
        user_id=user_id,
        conversation_id=conversation_id,
    )
