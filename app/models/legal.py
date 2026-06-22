from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


IdColumn = BigInteger().with_variant(Integer, "sqlite")


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(IdColumn, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    document_number: Mapped[Optional[str]] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), default="active")


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(IdColumn, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(180), nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(String(220))
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Client(Base, TimestampMixin):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(IdColumn, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    display_name: Mapped[str] = mapped_column(String(180), nullable=False)
    person_type: Mapped[str] = mapped_column(String(20), default="unknown")
    document_number: Mapped[Optional[str]] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), default="active")


class Contact(Base, TimestampMixin):
    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("organization_id", "channel", "channel_identifier"),
    )

    id: Mapped[int] = mapped_column(IdColumn, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    channel: Mapped[str] = mapped_column(String(24), nullable=False)
    channel_identifier: Mapped[str] = mapped_column(String(80), nullable=False)
    phone_number: Mapped[Optional[str]] = mapped_column(String(32))
    display_name: Mapped[Optional[str]] = mapped_column(String(180))
    external_contact_id: Mapped[Optional[str]] = mapped_column(String(120))


class ClientContact(Base, TimestampMixin):
    __tablename__ = "client_contacts"
    __table_args__ = (UniqueConstraint("client_id", "contact_id"),)

    id: Mapped[int] = mapped_column(IdColumn, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"), nullable=False)
    relationship_label: Mapped[Optional[str]] = mapped_column(String(80))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)


class LegalMatter(Base, TimestampMixin):
    __tablename__ = "legal_matters"

    id: Mapped[int] = mapped_column(IdColumn, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    matter_type: Mapped[Optional[str]] = mapped_column(String(80))
    process_number: Mapped[Optional[str]] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(40), default="active")


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(IdColumn, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"), nullable=False)
    client_id: Mapped[Optional[int]] = mapped_column(ForeignKey("clients.id"))
    legal_matter_id: Mapped[Optional[int]] = mapped_column(ForeignKey("legal_matters.id"))
    channel: Mapped[str] = mapped_column(String(24), nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(String(220))
    status: Mapped[str] = mapped_column(String(32), default="open")
    assigned_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))

    messages: Mapped[list["Message"]] = relationship(back_populates="conversation")


class Message(Base, TimestampMixin):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("provider", "external_message_id"),)

    id: Mapped[int] = mapped_column(IdColumn, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    external_message_id: Mapped[Optional[str]] = mapped_column(String(160))
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    sender_type: Mapped[str] = mapped_column(String(24), nullable=False)
    message_type: Mapped[str] = mapped_column(String(24), default="text")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class AiDecision(Base, TimestampMixin):
    __tablename__ = "ai_decisions"

    id: Mapped[int] = mapped_column(IdColumn, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    inbound_message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[Numeric] = mapped_column(Numeric(5, 4), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(500))
    model_name: Mapped[Optional[str]] = mapped_column(String(80))
    prompt_version: Mapped[str] = mapped_column(String(40), default="legal-v1")


class HandoffRequest(Base, TimestampMixin):
    __tablename__ = "handoff_requests"

    id: Mapped[int] = mapped_column(IdColumn, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    requested_by_message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="open")
    assigned_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class FollowUpTask(Base, TimestampMixin):
    __tablename__ = "follow_up_tasks"

    id: Mapped[int] = mapped_column(IdColumn, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"), nullable=False)
    trigger_message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="scheduled")
    reason: Mapped[str] = mapped_column(String(220), nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    sent_message_id: Mapped[Optional[int]] = mapped_column(ForeignKey("messages.id"))
    canceled_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class KnowledgeArticle(Base, TimestampMixin):
    __tablename__ = "knowledge_articles"

    id: Mapped[int] = mapped_column(IdColumn, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(80))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    approved_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
