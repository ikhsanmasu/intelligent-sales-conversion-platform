import json
import re
from collections.abc import Generator

from app.agents.database import create_database_agent
from app.agents.memory import create_memory_agent
from app.agents.memory.store import get_memory_summary
from app.agents.planner import create_planner_agent
from app.agents.vector import create_vector_agent
from app.channels.media import build_testimony_markdown_images, looks_like_testimony_reply
from app.modules.billing.service import record_usage_event
from app.modules.admin.service import resolve_config
from app.modules.chatbot.repository import ChatRepository
from app.modules.chatbot.schemas import ChatRequest, ChatResponse


_FALSE_VALUES = {"0", "false", "off", "no", "disabled"}
_KNOWN_CHANNELS = {"telegram", "whatsapp", "web"}

_READY_TO_BUY_PATTERNS = (
    r"\bmau (?:langsung )?(?:beli|checkout|co|order|pesan)\b",
    r"\bjadi (?:beli|checkout|co|order)\b",
    r"\blanjut (?:checkout|order|beli)\b",
)
_READY_TO_BUY_KEYWORDS = {
    "checkout",
    "order sekarang",
    "pesan sekarang",
}
_NOT_INTERESTED_KEYWORDS = {
    "ga jadi",
    "gak jadi",
    "tidak jadi",
    "nanti dulu",
    "belum dulu",
    "ga dulu",
    "gak dulu",
    "skip dulu",
    "tidak tertarik",
}
_CONSIDERING_KEYWORDS = {
    "harga",
    "berapa",
    "promo",
    "diskon",
    "ongkir",
    "testimoni",
    "review",
    "cocok gak",
    "aman gak",
}
_NEEDS_INFO_KEYWORDS = {
    "jerawat",
    "berminyak",
    "bruntusan",
    "komedo",
    "sensitif",
    "cara pakai",
    "kandungan",
    "bpom",
    "halal",
}
_TOPIC_KEYWORDS = {
    "skin concern": {"jerawat", "berminyak", "bruntusan", "komedo", "sensitif"},
    "price": {"harga", "promo", "diskon", "ongkir", "murah", "mahal"},
    "testimony": {"testimoni", "review", "bukti"},
    "usage": {"cara pakai", "pemakaian", "pakai", "gunakan"},
}


def _maybe_append_testimony_images(text: str, stage: str) -> str:
    """Append markdown testimony images when the response is a testimony reply."""
    if stage == "testimony" or looks_like_testimony_reply(text):
        images_md = build_testimony_markdown_images()
        if images_md:
            return f"{text.rstrip()}\n\n{images_md}"
    return text


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

    # Inject testimony images for dashboard/API consumers
    stage = (result.metadata or {}).get("stage", "")
    result.output = _maybe_append_testimony_images(result.output, stage)

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

    # Inject testimony images at end of stream for dashboard rendering
    stream_stage = (last_metadata or {}).get("stage", "")
    if stream_stage == "testimony" or looks_like_testimony_reply(full_content):
        images_md = build_testimony_markdown_images()
        if images_md:
            img_chunk = f"\n\n{images_md}"
            full_content += img_chunk
            yield f"data: {json.dumps({'type': 'content', 'content': img_chunk})}\n\n"

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


def _extract_channel_identity(user_id: str) -> tuple[str, str]:
    raw = str(user_id or "").strip()
    if ":" not in raw:
        if raw in _KNOWN_CHANNELS:
            return raw, ""
        return "web", raw

    channel, external_user_id = raw.split(":", 1)
    channel = channel.strip().lower() or "web"
    external_user_id = external_user_id.strip()
    if channel not in _KNOWN_CHANNELS:
        return "web", raw
    return channel, external_user_id


def _normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _contains_keyword(text: str, keywords: set[str]) -> bool:
    lowered = _normalize_for_match(text)
    return any(keyword in lowered for keyword in keywords)


def _is_ready_to_buy(text: str) -> bool:
    lowered = _normalize_for_match(text)
    if any(re.search(pattern, lowered) for pattern in _READY_TO_BUY_PATTERNS):
        return True
    return any(keyword in lowered for keyword in _READY_TO_BUY_KEYWORDS)


def _derive_lead_status(user_messages: list[str]) -> str:
    joined = _normalize_for_match(" ".join(user_messages))
    if not joined:
        return "unknown"

    if _contains_keyword(joined, _NOT_INTERESTED_KEYWORDS):
        return "not_interested"
    if _is_ready_to_buy(joined):
        return "ready_to_buy"
    if _contains_keyword(joined, _CONSIDERING_KEYWORDS):
        return "considering"
    if _contains_keyword(joined, _NEEDS_INFO_KEYWORDS):
        return "needs_info"
    return "unknown"


def _build_topics_summary(user_messages: list[str]) -> str:
    joined = _normalize_for_match(" ".join(user_messages))
    topics = []
    for topic, keywords in _TOPIC_KEYWORDS.items():
        if any(keyword in joined for keyword in keywords):
            topics.append(topic)
    if not topics:
        return "general inquiry"
    return ", ".join(topics)


def _shorten_text(text: str, max_chars: int = 140) -> str:
    clean = " ".join(str(text or "").split())
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 3].rstrip() + "..."


def _build_monitor_payload(conversation: dict) -> dict:
    messages = list(conversation.get("messages") or [])
    user_messages = [
        str(item.get("content") or "")
        for item in messages
        if str(item.get("role") or "").strip().lower() == "user"
    ]
    assistant_messages = [
        str(item.get("content") or "")
        for item in messages
        if str(item.get("role") or "").strip().lower() == "assistant"
    ]

    channel, external_user_id = _extract_channel_identity(conversation.get("user_id", ""))
    lead_status = _derive_lead_status(user_messages)
    topics_summary = _build_topics_summary(user_messages)
    summary = (
        f"Lead status: {lead_status.replace('_', ' ')}. "
        f"Primary topics: {topics_summary}."
    )

    return {
        "id": conversation["id"],
        "user_id": conversation["user_id"],
        "channel": channel,
        "external_user_id": external_user_id,
        "title": conversation["title"],
        "created_at": float(conversation["created_at"]),
        "updated_at": float(conversation["updated_at"]),
        "message_count": len(messages),
        "lead_status": lead_status,
        "summary": summary,
        "last_user_message": _shorten_text(user_messages[-1] if user_messages else ""),
        "last_assistant_message": _shorten_text(
            assistant_messages[-1] if assistant_messages else ""
        ),
        "messages": messages,
    }


def list_monitor_conversations(
    limit: int = 50,
    offset: int = 0,
    channel: str | None = None,
    lead_status: str | None = None,
    query: str | None = None,
) -> list[dict]:
    safe_limit = max(1, min(limit, 200))
    safe_offset = max(0, offset)
    channel_filter = str(channel or "").strip().lower()
    lead_filter = str(lead_status or "").strip().lower()
    query_filter = _normalize_for_match(query or "")

    repository = ChatRepository()
    # Pull a wider window then filter in memory.
    base_rows = repository.list_conversations_global(limit=500, offset=0)

    monitored_rows = []
    for row in base_rows:
        detail = repository.get_conversation_by_id(row["id"])
        if not detail:
            continue
        monitored = _build_monitor_payload(detail)

        if channel_filter and channel_filter != "all" and monitored["channel"] != channel_filter:
            continue
        if lead_filter and lead_filter != "all" and monitored["lead_status"] != lead_filter:
            continue
        if query_filter:
            haystack = _normalize_for_match(
                " ".join(
                    [
                        monitored["title"],
                        monitored["user_id"],
                        monitored["external_user_id"],
                        monitored["summary"],
                        monitored["last_user_message"],
                        monitored["last_assistant_message"],
                    ]
                )
            )
            if query_filter not in haystack:
                continue

        monitored_rows.append(monitored)

    return monitored_rows[safe_offset : safe_offset + safe_limit]


def get_monitor_conversation(conversation_id: str) -> dict | None:
    repository = ChatRepository()
    detail = repository.get_conversation_by_id(conversation_id)
    if not detail:
        return None
    monitored = _build_monitor_payload(detail)
    return monitored
