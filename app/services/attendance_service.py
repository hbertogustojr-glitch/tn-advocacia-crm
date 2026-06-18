from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.attendance_repository import AttendanceRepository
from app.schemas.whatsapp import WhatsAppInboundPayload, WhatsAppAutomationResult
from app.services.claude_service import ClaudeService
from app.services.followup_service import FollowUpService
from app.services.routing_rules import RoutingRules


class AttendanceService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = AttendanceRepository(db)
        self.claude = ClaudeService()
        self.followups = FollowUpService(db)

    def handle_inbound_whatsapp(
        self,
        payload: WhatsAppInboundPayload,
    ) -> WhatsAppAutomationResult:
        organization_id = payload.organization_id or settings.default_organization_id
        contact = self.repository.get_or_create_contact(
            organization_id=organization_id,
            phone_number=payload.phone_number,
            display_name=payload.contact_name,
            external_contact_id=payload.external_contact_id,
        )
        conversation = self.repository.get_or_create_open_conversation(
            organization_id=organization_id,
            contact_id=contact.id,
        )
        is_first_message = self.repository.count_messages(conversation.id) == 0
        was_waiting_human = conversation.status == "waiting_human"
        existing_message = self.repository.get_message_by_external_id(
            provider=payload.provider,
            external_message_id=payload.external_message_id,
        )
        if existing_message:
            return WhatsAppAutomationResult(conversation_id=conversation.id, action="ignore")

        inbound = self.repository.create_message(
            conversation_id=conversation.id,
            provider=payload.provider,
            external_message_id=payload.external_message_id,
            direction="inbound",
            sender_type="client",
            body=payload.message_text,
            sent_at=payload.sent_at,
        )
        self.repository.cancel_scheduled_followups(
            conversation_id=conversation.id,
            canceled_at=datetime.now(timezone.utc),
        )
        if was_waiting_human:
            self.db.commit()
            return WhatsAppAutomationResult(conversation_id=conversation.id, action="ignore")

        if not is_first_message and RoutingRules.is_closing_message(payload.message_text):
            reply_text = self._closing_reply(contact.display_name)
            self.repository.create_ai_decision(
                conversation_id=conversation.id,
                inbound_message_id=inbound.id,
                action="close",
                confidence=0.95,
                reason="Cliente encerrou a conversa.",
                model_name="routing-rules",
            )
            self.repository.create_message(
                conversation_id=conversation.id,
                provider=payload.provider,
                external_message_id=None,
                direction="outbound",
                sender_type="ai",
                body=reply_text,
                sent_at=datetime.now(timezone.utc),
            )
            conversation.status = "closed"
            self.db.commit()
            return WhatsAppAutomationResult(
                conversation_id=conversation.id,
                action="reply",
                reply_text=reply_text,
            )

        routing_rule = RoutingRules.classify(payload.message_text)
        if routing_rule:
            assigned_user = self.repository.get_lawyer_by_name(
                organization_id=organization_id,
                display_name=routing_rule.assigned_human_name,
            )
            self.repository.create_ai_decision(
                conversation_id=conversation.id,
                inbound_message_id=inbound.id,
                action=routing_rule.action,
                confidence=0.95,
                reason=routing_rule.reason,
                model_name="routing-rules",
            )
            conversation.status = "waiting_human"
            self.repository.create_handoff(
                conversation_id=conversation.id,
                requested_by_message_id=inbound.id,
                reason=routing_rule.reason,
                assigned_user_id=assigned_user.id if assigned_user else None,
            )
            self.db.commit()
            return WhatsAppAutomationResult(
                conversation_id=conversation.id,
                action="handoff",
                handoff_reason=routing_rule.reason,
            )

        decision = self.claude.decide_response(
            client_name=self._client_display_name(contact.id, contact.display_name),
            message_text=payload.message_text,
            is_first_message=is_first_message,
            greeting=self.claude.greeting_for_now(),
            crm_status=self._crm_status(contact.id, is_first_message),
            active_processes="Nenhum processo ativo informado no CRM.",
            recent_history=self._recent_history(conversation.id),
            conversation_status=self._conversation_status_for_prompt(conversation.status),
            last_interaction=self._last_interaction_for_prompt(conversation.updated_at),
        )
        self.repository.create_ai_decision(
            conversation_id=conversation.id,
            inbound_message_id=inbound.id,
            action=decision.action,
            confidence=decision.confidence,
            reason=decision.handoff_reason,
            model_name=settings.claude_model,
        )

        if decision.action == "close":
            reply_text = decision.reply_text or "Perfeito. Qualquer dúvida é só chamar."
            self.repository.create_message(
                conversation_id=conversation.id,
                provider=payload.provider,
                external_message_id=None,
                direction="outbound",
                sender_type="ai",
                body=reply_text,
                sent_at=datetime.now(timezone.utc),
            )
            conversation.status = "closed"
            self.db.commit()
            return WhatsAppAutomationResult(
                conversation_id=conversation.id,
                action="reply",
                reply_text=reply_text,
            )

        if decision.action == "handoff":
            conversation.status = "waiting_human"
            self.repository.create_handoff(
                conversation_id=conversation.id,
                requested_by_message_id=inbound.id,
                reason=self._handoff_reason(decision),
            )
            self.db.commit()
            return WhatsAppAutomationResult(
                conversation_id=conversation.id,
                action="handoff",
                handoff_reason=decision.handoff_reason,
            )

        if not settings.auto_reply_enabled:
            self.db.commit()
            return WhatsAppAutomationResult(conversation_id=conversation.id, action="ignore")

        reply_text = decision.reply_text or "Recebi sua mensagem. Vou verificar e já retorno."
        self.followups.maybe_schedule_from_client_message(
            conversation_id=conversation.id,
            contact_id=contact.id,
            trigger_message_id=inbound.id,
            message_text=payload.message_text,
        )
        self.repository.create_message(
            conversation_id=conversation.id,
            provider=payload.provider,
            external_message_id=None,
            direction="outbound",
            sender_type="ai",
            body=reply_text,
            sent_at=datetime.now(timezone.utc),
        )
        conversation.status = "bot_active"
        self.db.commit()
        return WhatsAppAutomationResult(
            conversation_id=conversation.id,
            action="reply",
            reply_text=reply_text,
        )

    def _client_display_name(
        self,
        contact_id: int,
        fallback_name: str | None,
    ) -> str | None:
        profile = self.repository.get_contact_profile(contact_id)
        if profile and profile[1]:
            return profile[1].display_name
        return fallback_name

    def _crm_status(self, contact_id: int, is_first_message: bool) -> str:
        profile = self.repository.get_contact_profile(contact_id)
        if profile and profile[1]:
            if profile[1].status == "active":
                return "cliente_ativo"
            return profile[1].status
        if is_first_message:
            return "desconhecido"
        return "lead"

    def _recent_history(self, conversation_id: int) -> str:
        messages = self.repository.list_recent_messages(conversation_id)
        if not messages:
            return "Sem historico recente."
        lines = []
        for message in messages:
            sender = "cliente" if message.direction == "inbound" else message.sender_type
            lines.append(f"- {sender}: {message.body}")
        return "\n".join(lines)

    @staticmethod
    def _conversation_status_for_prompt(status: str) -> str:
        status_map = {
            "bot_active": "ativa",
            "open": "ativa",
            "closed": "encerrada",
            "waiting_human": "aguardando_advogado",
        }
        return status_map.get(status, "ativa")

    @staticmethod
    def _last_interaction_for_prompt(updated_at) -> str:
        if not updated_at:
            return "Sem ultima interacao registrada."
        return str(updated_at)

    @staticmethod
    def _handoff_reason(decision) -> str:
        reason = decision.handoff_reason or "Atendimento precisa de humano."
        if decision.lawyer_summary:
            return f"{reason} Resumo: {decision.lawyer_summary}"
        return reason

    @staticmethod
    def _closing_reply(client_name: str | None) -> str:
        first_name = (client_name or "").strip().split(" ")[0]
        if first_name:
            return f"Perfeito, {first_name}! Qualquer dúvida é só chamar."
        return "Perfeito! Qualquer dúvida é só chamar."
