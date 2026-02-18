from pydantic import BaseModel


class WhatsappWebhookResponse(BaseModel):
    status: str
    processed_messages: int = 0
    detail: str | None = None

