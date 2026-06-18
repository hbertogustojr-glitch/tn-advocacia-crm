from datetime import datetime

from pydantic import BaseModel


class FollowUpProcessResult(BaseModel):
    processed: int
    sent: int
    errors: list[str] = []


class FollowUpSummary(BaseModel):
    id: int
    conversation_id: int
    contact_name: str | None
    phone_number: str | None
    status: str
    reason: str
    scheduled_for: datetime

