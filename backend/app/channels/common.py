from app.modules.chatbot.repository import ChatRepository
from app.modules.chatbot.schemas import ChatRequest
from app.modules.chatbot.service import chat, save_messages


def _normalize_channel_user_id(channel: str, external_user_id: str) -> str:
    channel_key = (channel or "unknown").strip().lower()
    external_key = str(external_user_id or "").strip()
    return f"{channel_key}:{external_key}"


def _recent_history_from_conversation(conversation_payload: dict | None, max_messages: int = 12) -> list[dict]:
    if not conversation_payload:
        return []

    messages = conversation_payload.get("messages") or []
    filtered = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if role not in {"user", "assistant"}:
            continue
        if not content:
            continue
        filtered.append({"role": role, "content": str(content)})
    if len(filtered) > max_messages:
        return filtered[-max_messages:]
    return filtered


def process_incoming_text(
    channel: str,
    external_user_id: str,
    text: str,
    conversation_title: str,
) -> dict:
    clean_text = str(text or "").strip()
    if not clean_text:
        return {"status": "ignored", "reason": "empty_message"}

    user_id = _normalize_channel_user_id(channel, external_user_id)
    repository = ChatRepository()
    conversations = repository.list_conversations(user_id)
    if conversations:
        conversation = conversations[0]
    else:
        conversation = repository.create_conversation(user_id=user_id, title=conversation_title)

    conversation_id = conversation["id"]
    conversation_payload = repository.get_conversation(user_id=user_id, conversation_id=conversation_id)
    history = _recent_history_from_conversation(conversation_payload)

    response = chat(
        ChatRequest(
            message=clean_text,
            history=history,
            user_id=user_id,
            conversation_id=conversation_id,
        )
    )
    metadata = response.usage if isinstance(response.usage, dict) else None

    save_messages(
        user_id=user_id,
        conversation_id=conversation_id,
        user_message=clean_text,
        assistant_content=response.response,
        assistant_thinking=None,
        assistant_metadata=metadata,
    )

    return {
        "status": "ok",
        "channel_user_id": user_id,
        "conversation_id": conversation_id,
        "reply_text": response.response,
        "assistant_metadata": metadata or {},
    }

