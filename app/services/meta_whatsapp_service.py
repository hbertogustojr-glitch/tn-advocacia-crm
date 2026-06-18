from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import settings
from app.schemas.meta import MetaInboundMessage


class MetaWhatsAppService:
    def verify_webhook(
        self,
        mode: str | None,
        token: str | None,
        challenge: str | None,
    ) -> str | None:
        if mode == "subscribe" and token == settings.meta_whatsapp_verify_token:
            return challenge
        return None

    def extract_text_messages(self, payload: dict[str, Any]) -> list[MetaInboundMessage]:
        extracted: list[MetaInboundMessage] = []
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                contacts_by_wa_id = {
                    contact.get("wa_id"): contact.get("profile", {}).get("name")
                    for contact in value.get("contacts", [])
                }
                for message in value.get("messages", []):
                    if message.get("type") != "text":
                        continue
                    phone_number = message.get("from")
                    message_id = message.get("id")
                    text = message.get("text", {}).get("body")
                    timestamp = message.get("timestamp")
                    if not phone_number or not message_id or not text or not timestamp:
                        continue
                    extracted.append(
                        MetaInboundMessage(
                            external_contact_id=phone_number,
                            phone_number=phone_number,
                            contact_name=contacts_by_wa_id.get(phone_number),
                            external_message_id=message_id,
                            message_text=text,
                            sent_at_unix=int(timestamp),
                        )
                    )
        return extracted

    def to_datetime(self, sent_at_unix: int) -> datetime:
        return datetime.fromtimestamp(sent_at_unix, tz=timezone.utc)

    def send_text_message(self, to_phone_number: str, text: str) -> str:
        if not settings.meta_whatsapp_access_token or not settings.meta_whatsapp_phone_number_id:
            raise RuntimeError("Meta WhatsApp credentials are not configured.")

        url = (
            f"https://graph.facebook.com/{settings.meta_graph_api_version}/"
            f"{settings.meta_whatsapp_phone_number_id}/messages"
        )
        headers = {
            "Authorization": f"Bearer {settings.meta_whatsapp_access_token}",
            "Content-Type": "application/json",
        }
        body = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone_number,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
        with httpx.Client(timeout=15) as client:
            response = client.post(url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
        messages = data.get("messages", [])
        if not messages:
            raise RuntimeError("Meta did not return a sent message id.")
        return messages[0].get("id", "")

    def handoff_ack_text(self) -> str:
        return (
            "Recebemos sua mensagem. Para garantir uma resposta correta e segura, "
            "vamos encaminhar seu atendimento para uma pessoa do escritorio."
        )

