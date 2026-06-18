from datetime import datetime

from pydantic import BaseModel


class ConversationSummary(BaseModel):
    id: int
    status: str
    channel: str
    contact_name: str | None
    phone_number: str | None
    created_at: datetime
    updated_at: datetime


class MessageSummary(BaseModel):
    id: int
    conversation_id: int
    direction: str
    sender_type: str
    body: str
    sent_at: datetime
    created_at: datetime


class HandoffSummary(BaseModel):
    id: int
    conversation_id: int
    status: str
    reason: str
    contact_name: str | None
    phone_number: str | None
    created_at: datetime

