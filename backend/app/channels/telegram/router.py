from fastapi import APIRouter, Request

from app.channels.telegram.api_schemas import TelegramWebhookResponse
from app.channels.telegram.service import handle_webhook

router = APIRouter(tags=["Channels"], prefix="/v1/channels/telegram")


@router.post("/webhook", response_model=TelegramWebhookResponse)
async def telegram_webhook_endpoint(request: Request):
    payload = await request.json()
    secret_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    return handle_webhook(payload=payload, secret_header=secret_header)

