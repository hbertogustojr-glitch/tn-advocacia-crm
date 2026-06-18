from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.attendance_repository import AttendanceRepository
from app.schemas.followup import FollowUpProcessResult
from app.services.meta_whatsapp_service import MetaWhatsAppService
from app.services.routing_rules import RoutingRules


class FollowUpService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = AttendanceRepository(db)
        self.meta = MetaWhatsAppService()

    def maybe_schedule_from_client_message(
        self,
        conversation_id: int,
        contact_id: int,
        trigger_message_id: int,
        message_text: str,
    ) -> None:
        if not settings.follow_up_enabled:
            return
        reason = self._followup_reason(message_text)
        if not reason:
            return

        delay_hours = settings.follow_up_delay_hours
        scheduled_for = datetime.now(timezone.utc) + timedelta(hours=delay_hours)
        self.repository.create_followup(
            conversation_id=conversation_id,
            contact_id=contact_id,
            trigger_message_id=trigger_message_id,
            reason=reason,
            scheduled_for=scheduled_for,
        )

    def process_due_followups(self) -> FollowUpProcessResult:
        now = datetime.now(timezone.utc)
        rows = self.repository.list_due_followups(now=now)
        result = FollowUpProcessResult(processed=0, sent=0)

        for followup, conversation, contact in rows:
            result.processed += 1
            text = self._build_followup_text(contact.display_name)
            try:
                external_message_id = None
                if contact.phone_number:
                    external_message_id = self.meta.send_text_message(contact.phone_number, text)
                sent_message = self.repository.create_message(
                    conversation_id=conversation.id,
                    provider="meta_whatsapp_cloud_api",
                    external_message_id=external_message_id,
                    direction="outbound",
                    sender_type="ai",
                    body=text,
                    sent_at=now,
                )
                self.repository.mark_followup_sent(
                    followup=followup,
                    sent_message_id=sent_message.id,
                    sent_at=now,
                )
                result.sent += 1
            except Exception as exc:
                result.errors.append(f"followup {followup.id}: {exc}")

        self.db.commit()
        return result

    @staticmethod
    def _followup_reason(message_text: str) -> str | None:
        normalized = message_text.lower()
        triggers = [
            "vou falar com meu marido",
            "vou falar com minha esposa",
            "vou falar com meu esposo",
            "vou falar com minha mulher",
            "vou falar com meu pai",
            "vou falar com minha mae",
            "vou falar com minha mãe",
            "vou conversar com meu marido",
            "vou conversar com minha esposa",
            "vou pensar",
            "vou decidir",
            "te retorno",
            "retorno depois",
            "falo depois",
            "respondo depois",
        ]
        document_waiting_terms = [
            "vou enviar os documentos",
            "vou mandar os documentos",
            "envio os documentos",
            "mando os documentos",
            "vou providenciar os documentos",
            "vou enviar a documentacao",
            "vou enviar a documentação",
        ]
        document_commitment_terms = [
            "vou enviar",
            "vou mandar",
            "vou providenciar",
            "vou separar",
            "envio",
            "mando",
        ]
        is_question = "?" in normalized
        if not is_question and any(trigger in normalized for trigger in document_waiting_terms):
            return "Cliente ficou de enviar documentacao solicitada."
        if not is_question and RoutingRules.mentions_documents(message_text) and any(
            trigger in normalized for trigger in document_commitment_terms
        ):
            return "Cliente ficou de enviar documentacao solicitada."
        if RoutingRules.mentions_documents(message_text) and any(trigger in normalized for trigger in triggers):
            return "Cliente indicou que enviara documentacao depois."
        if any(trigger in normalized for trigger in triggers):
            return "Cliente indicou que vai conversar/decidir e retornar depois."
        return None

    @staticmethod
    def _build_followup_text(contact_name: str | None) -> str:
        greeting = f"Olá, {contact_name}." if contact_name else "Olá."
        return (
            f"{greeting} Passando para lembrar sobre a continuidade do atendimento. "
            "Se ficou de enviar documentos, pode encaminhar por aqui. Se preferir, "
            "tambem posso direcionar seu contato para Camilla ou Thiago."
        )
