# Meta WhatsApp Cloud API

## Objetivo

Este projeto tem endpoints compatíveis com a WhatsApp Business Platform da Meta.

## Endpoints do projeto

Verificação do webhook:

```text
GET /webhooks/meta/whatsapp
```

Recebimento de mensagens:

```text
POST /webhooks/meta/whatsapp
```

## Variáveis necessárias

No `.env`:

```env
META_GRAPH_API_VERSION=v23.0
META_WHATSAPP_VERIFY_TOKEN=um_token_forte_criado_por_voce
META_WHATSAPP_ACCESS_TOKEN=token_da_meta
META_WHATSAPP_PHONE_NUMBER_ID=id_do_numero_do_whatsapp
META_SEND_HANDOFF_ACK=true
```

## O que configurar na Meta

1. Criar ou acessar uma conta no Meta for Developers.
2. Criar um app com produto WhatsApp.
3. Vincular ou criar uma Meta Business Account.
4. Obter o `Phone Number ID`.
5. Criar um token permanente com System User para producao.
6. Configurar o webhook apontando para:

```text
https://SEU-DOMINIO.com/webhooks/meta/whatsapp
```

7. Usar no campo Verify Token o mesmo valor de:

```env
META_WHATSAPP_VERIFY_TOKEN
```

8. Assinar o evento:

```text
messages
```

## Teste local de verificacao

```bash
curl "http://127.0.0.1:8000/webhooks/meta/whatsapp?hub.mode=subscribe&hub.verify_token=local_verify_token_123&hub.challenge=abc123"
```

Resposta esperada:

```text
abc123
```

## Teste local de recebimento

Este teste processa a mensagem e chama o Claude. Se as credenciais da Meta ainda nao estiverem configuradas, o envio real para WhatsApp vai falhar e aparecer em `errors`, mas a conversa sera salva.

```bash
curl -X POST http://127.0.0.1:8000/webhooks/meta/whatsapp \
  -H "Content-Type: application/json" \
  --data @samples/meta-webhook-text.json
```

## Como fica o fluxo real

```text
Cliente manda WhatsApp
        ↓
Meta Cloud API
        ↓
FastAPI /webhooks/meta/whatsapp
        ↓
Banco + Claude
        ↓
FastAPI envia resposta pela Meta
        ↓
Cliente recebe WhatsApp
```

## Papel do n8n no projeto real

O n8n pode continuar no projeto para:

- avisar humano no Telegram, email ou Slack;
- criar tarefa em CRM;
- registrar planilha;
- gerar relatórios;
- disparar follow-up.

Mas o webhook oficial da Meta e o envio da resposta ficam no backend.

## Follow-up automatico

Quando o cliente indicar que vai enviar documentacao depois, conversar com alguem ou decidir depois, o backend agenda um follow-up.

Exemplos de frases que agendam retorno:

```text
vou falar com meu marido
vou falar com minha esposa
vou pensar
te retorno
respondo depois
```

O n8n deve chamar periodicamente:

```http
POST /internal/followups/process
```

Sugestao: um workflow com Cron a cada 1 hora chamando:

```text
https://SEU-DOMINIO.com/internal/followups/process
```

Para consultar os follow-ups:

```http
GET /internal/followups
```
