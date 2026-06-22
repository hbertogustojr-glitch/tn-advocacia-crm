from html import escape

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.repositories.attendance_repository import AttendanceRepository
from app.schemas.evolution import EvolutionWebhookProcessResult
from app.schemas.followup import FollowUpProcessResult, FollowUpSummary
from app.schemas.internal import ConversationSummary, HandoffSummary, MessageSummary
from app.schemas.meta import MetaWebhookProcessResult
from app.schemas.whatsapp import WhatsAppInboundPayload, WhatsAppAutomationResult
from app.services.attendance_service import AttendanceService
from app.services.evolution_service import EvolutionService
from app.services.followup_service import FollowUpService
from app.services.document_service import DocumentService
from app.services.meta_whatsapp_service import MetaWhatsAppService


router = APIRouter()


@router.post("/webhooks/n8n/whatsapp", response_model=WhatsAppAutomationResult)
def receive_whatsapp_message(
    payload: WhatsAppInboundPayload,
    db: Session = Depends(get_db),
) -> WhatsAppAutomationResult:
    service = AttendanceService(db)
    return service.handle_inbound_whatsapp(payload)


@router.get("/webhooks/meta/whatsapp", response_class=PlainTextResponse)
def verify_meta_whatsapp_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> str:
    service = MetaWhatsAppService()
    challenge = service.verify_webhook(hub_mode, hub_verify_token, hub_challenge)
    if challenge is None:
        raise HTTPException(status_code=403, detail="Invalid Meta webhook verification token.")
    return challenge


@router.post("/webhooks/meta/whatsapp", response_model=MetaWebhookProcessResult)
async def receive_meta_whatsapp_webhook(
    request: Request,
    db: Session = Depends(get_db),
) -> MetaWebhookProcessResult:
    payload = await request.json()
    meta_service = MetaWhatsAppService()
    attendance_service = AttendanceService(db)
    messages = meta_service.extract_text_messages(payload)

    result = MetaWebhookProcessResult(
        processed_messages=0,
        replies_sent=0,
        handoffs_created=0,
    )
    for message in messages:
        inbound = WhatsAppInboundPayload(
            provider=message.provider,
            organization_id=settings.default_organization_id,
            external_contact_id=message.external_contact_id,
            phone_number=message.phone_number,
            contact_name=message.contact_name,
            external_message_id=message.external_message_id,
            message_text=message.message_text,
            sent_at=meta_service.to_datetime(message.sent_at_unix),
        )
        automation = attendance_service.handle_inbound_whatsapp(inbound)
        result.processed_messages += 1

        if automation.action == "reply" and automation.reply_text:
            try:
                meta_service.send_text_message(message.phone_number, automation.reply_text)
                result.replies_sent += 1
            except Exception as exc:
                result.errors.append(f"conversation {automation.conversation_id}: {exc}")
        elif automation.action == "handoff":
            result.handoffs_created += 1
            if settings.meta_send_handoff_ack:
                try:
                    handoff_text = automation.reply_text or meta_service.handoff_ack_text()
                    meta_service.send_text_message(message.phone_number, handoff_text)
                    result.replies_sent += 1
                except Exception as exc:
                    result.errors.append(f"conversation {automation.conversation_id}: {exc}")

    return result


@router.post("/webhooks/evolution/whatsapp", response_model=EvolutionWebhookProcessResult)
async def receive_evolution_whatsapp_webhook(
    request: Request,
    db: Session = Depends(get_db),
) -> EvolutionWebhookProcessResult:
    return await _process_evolution_webhook(request, db)


@router.post("/webhooks/evolution/whatsapp/{event_name}", response_model=EvolutionWebhookProcessResult)
async def receive_evolution_whatsapp_event_webhook(
    event_name: str,
    request: Request,
    db: Session = Depends(get_db),
) -> EvolutionWebhookProcessResult:
    return await _process_evolution_webhook(request, db)


async def _process_evolution_webhook(
    request: Request,
    db: Session,
) -> EvolutionWebhookProcessResult:
    payload = await request.json()
    evolution_service = EvolutionService()
    attendance_service = AttendanceService(db)
    messages = evolution_service.extract_text_messages(payload)

    result = EvolutionWebhookProcessResult(
        processed_messages=0,
        replies_sent=0,
        handoffs_created=0,
    )
    for message in messages:
        if message.message_type in {"document", "image"}:
            media_base64 = message.media_base64
            if not media_base64:
                try:
                    media_base64 = evolution_service.get_media_base64(message.external_message_id)
                except Exception as exc:
                    result.errors.append(f"media {message.external_message_id}: {exc}")
            document_context = DocumentService().analyze(
                media_base64=media_base64,
                mimetype=message.media_mimetype,
                filename=message.media_filename,
            )
            caption = message.message_text if message.message_text != "Arquivo enviado pelo cliente." else ""
            message.message_text = DocumentService.context_message(
                filename=message.media_filename,
                caption=caption,
                analysis=document_context,
            )
        inbound = WhatsAppInboundPayload(
            provider=message.provider,
            organization_id=settings.default_organization_id,
            external_contact_id=message.phone_number,
            phone_number=message.phone_number,
            contact_name=message.contact_name,
            external_message_id=message.external_message_id,
            message_text=message.message_text,
            message_type=message.message_type,
            sent_at=message.sent_at,
        )
        automation = attendance_service.handle_inbound_whatsapp(inbound)
        result.processed_messages += 1

        if automation.action == "reply" and automation.reply_text:
            try:
                evolution_service.send_text_message(message.phone_number, automation.reply_text)
                result.replies_sent += 1
            except Exception as exc:
                result.errors.append(f"conversation {automation.conversation_id}: {exc}")
        elif automation.action == "handoff":
            result.handoffs_created += 1
            if settings.evolution_send_handoff_ack:
                try:
                    handoff_text = automation.reply_text or evolution_service.handoff_ack_text()
                    evolution_service.send_text_message(message.phone_number, handoff_text)
                    result.replies_sent += 1
                except Exception as exc:
                    result.errors.append(f"conversation {automation.conversation_id}: {exc}")
        elif automation.action == "ignore":
            result.ignored_messages += 1

    return result


@router.get("/internal/conversations", response_model=list[ConversationSummary])
def list_conversations(db: Session = Depends(get_db)) -> list[ConversationSummary]:
    repository = AttendanceRepository(db)
    rows = repository.list_conversations()
    return [
        ConversationSummary(
            id=conversation.id,
            status=conversation.status,
            channel=conversation.channel,
            contact_name=contact.display_name,
            phone_number=contact.phone_number,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )
        for conversation, contact in rows
    ]


@router.get("/internal/conversations/{conversation_id}/messages", response_model=list[MessageSummary])
def list_conversation_messages(
    conversation_id: int,
    db: Session = Depends(get_db),
) -> list[MessageSummary]:
    repository = AttendanceRepository(db)
    return [
        MessageSummary(
            id=message.id,
            conversation_id=message.conversation_id,
            direction=message.direction,
            sender_type=message.sender_type,
            body=message.body,
            sent_at=message.sent_at,
            created_at=message.created_at,
        )
        for message in repository.list_messages(conversation_id)
    ]


@router.post("/internal/conversations/{conversation_id}/close", response_model=ConversationSummary)
def close_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
) -> ConversationSummary:
    repository = AttendanceRepository(db)
    conversation = repository.close_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    db.commit()
    matched = repository.get_conversation_with_contact(conversation_id)
    if not matched:
        raise HTTPException(status_code=404, detail="Conversation contact not found.")
    conversation, contact = matched
    return ConversationSummary(
        id=conversation.id,
        status=conversation.status,
        channel=conversation.channel,
        contact_name=getattr(contact, "display_name", None),
        phone_number=getattr(contact, "phone_number", None),
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


@router.get("/internal/handoffs", response_model=list[HandoffSummary])
def list_handoffs(db: Session = Depends(get_db)) -> list[HandoffSummary]:
    repository = AttendanceRepository(db)
    rows = repository.list_open_handoffs()
    return [
        HandoffSummary(
            id=handoff.id,
            conversation_id=conversation.id,
            status=handoff.status,
            reason=handoff.reason,
            contact_name=contact.display_name,
            phone_number=contact.phone_number,
            created_at=handoff.created_at,
        )
        for handoff, conversation, contact in rows
    ]


@router.get("/internal/followups", response_model=list[FollowUpSummary])
def list_followups(db: Session = Depends(get_db)) -> list[FollowUpSummary]:
    repository = AttendanceRepository(db)
    rows = repository.list_followups()
    return [
        FollowUpSummary(
            id=followup.id,
            conversation_id=conversation.id,
            contact_name=contact.display_name,
            phone_number=contact.phone_number,
            status=followup.status,
            reason=followup.reason,
            scheduled_for=followup.scheduled_for,
        )
        for followup, conversation, contact in rows
    ]


@router.post("/internal/followups/process", response_model=FollowUpProcessResult)
def process_followups(db: Session = Depends(get_db)) -> FollowUpProcessResult:
    service = FollowUpService(db)
    return service.process_due_followups()


@router.get("/internal/dashboard", response_class=HTMLResponse)
def dashboard(db: Session = Depends(get_db)) -> str:
    repository = AttendanceRepository(db)
    conversations = repository.list_conversations()
    handoffs = repository.list_open_handoffs()
    followups = repository.list_followups()

    conversation_rows = "\n".join(
        f"""
        <tr>
            <td>#{conversation.id}</td>
            <td>{escape(contact.display_name or "-")}</td>
            <td>{escape(contact.phone_number or "-")}</td>
            <td><span class="badge">{conversation.status}</span></td>
            <td><a href="/internal/conversations/{conversation.id}">ver mensagens</a></td>
        </tr>
        """
        for conversation, contact in conversations
    )
    handoff_rows = "\n".join(
        f"""
        <tr>
            <td>#{handoff.id}</td>
            <td>#{conversation.id}</td>
            <td>{escape(contact.display_name or "-")}</td>
            <td>{escape(handoff.reason)}</td>
        </tr>
        """
        for handoff, conversation, contact in handoffs
    )
    followup_rows = "\n".join(
        f"""
        <tr>
            <td>#{followup.id}</td>
            <td>#{conversation.id}</td>
            <td>{escape(contact.display_name or "-")}</td>
            <td><span class="badge">{escape(followup.status)}</span></td>
            <td>{followup.scheduled_for}</td>
            <td>{escape(followup.reason)}</td>
        </tr>
        """
        for followup, conversation, contact in followups
    )

    return f"""
    <!doctype html>
    <html lang="pt-BR">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Atendimento Legal</title>
        <style>
            body {{
                margin: 0;
                font-family: Arial, sans-serif;
                background: #f6f7f9;
                color: #1f2933;
            }}
            header {{
                background: #1f2933;
                color: white;
                padding: 24px 32px;
            }}
            main {{
                max-width: 1100px;
                margin: 0 auto;
                padding: 28px 20px 48px;
            }}
            section {{
                margin-bottom: 32px;
            }}
            h1, h2 {{
                margin: 0 0 14px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                background: white;
                border: 1px solid #dde2e8;
            }}
            th, td {{
                padding: 12px 14px;
                border-bottom: 1px solid #e6eaf0;
                text-align: left;
                font-size: 14px;
            }}
            th {{
                background: #eef2f6;
                font-weight: 700;
            }}
            a {{
                color: #0f766e;
                font-weight: 700;
                text-decoration: none;
            }}
            .badge {{
                display: inline-block;
                padding: 4px 8px;
                border-radius: 6px;
                background: #e0f2fe;
                color: #075985;
                font-size: 12px;
                font-weight: 700;
            }}
            .empty {{
                background: white;
                border: 1px solid #dde2e8;
                padding: 14px;
            }}
        </style>
    </head>
    <body>
        <header>
            <h1>Atendimento Legal</h1>
        </header>
        <main>
            <section>
                <h2>Conversas</h2>
                <table>
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Contato</th>
                            <th>Telefone</th>
                            <th>Status</th>
                            <th>Mensagens</th>
                        </tr>
                    </thead>
                    <tbody>
                        {conversation_rows or '<tr><td colspan="5">Nenhuma conversa ainda.</td></tr>'}
                    </tbody>
                </table>
            </section>
            <section>
                <h2>Handoffs Pendentes</h2>
                <table>
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Conversa</th>
                            <th>Contato</th>
                            <th>Motivo</th>
                        </tr>
                    </thead>
                    <tbody>
                        {handoff_rows or '<tr><td colspan="4">Nenhum handoff pendente.</td></tr>'}
                    </tbody>
                </table>
            </section>
            <section>
                <h2>Follow-ups</h2>
                <table>
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Conversa</th>
                            <th>Contato</th>
                            <th>Status</th>
                            <th>Agendado para</th>
                            <th>Motivo</th>
                        </tr>
                    </thead>
                    <tbody>
                        {followup_rows or '<tr><td colspan="6">Nenhum follow-up registrado.</td></tr>'}
                    </tbody>
                </table>
            </section>
        </main>
    </body>
    </html>
    """


@router.get("/internal/conversations/{conversation_id}", response_class=HTMLResponse)
def conversation_detail(conversation_id: int, db: Session = Depends(get_db)) -> str:
    repository = AttendanceRepository(db)
    messages = repository.list_messages(conversation_id)
    message_rows = "\n".join(
        f"""
        <article class="message {message.direction}">
            <div class="meta">
                <strong>{escape(message.sender_type)}</strong>
                <span>{message.sent_at}</span>
            </div>
            <p>{escape(message.body)}</p>
        </article>
        """
        for message in messages
    )

    return f"""
    <!doctype html>
    <html lang="pt-BR">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Conversa #{conversation_id}</title>
        <style>
            body {{
                margin: 0;
                font-family: Arial, sans-serif;
                background: #f6f7f9;
                color: #1f2933;
            }}
            header {{
                background: #1f2933;
                color: white;
                padding: 22px 32px;
            }}
            main {{
                max-width: 860px;
                margin: 0 auto;
                padding: 28px 20px 48px;
            }}
            a {{
                color: #0f766e;
                font-weight: 700;
                text-decoration: none;
            }}
            .message {{
                background: white;
                border: 1px solid #dde2e8;
                margin-bottom: 12px;
                padding: 14px 16px;
            }}
            .message.outbound {{
                border-left: 5px solid #0f766e;
            }}
            .message.inbound {{
                border-left: 5px solid #334155;
            }}
            .meta {{
                display: flex;
                justify-content: space-between;
                gap: 16px;
                color: #607080;
                font-size: 13px;
                margin-bottom: 8px;
            }}
            p {{
                margin: 0;
                line-height: 1.5;
            }}
        </style>
    </head>
    <body>
        <header>
            <h1>Conversa #{conversation_id}</h1>
        </header>
        <main>
            <p><a href="/internal/dashboard">voltar ao painel</a></p>
            {message_rows or '<p>Nenhuma mensagem encontrada.</p>'}
        </main>
    </body>
    </html>
    """
