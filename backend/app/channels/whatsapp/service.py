import json
import logging
from urllib import request as urllib_request

from app.channels.common import process_incoming_text
from app.channels.media import format_testimony_reply_text, pick_random_testimonial_image
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


def _send_whatsapp_typing_indicator(message_id: str) -> None:
    if not message_id:
        return
    # Meta Cloud API supports typing indicator via read status payload.
    _post_whatsapp_payload(
        {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
            "typing_indicator": {"type": "text"},
        }
    )


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

                if inbound_message_id:
                    try:
                        _send_whatsapp_typing_indicator(message_id=inbound_message_id)
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("Failed to send WhatsApp typing indicator: %s", exc)

                result = process_incoming_text(
                    channel="whatsapp",
                    external_user_id=sender,
                    text=body,
                    conversation_title=f"WhatsApp {sender}",
                )

                metadata = result.get("assistant_metadata") or {}
                stage = str(metadata.get("stage") or "").strip().lower()
                reply_text = str(result.get("reply_text") or "").strip()
                if stage == "testimony" and reply_text:
                    try:
                        image = pick_random_testimonial_image()
                        _send_whatsapp_image(
                            recipient=sender,
                            image_url=image.image_url,
                            caption=f"Vibes testimoni hari ini: {image.title}",
                        )
                        reply_text = format_testimony_reply_text(reply_text)
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("Failed to send WhatsApp testimonial photo: %s", exc)

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
