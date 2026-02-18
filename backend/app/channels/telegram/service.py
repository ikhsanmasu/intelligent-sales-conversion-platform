import json
import logging
from urllib import request as urllib_request

from fastapi import HTTPException

from app.channels.common import process_incoming_text
from app.core.config import settings

logger = logging.getLogger(__name__)


def _send_telegram_message(chat_id: str, text: str) -> None:
    token = (settings.TELEGRAM_BOT_TOKEN or "").strip()
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN is empty, skip sendMessage.")
        return

    payload = {
        "chat_id": chat_id,
        "text": text,
    }
    data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    req = urllib_request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib_request.urlopen(req, timeout=20) as response:  # noqa: S310
        _ = response.read()


def _extract_text_message(payload: dict) -> tuple[str, str] | None:
    message = payload.get("message") or payload.get("edited_message")
    if not isinstance(message, dict):
        return None

    text = str(message.get("text") or "").strip()
    chat_obj = message.get("chat") or {}
    chat_id = str(chat_obj.get("id") or "").strip()
    if not chat_id or not text:
        return None
    return chat_id, text


def handle_webhook(payload: dict, secret_header: str | None = None) -> dict:
    expected_secret = (settings.TELEGRAM_WEBHOOK_SECRET or "").strip()
    provided_secret = (secret_header or "").strip()
    if expected_secret and expected_secret != provided_secret:
        raise HTTPException(status_code=403, detail="Invalid Telegram webhook secret")

    extracted = _extract_text_message(payload)
    if extracted is None:
        return {"status": "ignored", "detail": "No text message payload"}

    chat_id, text = extracted
    result = process_incoming_text(
        channel="telegram",
        external_user_id=chat_id,
        text=text,
        conversation_title=f"Telegram {chat_id}",
    )
    reply_text = str(result.get("reply_text") or "").strip()
    if reply_text:
        try:
            _send_telegram_message(chat_id=chat_id, text=reply_text)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to send Telegram reply: %s", exc)

    return {"status": "ok", "detail": "Telegram webhook processed"}

