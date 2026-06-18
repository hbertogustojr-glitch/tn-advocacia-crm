from pydantic import BaseModel


class MetaInboundMessage(BaseModel):
    provider: str = "meta_whatsapp_cloud_api"
    external_contact_id: str | None = None
    phone_number: str
    contact_name: str | None = None
    external_message_id: str
    message_text: str
    sent_at_unix: int


class MetaWebhookProcessResult(BaseModel):
    received: bool = True
    processed_messages: int
    replies_sent: int
    handoffs_created: int
    errors: list[str] = []

