from pydantic import BaseModel


class TelegramWebhookResponse(BaseModel):
    status: str
    detail: str | None = None

