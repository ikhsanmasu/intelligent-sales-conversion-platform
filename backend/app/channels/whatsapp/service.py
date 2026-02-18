import json
import logging
from urllib import request as urllib_request

from app.channels.common import process_incoming_text
from app.core.config import settings

logger = logging.getLogger(__name__)


def _send_whatsapp_message(recipient: str, text: str) -> None:
    access_token = (settings.WHATSAPP_ACCESS_TOKEN or "").strip()
    phone_number_id = (settings.WHATSAPP_PHONE_NUMBER_ID or "").strip()
    api_version = (settings.WHATSAPP_API_VERSION or "v22.0").strip()

    if not access_token or not phone_number_id:
        logger.warning(
            "WhatsApp credentials are incomplete (WHATSAPP_ACCESS_TOKEN/WHATSAPP_PHONE_NUMBER_ID)."
        )
        return

    url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "text",
        "text": {"body": text},
    }
    data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    req = urllib_request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
        },
        method="POST",
    )
    with urllib_request.urlopen(req, timeout=20) as response:  # noqa: S310
        _ = response.read()


def handle_webhook(payload: dict) -> dict:
    processed_messages = 0

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value") or {}
            messages = value.get("messages") or []
            for message in messages:
                if message.get("type") != "text":
                    continue

                sender = str(message.get("from") or "").strip()
                body = str((message.get("text") or {}).get("body") or "").strip()
                if not sender or not body:
                    continue

                result = process_incoming_text(
                    channel="whatsapp",
                    external_user_id=sender,
                    text=body,
                    conversation_title=f"WhatsApp {sender}",
                )
                reply_text = str(result.get("reply_text") or "").strip()
                if reply_text:
                    try:
                        _send_whatsapp_message(recipient=sender, text=reply_text)
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("Failed to send WhatsApp reply: %s", exc)
                processed_messages += 1

    return {
        "status": "ok",
        "processed_messages": processed_messages,
        "detail": "WhatsApp webhook processed",
    }

