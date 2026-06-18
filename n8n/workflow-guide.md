# Guia do workflow n8n

## Nos principais

1. WhatsApp Trigger ou Webhook do provedor.
2. Set/Function para normalizar payload.
3. HTTP Request para FastAPI.
4. Switch usando `action`.
5. Se `reply`, enviar mensagem no WhatsApp.
6. Se `handoff`, notificar humano e marcar atendimento manual.

## Workflow de teste pronto

Importe o arquivo:

```text
n8n/legal-whatsapp-test-workflow.json
```

Ele cria um webhook local em:

```text
http://127.0.0.1:5678/webhook-test/legal-whatsapp-test
```

Enquanto estiver testando pelo editor do n8n, clique em **Listen for test event** no node do webhook antes de mandar o `curl`.

Teste simples:

```bash
curl -X POST http://127.0.0.1:5678/webhook-test/legal-whatsapp-test \
  -H "Content-Type: application/json" \
  --data @samples/n8n-webhook-simple.json
```

Teste de handoff:

```bash
curl -X POST http://127.0.0.1:5678/webhook-test/legal-whatsapp-test \
  -H "Content-Type: application/json" \
  --data @samples/n8n-webhook-handoff.json
```

## Payload para FastAPI

```json
{
  "provider": "whatsapp_cloud_api",
  "organization_id": 1,
  "external_contact_id": "={{$json.contacts[0].wa_id}}",
  "phone_number": "={{$json.contacts[0].wa_id}}",
  "contact_name": "={{$json.contacts[0].profile.name}}",
  "external_message_id": "={{$json.messages[0].id}}",
  "message_text": "={{$json.messages[0].text.body}}",
  "sent_at": "={{new Date(Number($json.messages[0].timestamp) * 1000).toISOString()}}"
}
```

## Resposta do FastAPI

```json
{
  "conversation_id": 1,
  "action": "reply",
  "reply_text": "Mensagem pronta para enviar",
  "handoff_reason": null
}
```

## Switch no n8n

- `action == reply`: enviar `reply_text` no WhatsApp.
- `action == handoff`: criar alerta para humano e enviar mensagem de acolhimento, se o escritório aprovar.
- `action == ignore`: não responder automaticamente.

## Mensagem sugerida no handoff

```text
Recebemos sua mensagem. Para garantir uma resposta correta e segura, vou encaminhar seu atendimento para uma pessoa do escritório.
```
