from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.modules.chatbot.schemas import (
    ChatRequest,
    ChatResponse,
    ConversationDetail,
    ConversationSummary,
    CreateConversationRequest,
    HistoryEntry,
    SaveMessagesRequest,
    UpdateConversationTitleRequest,
)
from app.modules.chatbot.service import (
    chat,
    chat_stream,
    clear_history,
    create_conversation,
    delete_conversation,
    get_conversation,
    list_history,
    list_conversations,
    save_messages,
    update_conversation_title,
)

router = APIRouter(tags=["Chatbot"], prefix="/v1/chatbot")


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    return chat(request=request)


@router.post("/chat/stream")
async def chat_stream_endpoint(request: ChatRequest):
    return StreamingResponse(
        chat_stream(request),
        media_type="text/event-stream",
    )


@router.get("/conversations/{user_id}", response_model=list[ConversationSummary])
async def list_conversations_endpoint(user_id: str):
    return list_conversations(user_id)


@router.post("/conversations/{user_id}", response_model=ConversationSummary)
async def create_conversation_endpoint(user_id: str, request: CreateConversationRequest):
    return create_conversation(user_id, request.title)


@router.get("/conversations/{user_id}/{conversation_id}", response_model=ConversationDetail)
async def get_conversation_endpoint(user_id: str, conversation_id: str):
    conv = get_conversation(user_id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.delete("/conversations/{user_id}/{conversation_id}")
async def delete_conversation_endpoint(user_id: str, conversation_id: str):
    deleted = delete_conversation(user_id, conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "deleted"}


@router.patch("/conversations/{user_id}/{conversation_id}/title")
async def update_title_endpoint(
    user_id: str, conversation_id: str, request: UpdateConversationTitleRequest
):
    updated = update_conversation_title(user_id, conversation_id, request.title)
    if not updated:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "updated"}


@router.post("/conversations/{user_id}/{conversation_id}/messages")
async def save_messages_endpoint(
    user_id: str, conversation_id: str, request: SaveMessagesRequest
):
    saved = save_messages(
        user_id,
        conversation_id,
        request.user_message,
        request.assistant_content,
        request.assistant_thinking,
        request.assistant_metadata,
    )
    if not saved:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "saved"}


@router.get("/history/{user_id}", response_model=list[HistoryEntry])
async def list_history_endpoint(
    user_id: str,
    conversation_id: str | None = None,
    limit: int = 100,
):
    safe_limit = max(1, min(limit, 500))
    return list_history(user_id, conversation_id=conversation_id, limit=safe_limit)


@router.delete("/history/{user_id}")
async def clear_history_endpoint(user_id: str, conversation_id: str | None = None):
    deleted_count = clear_history(user_id, conversation_id=conversation_id)
    return {"status": "deleted", "deleted_count": deleted_count}
