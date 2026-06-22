from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.models.legal import (
    AiDecision,
    Client,
    ClientContact,
    Contact,
    Conversation,
    FollowUpTask,
    HandoffRequest,
    LegalMatter,
    Message,
    User,
)


class AttendanceRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_or_create_contact(
        self,
        organization_id: int,
        phone_number: str,
        display_name: str | None,
        external_contact_id: str | None,
    ) -> Contact:
        stmt = select(Contact).where(
            Contact.organization_id == organization_id,
            Contact.channel == "whatsapp",
            Contact.channel_identifier == phone_number,
        )
        contact = self.db.scalar(stmt)
        if contact:
            if display_name and contact.display_name != display_name:
                contact.display_name = display_name
            return contact

        contact = Contact(
            organization_id=organization_id,
            channel="whatsapp",
            channel_identifier=phone_number,
            phone_number=phone_number,
            display_name=display_name,
            external_contact_id=external_contact_id,
        )
        self.db.add(contact)
        try:
            self.db.flush()
            return contact
        except IntegrityError:
            self.db.rollback()
            existing_contact = self.db.scalar(stmt)
            if existing_contact:
                return existing_contact
            raise

    def get_or_create_open_conversation(
        self,
        organization_id: int,
        contact_id: int,
    ) -> Conversation:
        stmt = select(Conversation).where(
            Conversation.organization_id == organization_id,
            Conversation.contact_id == contact_id,
            Conversation.channel == "whatsapp",
            Conversation.status.in_(["open", "waiting_human", "bot_active"]),
        )
        conversation = self.db.scalar(stmt)
        if conversation:
            return conversation

        conversation = Conversation(
            organization_id=organization_id,
            contact_id=contact_id,
            channel="whatsapp",
            status="bot_active",
        )
        self.db.add(conversation)
        self.db.flush()
        return conversation

    def create_message(
        self,
        conversation_id: int,
        provider: str,
        external_message_id: str | None,
        direction: str,
        sender_type: str,
        body: str,
        sent_at: datetime,
        message_type: str = "text",
    ) -> Message:
        message = Message(
            conversation_id=conversation_id,
            provider=provider,
            external_message_id=external_message_id,
            direction=direction,
            sender_type=sender_type,
            message_type=message_type,
            body=body,
            sent_at=sent_at,
        )
        self.db.add(message)
        self.db.flush()
        return message

    def count_messages(self, conversation_id: int) -> int:
        stmt = select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
        return int(self.db.scalar(stmt) or 0)

    def get_message_by_external_id(
        self,
        provider: str,
        external_message_id: str | None,
    ) -> Message | None:
        if not external_message_id:
            return None
        stmt = select(Message).where(
            Message.provider == provider,
            Message.external_message_id == external_message_id,
        )
        return self.db.scalar(stmt)

    def create_ai_decision(
        self,
        conversation_id: int,
        inbound_message_id: int,
        action: str,
        confidence: float,
        reason: str | None,
        model_name: str | None,
    ) -> AiDecision:
        decision = AiDecision(
            conversation_id=conversation_id,
            inbound_message_id=inbound_message_id,
            action=action,
            confidence=confidence,
            reason=reason[:500] if reason else None,
            model_name=model_name,
        )
        self.db.add(decision)
        self.db.flush()
        return decision

    def create_handoff(
        self,
        conversation_id: int,
        requested_by_message_id: int,
        reason: str,
        assigned_user_id: int | None = None,
    ) -> HandoffRequest:
        handoff = HandoffRequest(
            conversation_id=conversation_id,
            requested_by_message_id=requested_by_message_id,
            reason=reason[:4000],
            status="open",
            assigned_user_id=assigned_user_id,
        )
        conversation = self.get_conversation(conversation_id)
        if conversation and assigned_user_id:
            conversation.assigned_user_id = assigned_user_id
        self.db.add(handoff)
        self.db.flush()
        return handoff

    def list_lawyers(self, organization_id: int) -> list[User]:
        stmt = (
            select(User)
            .where(
                User.organization_id == organization_id,
                User.is_active.is_(True),
                User.role.in_(["lawyer", "attorney", "advogado"]),
            )
            .order_by(User.full_name)
        )
        return list(self.db.scalars(stmt).all())

    def get_user(self, user_id: int) -> User | None:
        return self.db.get(User, user_id)

    def get_user_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email.strip().lower())
        return self.db.scalar(stmt)

    def create_lawyer(
        self,
        organization_id: int,
        full_name: str,
        email: str,
        password_hash: str | None = None,
    ) -> User:
        clean_name = full_name.strip()
        clean_email = email.strip().lower()
        existing = self.db.scalar(select(User).where(User.email == clean_email))
        if existing:
            existing.full_name = clean_name
            existing.role = "lawyer"
            existing.is_active = True
            if password_hash:
                existing.password_hash = password_hash
            self.db.flush()
            return existing
        lawyer = User(
            organization_id=organization_id,
            full_name=clean_name,
            email=clean_email,
            password_hash=password_hash,
            role="lawyer",
            is_active=True,
        )
        self.db.add(lawyer)
        self.db.flush()
        return lawyer

    def get_lawyer_by_name(
        self,
        organization_id: int,
        display_name: str | None,
    ) -> User | None:
        if not display_name:
            return None
        first_name = display_name.strip().split(" ")[0].lower()
        stmt = select(User).where(
            User.organization_id == organization_id,
            User.is_active.is_(True),
            User.role.in_(["lawyer", "attorney", "advogado"]),
        )
        for user in self.db.scalars(stmt).all():
            if user.full_name.strip().split(" ")[0].lower() == first_name:
                return user
        return None

    def cancel_scheduled_followups(
        self,
        conversation_id: int,
        canceled_at: datetime,
    ) -> int:
        stmt = select(FollowUpTask).where(
            FollowUpTask.conversation_id == conversation_id,
            FollowUpTask.status == "scheduled",
        )
        followups = list(self.db.scalars(stmt).all())
        for followup in followups:
            followup.status = "canceled"
            followup.canceled_at = canceled_at
        return len(followups)

    def create_followup(
        self,
        conversation_id: int,
        contact_id: int,
        trigger_message_id: int,
        reason: str,
        scheduled_for: datetime,
    ) -> FollowUpTask:
        followup = FollowUpTask(
            conversation_id=conversation_id,
            contact_id=contact_id,
            trigger_message_id=trigger_message_id,
            reason=reason,
            scheduled_for=scheduled_for,
            status="scheduled",
        )
        self.db.add(followup)
        self.db.flush()
        return followup

    def list_due_followups(
        self,
        now: datetime,
        limit: int = 25,
    ) -> list[tuple[FollowUpTask, Conversation, Contact]]:
        stmt = (
            select(FollowUpTask, Conversation, Contact)
            .join(Conversation, FollowUpTask.conversation_id == Conversation.id)
            .join(Contact, FollowUpTask.contact_id == Contact.id)
            .where(
                FollowUpTask.status == "scheduled",
                FollowUpTask.scheduled_for <= now,
                Conversation.status == "bot_active",
            )
            .order_by(FollowUpTask.scheduled_for, FollowUpTask.id)
            .limit(limit)
        )
        return list(self.db.execute(stmt).all())

    def list_followups(
        self,
        limit: int = 50,
    ) -> list[tuple[FollowUpTask, Conversation, Contact]]:
        stmt = (
            select(FollowUpTask, Conversation, Contact)
            .join(Conversation, FollowUpTask.conversation_id == Conversation.id)
            .join(Contact, FollowUpTask.contact_id == Contact.id)
            .order_by(desc(FollowUpTask.created_at), desc(FollowUpTask.id))
            .limit(limit)
        )
        return list(self.db.execute(stmt).all())

    def mark_followup_sent(
        self,
        followup: FollowUpTask,
        sent_message_id: int,
        sent_at: datetime,
    ) -> None:
        followup.status = "sent"
        followup.sent_message_id = sent_message_id
        followup.sent_at = sent_at

    def list_conversations(self, limit: int = 50) -> list[tuple[Conversation, Contact]]:
        stmt = (
            select(Conversation, Contact)
            .join(Contact, Conversation.contact_id == Contact.id)
            .order_by(desc(Conversation.updated_at), desc(Conversation.id))
            .limit(limit)
        )
        return list(self.db.execute(stmt).all())

    def get_conversation(self, conversation_id: int) -> Conversation | None:
        return self.db.get(Conversation, conversation_id)

    def get_conversation_with_contact(
        self,
        conversation_id: int,
    ) -> tuple[Conversation, Contact] | None:
        stmt = (
            select(Conversation, Contact)
            .join(Contact, Conversation.contact_id == Contact.id)
            .where(Conversation.id == conversation_id)
        )
        return self.db.execute(stmt).first()

    def close_conversation(self, conversation_id: int) -> Conversation | None:
        conversation = self.get_conversation(conversation_id)
        if conversation:
            conversation.status = "closed"
            open_handoffs = self.db.scalars(
                select(HandoffRequest).where(
                    HandoffRequest.conversation_id == conversation_id,
                    HandoffRequest.status == "open",
                )
            ).all()
            for handoff in open_handoffs:
                handoff.status = "resolved"
                handoff.resolved_at = datetime.now()
            self.db.flush()
        return conversation

    def list_messages(self, conversation_id: int) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at, Message.id)
        )
        return list(self.db.scalars(stmt).all())

    def list_recent_messages(
        self,
        conversation_id: int,
        limit: int = 8,
    ) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(desc(Message.created_at), desc(Message.id))
            .limit(limit)
        )
        return list(reversed(self.db.scalars(stmt).all()))

    def list_recent_document_messages(
        self,
        conversation_id: int,
        limit: int = 2,
    ) -> list[Message]:
        stmt = (
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.message_type.in_(["document", "image"]),
            )
            .order_by(desc(Message.created_at), desc(Message.id))
            .limit(limit)
        )
        return list(reversed(self.db.scalars(stmt).all()))

    def list_open_handoffs(
        self,
        limit: int = 50,
        assigned_user_id: int | None = None,
    ) -> list[tuple[HandoffRequest, Conversation, Contact]]:
        stmt = (
            select(HandoffRequest, Conversation, Contact)
            .join(Conversation, HandoffRequest.conversation_id == Conversation.id)
            .join(Contact, Conversation.contact_id == Contact.id)
            .where(HandoffRequest.status == "open")
            .order_by(desc(HandoffRequest.created_at), desc(HandoffRequest.id))
            .limit(limit)
        )
        if assigned_user_id is not None:
            stmt = stmt.where(HandoffRequest.assigned_user_id == assigned_user_id)
        return list(self.db.execute(stmt).all())

    def resolve_handoff(self, handoff_id: int) -> HandoffRequest | None:
        handoff = self.db.get(HandoffRequest, handoff_id)
        if handoff and handoff.status == "open":
            handoff.status = "resolved"
            handoff.resolved_at = datetime.now()
            conversation = self.get_conversation(handoff.conversation_id)
            if conversation and conversation.status == "waiting_human":
                # The human finished this attendance, but the WhatsApp conversation
                # remains available so the client can return with another question.
                conversation.status = "bot_active"
            self.db.flush()
        return handoff

    def assign_handoff(
        self,
        handoff_id: int,
        assigned_user_id: int,
    ) -> HandoffRequest | None:
        handoff = self.db.get(HandoffRequest, handoff_id)
        user = self.get_user(assigned_user_id)
        if not handoff or not user:
            return None
        handoff.assigned_user_id = assigned_user_id
        conversation = self.get_conversation(handoff.conversation_id)
        if conversation:
            conversation.assigned_user_id = assigned_user_id
        self.db.flush()
        return handoff

    def list_pending_queue(
        self,
        organization_id: int,
        assigned_user_id: int | None = None,
        only_assigned: bool = False,
        limit: int = 100,
    ) -> list[dict]:
        handoff_rows = (
            select(HandoffRequest, Conversation, Contact, Client)
            .join(Conversation, HandoffRequest.conversation_id == Conversation.id)
            .join(Contact, Conversation.contact_id == Contact.id)
            .outerjoin(Client, Conversation.client_id == Client.id)
            .where(
                Conversation.organization_id == organization_id,
                HandoffRequest.status == "open",
            )
            .order_by(desc(HandoffRequest.created_at), desc(HandoffRequest.id))
            .limit(limit)
        )
        if assigned_user_id is not None:
            handoff_rows = handoff_rows.where(HandoffRequest.assigned_user_id == assigned_user_id)
        elif only_assigned:
            handoff_rows = handoff_rows.where(HandoffRequest.assigned_user_id.is_not(None))

        followup_rows = (
            select(FollowUpTask, Conversation, Contact, Client)
            .join(Conversation, FollowUpTask.conversation_id == Conversation.id)
            .join(Contact, FollowUpTask.contact_id == Contact.id)
            .outerjoin(Client, Conversation.client_id == Client.id)
            .where(
                Conversation.organization_id == organization_id,
                FollowUpTask.status == "scheduled",
            )
            .order_by(FollowUpTask.scheduled_for, FollowUpTask.id)
            .limit(limit)
        )
        if assigned_user_id is not None:
            followup_rows = followup_rows.where(Conversation.assigned_user_id == assigned_user_id)
        elif only_assigned:
            followup_rows = followup_rows.where(Conversation.assigned_user_id.is_not(None))

        pending_items = []
        for handoff, conversation, contact, client in self.db.execute(handoff_rows).all():
            assigned_user = self.get_user(handoff.assigned_user_id) if handoff.assigned_user_id else None
            pending_items.append(
                {
                    "kind": "handoff",
                    "id": handoff.id,
                    "conversation": conversation,
                    "contact": contact,
                    "client": client,
                    "reason": handoff.reason,
                    "created_at": handoff.created_at,
                    "due_at": None,
                    "status": handoff.status,
                    "can_resolve": True,
                    "assigned_user": assigned_user,
                }
            )
        for followup, conversation, contact, client in self.db.execute(followup_rows).all():
            assigned_user = self.get_user(conversation.assigned_user_id) if conversation.assigned_user_id else None
            pending_items.append(
                {
                    "kind": "followup",
                    "id": followup.id,
                    "conversation": conversation,
                    "contact": contact,
                    "client": client,
                    "reason": followup.reason,
                    "created_at": followup.created_at,
                    "due_at": followup.scheduled_for,
                    "status": followup.status,
                    "can_resolve": False,
                    "assigned_user": assigned_user,
                }
            )
        return pending_items

    def crm_stats(self, organization_id: int) -> dict[str, int]:
        conversation_count = self.db.scalar(
            select(func.count(Conversation.id)).where(
                Conversation.organization_id == organization_id,
            )
        )
        active_conversation_count = self.db.scalar(
            select(func.count(Conversation.id)).where(
                Conversation.organization_id == organization_id,
                Conversation.status.in_(["open", "bot_active", "waiting_human"]),
            )
        )
        waiting_human_count = self.db.scalar(
            select(func.count(Conversation.id)).where(
                Conversation.organization_id == organization_id,
                Conversation.status == "waiting_human",
            )
        )
        contact_count = self.db.scalar(
            select(func.count(Contact.id)).where(Contact.organization_id == organization_id)
        )
        open_handoff_count = self.db.scalar(
            select(func.count(HandoffRequest.id))
            .join(Conversation, HandoffRequest.conversation_id == Conversation.id)
            .where(
                Conversation.organization_id == organization_id,
                HandoffRequest.status == "open",
            )
        )
        scheduled_followup_count = self.db.scalar(
            select(func.count(FollowUpTask.id))
            .join(Conversation, FollowUpTask.conversation_id == Conversation.id)
            .where(
                Conversation.organization_id == organization_id,
                FollowUpTask.status == "scheduled",
            )
        )
        return {
            "conversations": int(conversation_count or 0),
            "active_conversations": int(active_conversation_count or 0),
            "waiting_human": int(waiting_human_count or 0),
            "contacts": int(contact_count or 0),
            "open_handoffs": int(open_handoff_count or 0),
            "scheduled_followups": int(scheduled_followup_count or 0),
        }

    def list_crm_conversations(
        self,
        organization_id: int,
        status: str | None = None,
        query: str | None = None,
        assigned_user_id: int | None = None,
        limit: int = 100,
    ) -> list[tuple[Conversation, Contact, Client | None, int, datetime | None, str | None]]:
        first_message = aliased(Message)
        first_inbound_message_ids = (
            select(
                Message.conversation_id.label("conversation_id"),
                func.min(Message.id).label("first_message_id"),
            )
            .where(Message.direction == "inbound")
            .group_by(Message.conversation_id)
            .subquery()
        )
        message_stats = (
            select(
                Message.conversation_id.label("conversation_id"),
                func.count(Message.id).label("message_count"),
                func.max(Message.sent_at).label("last_message_at"),
            )
            .group_by(Message.conversation_id)
            .subquery()
        )
        stmt = (
            select(
                Conversation,
                Contact,
                Client,
                message_stats.c.message_count,
                message_stats.c.last_message_at,
                func.coalesce(Conversation.subject, first_message.body).label("subject"),
            )
            .join(Contact, Conversation.contact_id == Contact.id)
            .outerjoin(Client, Conversation.client_id == Client.id)
            .outerjoin(message_stats, message_stats.c.conversation_id == Conversation.id)
            .outerjoin(
                first_inbound_message_ids,
                first_inbound_message_ids.c.conversation_id == Conversation.id,
            )
            .outerjoin(first_message, first_message.id == first_inbound_message_ids.c.first_message_id)
            .where(Conversation.organization_id == organization_id)
            .order_by(desc(Conversation.updated_at), desc(Conversation.id))
            .limit(limit)
        )
        if status:
            stmt = stmt.where(Conversation.status == status)
        if assigned_user_id is not None:
            stmt = stmt.where(Conversation.assigned_user_id == assigned_user_id)
        if query:
            like_query = f"%{query.strip()}%"
            stmt = stmt.where(
                or_(
                    Contact.display_name.ilike(like_query),
                    Contact.phone_number.ilike(like_query),
                    Client.display_name.ilike(like_query),
                    Client.document_number.ilike(like_query),
                    first_message.body.ilike(like_query),
                )
            )
        rows = self.db.execute(stmt).all()
        return [
            (
                conversation,
                contact,
                client,
                int(message_count or 0),
                last_message_at,
                subject,
            )
            for conversation, contact, client, message_count, last_message_at, subject in rows
        ]

    def list_crm_contacts(
        self,
        organization_id: int,
        query: str | None = None,
        assigned_user_id: int | None = None,
        limit: int = 100,
    ) -> list[tuple[Contact, Client | None, int, datetime | None]]:
        conversation_stats_stmt = (
            select(
                Conversation.contact_id.label("contact_id"),
                func.count(Conversation.id).label("conversation_count"),
                func.max(Conversation.updated_at).label("last_conversation_at"),
            )
            .where(Conversation.organization_id == organization_id)
            .group_by(Conversation.contact_id)
        )
        if assigned_user_id is not None:
            conversation_stats_stmt = conversation_stats_stmt.where(Conversation.assigned_user_id == assigned_user_id)
        conversation_stats = conversation_stats_stmt.subquery()
        stmt = (
            select(
                Contact,
                Client,
                conversation_stats.c.conversation_count,
                conversation_stats.c.last_conversation_at,
            )
            .outerjoin(ClientContact, ClientContact.contact_id == Contact.id)
            .outerjoin(Client, ClientContact.client_id == Client.id)
            .outerjoin(conversation_stats, conversation_stats.c.contact_id == Contact.id)
            .where(Contact.organization_id == organization_id)
            .order_by(desc(conversation_stats.c.last_conversation_at), desc(Contact.id))
            .limit(limit)
        )
        if assigned_user_id is not None:
            stmt = stmt.where(conversation_stats.c.conversation_count.is_not(None))
        if query:
            like_query = f"%{query.strip()}%"
            stmt = stmt.where(
                or_(
                    Contact.display_name.ilike(like_query),
                    Contact.phone_number.ilike(like_query),
                    Client.display_name.ilike(like_query),
                    Client.document_number.ilike(like_query),
                )
            )
        rows = self.db.execute(stmt).all()
        return [
            (
                contact,
                client,
                int(conversation_count or 0),
                last_conversation_at,
            )
            for contact, client, conversation_count, last_conversation_at in rows
        ]

    def get_contact_profile(
        self,
        contact_id: int,
    ) -> tuple[Contact, Client | None] | None:
        stmt = (
            select(Contact, Client)
            .outerjoin(ClientContact, ClientContact.contact_id == Contact.id)
            .outerjoin(Client, ClientContact.client_id == Client.id)
            .where(Contact.id == contact_id)
        )
        return self.db.execute(stmt).first()

    def list_conversations_for_contact(
        self,
        contact_id: int,
        assigned_user_id: int | None = None,
        limit: int = 50,
    ) -> list[Conversation]:
        stmt = (
            select(Conversation)
            .where(Conversation.contact_id == contact_id)
            .order_by(desc(Conversation.updated_at), desc(Conversation.id))
            .limit(limit)
        )
        if assigned_user_id is not None:
            stmt = stmt.where(Conversation.assigned_user_id == assigned_user_id)
        return list(self.db.scalars(stmt).all())

    def get_conversation_subject(self, conversation_id: int) -> str | None:
        conversation_subject = self.db.scalar(
            select(Conversation.subject).where(Conversation.id == conversation_id)
        )
        if conversation_subject:
            return conversation_subject
        stmt = (
            select(Message.body)
            .where(
                Message.conversation_id == conversation_id,
                Message.direction == "inbound",
            )
            .order_by(Message.created_at, Message.id)
            .limit(1)
        )
        return self.db.scalar(stmt)

    def list_legal_matters_for_client(self, client_id: int) -> list[LegalMatter]:
        stmt = (
            select(LegalMatter)
            .where(LegalMatter.client_id == client_id)
            .order_by(desc(LegalMatter.updated_at), desc(LegalMatter.id))
        )
        return list(self.db.scalars(stmt).all())

    def create_legal_matter(
        self,
        organization_id: int,
        client_id: int,
        title: str,
        matter_type: str | None,
        process_number: str | None,
        status: str,
    ) -> LegalMatter:
        matter = LegalMatter(
            organization_id=organization_id,
            client_id=client_id,
            title=title.strip(),
            matter_type=(matter_type or "").strip() or None,
            process_number=(process_number or "").strip() or None,
            status=status,
        )
        self.db.add(matter)
        self.db.flush()
        return matter

    def save_contact_client_profile(
        self,
        organization_id: int,
        contact_id: int,
        contact_name: str | None,
        client_name: str | None,
        document_number: str | None,
        client_status: str,
    ) -> tuple[Contact, Client]:
        contact = self.db.get(Contact, contact_id)
        if not contact:
            raise ValueError("Contact not found.")
        clean_contact_name = (contact_name or "").strip()
        if clean_contact_name:
            contact.display_name = clean_contact_name

        stmt = (
            select(Client, ClientContact)
            .join(ClientContact, ClientContact.client_id == Client.id)
            .where(ClientContact.contact_id == contact_id)
        )
        row = self.db.execute(stmt).first()
        client = row[0] if row else None
        clean_client_name = (client_name or clean_contact_name or contact.display_name or "Cliente").strip()
        clean_document = (document_number or "").strip() or None

        if not client:
            client = Client(
                organization_id=organization_id,
                display_name=clean_client_name,
                person_type="person",
                document_number=clean_document,
                status=client_status,
            )
            self.db.add(client)
            self.db.flush()
            self.db.add(
                ClientContact(
                    client_id=client.id,
                    contact_id=contact.id,
                    relationship_label="WhatsApp",
                    is_primary=True,
                )
            )
        else:
            client.display_name = clean_client_name
            client.document_number = clean_document
            client.status = client_status

        for conversation in self.list_conversations_for_contact(contact_id):
            if conversation.client_id is None:
                conversation.client_id = client.id
        self.db.flush()
        return contact, client
