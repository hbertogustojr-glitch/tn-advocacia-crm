from app.services.evolution_service import EvolutionService


def test_extracts_document_message_metadata() -> None:
    payload = {
        "event": "messages.upsert",
        "instance": "escritorio",
        "data": {
            "key": {"fromMe": False, "remoteJid": "558299999999@s.whatsapp.net", "id": "ABC"},
            "pushName": "Cliente",
            "messageTimestamp": 1_700_000_000,
            "base64": "Y29udGV1ZG8=",
            "message": {
                "documentMessage": {
                    "mimetype": "application/pdf",
                    "fileName": "processo.pdf",
                    "caption": "Pode analisar?",
                }
            },
        },
    }

    message = EvolutionService().extract_text_messages(payload)[0]

    assert message.message_type == "document"
    assert message.media_filename == "processo.pdf"
    assert message.media_mimetype == "application/pdf"
    assert message.media_base64 == "Y29udGV1ZG8="
    assert message.message_text == "Pode analisar?"
