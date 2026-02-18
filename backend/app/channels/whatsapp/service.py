import logging
import threading
import time

import httpx

from app.channels.common import process_incoming_text
from app.channels.media import (
    format_testimony_reply_text,
    get_testimony_images,
    looks_like_testimony_reply,
)
from app.core.config import settings

logger = logging.getLogger(__name__)


def _get_whatsapp_api_context() -> tuple[str, str, str] | None:
    access_token = (settings.WHATSAPP_ACCESS_TOKEN or "").strip()
    phone_number_id = (settings.WHATSAPP_PHONE_NUMBER_ID or "").strip()
    api_version = (settings.WHATSAPP_API_VERSION or "v22.0").strip()

    if not access_token or not phone_number_id:
        logger.warning(
            "WhatsApp credentials are incomplete (WHATSAPP_ACCESS_TOKEN/WHATSAPP_PHONE_NUMBER_ID)."
        )
        return None

    return access_token, phone_number_id, api_version


def _post_whatsapp_payload(payload: dict) -> None:
    context = _get_whatsapp_api_context()
    if context is None:
        return

    access_token, phone_number_id, api_version = context
    url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"

    with httpx.Client(timeout=20.0) as client:
        response = client.post(
            url,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}",
            },
            json=payload,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"WhatsApp API request failed ({response.status_code}): {response.text}"
            ) from exc


def _send_whatsapp_message(recipient: str, text: str) -> None:
    _post_whatsapp_payload(
        {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "text",
            "text": {"body": text},
        }
    )


def _send_whatsapp_image(recipient: str, image_url: str, caption: str | None = None) -> None:
    image_payload: dict[str, object] = {"link": image_url}
    if caption:
        image_payload["caption"] = caption

    _post_whatsapp_payload(
        {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "image",
            "image": image_payload,
        }
    )


def _send_whatsapp_typing_indicator(message_id: str) -> bool:
    if not message_id:
        return False

    _post_whatsapp_payload(
        {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
            "typing_indicator": {"type": "text"},
        }
    )
    return True


class _WhatsAppTypingHeartbeat:
    """Keep WhatsApp typing indicator alive while response is being generated."""

    def __init__(
        self,
        message_id: str,
        interval_seconds: float = 20.0,
        minimum_visible_seconds: float = 1.0,
    ):
        self._message_id = message_id
        self._interval_seconds = interval_seconds
        self._minimum_visible_seconds = minimum_visible_seconds
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._started_at = 0.0

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                _send_whatsapp_typing_indicator(self._message_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to send WhatsApp typing indicator: %s", exc)
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
        self._thread.join(timeout=2.0)
        return False


def _should_attach_testimony_media(stage: str, user_text: str, assistant_text: str) -> bool:
    if stage == "testimony":
        return True

    lowered = (user_text or "").lower()
    if any(token in lowered for token in {"testimoni", "review", "bukti", "real"}):
        return True

    return looks_like_testimony_reply(assistant_text)


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
                inbound_message_id = str(message.get("id") or "").strip()
                body = str((message.get("text") or {}).get("body") or "").strip()
                if not sender or not body:
                    continue

                with _WhatsAppTypingHeartbeat(message_id=inbound_message_id):
                    result = process_incoming_text(
                        channel="whatsapp",
                        external_user_id=sender,
                        text=body,
                        conversation_title=f"WhatsApp {sender}",
                    )

                metadata = result.get("assistant_metadata") or {}
                stage = str(metadata.get("stage") or "").strip().lower()
                reply_text = str(result.get("reply_text") or "").strip()

                if _should_attach_testimony_media(stage=stage, user_text=body, assistant_text=reply_text) and reply_text:
                    try:
                        base_url = (settings.PUBLIC_BASE_URL or "").strip()
                        images = get_testimony_images(base_url=base_url) if base_url else []
                        for image in images:
                            try:
                                _send_whatsapp_image(
                                    recipient=sender,
                                    image_url=image.image_url,
                                    caption=image.title,
                                )
                            except Exception as media_exc:  # noqa: BLE001
                                logger.warning(
                                    "Failed to send WhatsApp image %s: %s",
                                    image.title,
                                    media_exc,
                                )

                        reply_text = format_testimony_reply_text(reply_text)
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("Failed to send WhatsApp testimonial media: %s", exc)
                        reply_text = format_testimony_reply_text(reply_text)

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
