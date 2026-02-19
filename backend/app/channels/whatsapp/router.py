from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.channels.whatsapp.api_schemas import WhatsappWebhookResponse
from app.channels.whatsapp.service import count_incoming_text_messages, handle_webhook
from app.core.config import settings

router = APIRouter(tags=["Channels"], prefix="/v1/channels/whatsapp")


@router.get("/webhook")
async def verify_whatsapp_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    expected_token = (settings.WHATSAPP_VERIFY_TOKEN or "").strip()
    if not expected_token:
        raise HTTPException(status_code=503, detail="WHATSAPP_VERIFY_TOKEN is not configured")

    if hub_mode == "subscribe" and hub_verify_token == expected_token:
        return PlainTextResponse(content=hub_challenge or "", status_code=200)

    raise HTTPException(status_code=403, detail="Invalid WhatsApp verify token")


@router.post("/webhook", response_model=WhatsappWebhookResponse)
async def whatsapp_webhook_endpoint(request: Request, background_tasks: BackgroundTasks):
    payload = await request.json()
    queued = count_incoming_text_messages(payload)
    background_tasks.add_task(handle_webhook, payload)
    return WhatsappWebhookResponse(
        status="accepted",
        processed_messages=queued,
        detail="WhatsApp webhook accepted",
    )
