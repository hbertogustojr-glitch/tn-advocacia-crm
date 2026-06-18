from datetime import datetime

from pydantic import BaseModel


class EvolutionInboundMessage(BaseModel):
    provider: str = "evolution_api"
    instance: str | None = None
    phone_number: str
    contact_name: str | None = None
    external_message_id: str
    message_text: str
    sent_at: datetime


class EvolutionWebhookProcessResult(BaseModel):
    received: bool = True
    processed_messages: int
    replies_sent: int
    handoffs_created: int
    ignored_messages: int = 0
    errors: list[str] = []

