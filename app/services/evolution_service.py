from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import settings
from app.schemas.evolution import EvolutionInboundMessage


class EvolutionService:
    def extract_text_messages(self, payload: dict[str, Any]) -> list[EvolutionInboundMessage]:
        event_name = str(payload.get("event") or "").lower()
        if event_name and "messages" not in event_name:
            return []
        message = self._extract_single(payload)
        return [message] if message else []

    def send_text_message(self, to_phone_number: str, text: str) -> str:
        if not settings.evolution_api_key:
            raise RuntimeError("Evolution API key is not configured.")

        url = f"{settings.evolution_api_url.rstrip('/')}/message/sendText/{settings.evolution_instance_name}"
        headers = {
            "apikey": settings.evolution_api_key,
            "Content-Type": "application/json",
        }
        body = {
            "number": to_phone_number,
            "text": text,
            "delay": 800,
            "linkPreview": False,
        }
        with httpx.Client(timeout=20) as client:
            response = client.post(url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
        return data.get("key", {}).get("id", "")

    def get_media_base64(self, message_id: str) -> str | None:
        """Fetch media when the instance webhook was not configured with base64."""
        if not settings.evolution_api_key:
            return None
        url = (
            f"{settings.evolution_api_url.rstrip('/')}"
            f"/chat/getBase64FromMediaMessage/{settings.evolution_instance_name}"
        )
        headers = {"apikey": settings.evolution_api_key, "Content-Type": "application/json"}
        with httpx.Client(timeout=40) as client:
            response = client.post(
                url,
                headers=headers,
                json={"message": {"key": {"id": message_id}}, "convertToMp4": False},
            )
            response.raise_for_status()
            data = response.json()
        if isinstance(data, dict):
            value = data.get("base64") or data.get("data")
            if isinstance(value, str):
                return value
        return None

    def handoff_ack_text(self) -> str:
        return (
            "Para garantir um atendimento correto e seguro, vou encaminhar sua mensagem "
            "para a pessoa responsavel do escritorio."
        )

    def _extract_single(self, payload: dict[str, Any]) -> EvolutionInboundMessage | None:
        data = payload.get("data") or payload
        if not isinstance(data, dict):
            return None
        key = data.get("key", {})
        if key.get("fromMe") is True:
            return None

        remote_jid = key.get("remoteJid") or data.get("remoteJid") or data.get("chatId")
        message_id = key.get("id") or data.get("id")
        text = self._extract_text(data)
        media = self._extract_media(data, payload)
        if not remote_jid or not message_id or (not text and not media):
            return None
        if str(remote_jid).endswith("@g.us"):
            return None

        phone_number = str(remote_jid).split("@")[0]
        timestamp = data.get("messageTimestamp") or payload.get("date_time")
        sent_at = self._parse_timestamp(timestamp)
        return EvolutionInboundMessage(
            instance=payload.get("instance"),
            phone_number=phone_number,
            contact_name=data.get("pushName") or data.get("senderName"),
            external_message_id=message_id,
            message_text=text or media["caption"] or "Arquivo enviado pelo cliente.",
            message_type=media["type"] if media else "text",
            media_mimetype=media["mimetype"] if media else None,
            media_filename=media["filename"] if media else None,
            media_base64=media["base64"] if media else None,
            sent_at=sent_at,
        )

    @staticmethod
    def _extract_media(data: dict[str, Any], payload: dict[str, Any]) -> dict[str, str | None] | None:
        message = data.get("message", {})
        candidates = (
            ("document", message.get("documentMessage")),
            ("image", message.get("imageMessage")),
        )
        for media_type, details in candidates:
            if not isinstance(details, dict):
                continue
            raw_base64 = data.get("base64") or payload.get("base64") or details.get("base64")
            return {
                "type": media_type,
                "mimetype": details.get("mimetype"),
                "filename": details.get("fileName") or details.get("filename"),
                "caption": details.get("caption"),
                "base64": raw_base64 if isinstance(raw_base64, str) else None,
            }
        return None

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str | None:
        message = data.get("message", {})
        if isinstance(message.get("conversation"), str):
            return message["conversation"]
        extended = message.get("extendedTextMessage", {})
        if isinstance(extended.get("text"), str):
            return extended["text"]
        if isinstance(data.get("text"), str):
            return data["text"]
        if isinstance(data.get("messageText"), str):
            return data["messageText"]
        return None

    @staticmethod
    def _parse_timestamp(raw_timestamp: Any) -> datetime:
        if isinstance(raw_timestamp, int):
            return datetime.fromtimestamp(raw_timestamp, tz=timezone.utc)
        if isinstance(raw_timestamp, str):
            if raw_timestamp.isdigit():
                return datetime.fromtimestamp(int(raw_timestamp), tz=timezone.utc)
            try:
                return datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
            except ValueError:
                pass
        return datetime.now(timezone.utc)
