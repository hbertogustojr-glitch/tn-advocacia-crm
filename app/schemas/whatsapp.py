from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class WhatsAppInboundPayload(BaseModel):
    provider: str = Field(default="whatsapp_cloud_api", max_length=40)
    organization_id: int | None = None
    external_contact_id: str | None = None
    phone_number: str = Field(min_length=8, max_length=32)
    contact_name: str | None = Field(default=None, max_length=180)
    external_message_id: str | None = Field(default=None, max_length=160)
    message_text: str = Field(min_length=1)
    sent_at: datetime


class WhatsAppAutomationResult(BaseModel):
    conversation_id: int
    action: Literal["reply", "handoff", "ignore"]
    reply_text: str | None = None
    handoff_reason: str | None = None


class AiRoutingDecision(BaseModel):
    action: Literal["reply", "handoff", "close"]
    reply_text: str | None = None
    handoff_reason: str | None = None
    lawyer_summary: str | None = None
    conversation_status: Literal["active", "closed", "waiting_human"] = "active"
    confidence: float = Field(ge=0, le=1)
