import logging
import threading
import time

import httpx
from fastapi import HTTPException

from app.channels.common import natural_read_delay, process_incoming_text
from app.channels.media import (
    format_testimony_reply_text,
    get_testimony_images,
    looks_like_testimony_reply,
)
from app.core.config import settings

logger = logging.getLogger(__name__)


def _telegram_api_request(method: str, payload: dict) -> None:
    token = (settings.TELEGRAM_BOT_TOKEN or "").strip()
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN is empty, skip Telegram API call: %s", method)
        return

    url = f"https://api.telegram.org/bot{token}/{method}"
    with httpx.Client(timeout=20.0) as client:
        response = client.post(url, json=payload)
        try:
            body = response.json()
        except ValueError:
            body = {"raw": response.text}

        if response.status_code >= 400:
            raise RuntimeError(
                f"Telegram API {method} failed ({response.status_code}): {body}"
            )

        if not body.get("ok", False):
            raise RuntimeError(f"Telegram API error on {method}: {body}")


def _send_telegram_message(chat_id: str, text: str) -> None:
    _telegram_api_request(
        method="sendMessage",
        payload={
            "chat_id": chat_id,
            "text": text,
        },
    )


def _send_telegram_photo(chat_id: str, photo_url: str, caption: str | None = None) -> None:
    payload: dict[str, str] = {
        "chat_id": chat_id,
        "photo": photo_url,
    }
    if caption:
        payload["caption"] = caption[:1024]
    _telegram_api_request(method="sendPhoto", payload=payload)


def _send_telegram_typing_action(chat_id: str) -> None:
    _telegram_api_request(
        method="sendChatAction",
        payload={
            "chat_id": chat_id,
            "action": "typing",
        },
    )


class _TelegramTypingHeartbeat:
    """Keep Telegram typing indicator alive while response is being generated."""

    def __init__(
        self,
        chat_id: str,
        interval_seconds: float = 3.5,
        minimum_visible_seconds: float = 1.4,
    ):
        self._chat_id = chat_id
        self._interval_seconds = interval_seconds
        self._minimum_visible_seconds = minimum_visible_seconds
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._started_at = 0.0

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                _send_telegram_typing_action(self._chat_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to send Telegram typing action: %s", exc)
            if self._stop_event.wait(self._interval_seconds):
                return

    def __enter__(self):
        self._started_at = time.monotonic()
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = time.monotonic() - self._started_at
        remaining = self._minimum_visible_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)
        self._stop_event.set()
        self._thread.join(timeout=1.0)
        return False


def _should_attach_testimony_media(stage: str, user_text: str, assistant_text: str) -> bool:
    if stage == "testimony":
        return True

    lowered = (user_text or "").lower()
    if any(token in lowered for token in {"testimoni", "review", "bukti"}):
        return True

    return looks_like_testimony_reply(assistant_text)


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
    time.sleep(natural_read_delay(text))
    with _TelegramTypingHeartbeat(chat_id=chat_id):
        result = process_incoming_text(
            channel="telegram",
            external_user_id=chat_id,
            text=text,
            conversation_title=f"Telegram {chat_id}",
        )

    metadata = result.get("assistant_metadata") or {}
    stage = str(metadata.get("stage") or "").strip().lower()
    reply_text = str(result.get("reply_text") or "").strip()

    if _should_attach_testimony_media(stage=stage, user_text=text, assistant_text=reply_text) and reply_text:
        try:
            base_url = (settings.PUBLIC_BASE_URL or "").strip()
            images = get_testimony_images(base_url=base_url) if base_url else []
            for image in images:
                try:
                    _send_telegram_photo(
                        chat_id=chat_id,
                        photo_url=image.image_url,
                        caption=image.title,
                    )
                except Exception as photo_exc:  # noqa: BLE001
                    logger.warning(
                        "Failed to send Telegram photo %s: %s",
                        image.title,
                        photo_exc,
                    )
            reply_text = format_testimony_reply_text(reply_text)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to prepare Telegram testimonial media: %s", exc)
            reply_text = format_testimony_reply_text(reply_text)

    if reply_text:
        try:
            _send_telegram_message(chat_id=chat_id, text=reply_text)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to send Telegram reply: %s", exc)

    return {"status": "ok", "detail": "Telegram webhook processed"}
