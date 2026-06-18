# Evolution API

## Objetivo

Usar o numero atual do WhatsApp Business via conexao tipo WhatsApp Web, sem migrar para a Meta Cloud API.

## Fluxo

```text
WhatsApp Business atual
        ↓
Evolution API
        ↓
FastAPI /webhooks/evolution/whatsapp
        ↓
Claude + banco
        ↓
FastAPI envia resposta pela Evolution API
        ↓
Cliente recebe no mesmo WhatsApp
```

## Subir localmente

Docker Desktop precisa estar aberto.

```bash
/Applications/Docker.app/Contents/Resources/bin/docker compose -f docker-compose.evolution.yml up -d
```

Evolution API:

```text
http://127.0.0.1:8080
```

API key local:

```text
SUA_CHAVE_LOCAL_FORTE
```

## Criar instancia

```bash
curl -X POST http://127.0.0.1:8080/instance/create \
  -H "Content-Type: application/json" \
  -H "apikey: SUA_CHAVE_LOCAL_FORTE" \
  --data '{
    "instanceName": "escritorio",
    "integration": "WHATSAPP-BAILEYS",
    "qrcode": true,
    "rejectCall": true,
    "msgCall": "No momento nao atendemos chamadas por este canal. Envie uma mensagem de texto.",
    "groupsIgnore": true,
    "alwaysOnline": false,
    "readMessages": false,
    "readStatus": false,
    "syncFullHistory": false
  }'
```

## Obter QR Code

```bash
curl http://127.0.0.1:8080/instance/connect/escritorio \
  -H "apikey: SUA_CHAVE_LOCAL_FORTE"
```

Escaneie com:

```text
WhatsApp Business > Aparelhos conectados > Conectar aparelho
```

## Webhook

O docker-compose ja configura o webhook global para:

```text
http://host.docker.internal:8000/webhooks/evolution/whatsapp
```

## Teste local sem WhatsApp

```bash
curl -X POST http://127.0.0.1:8000/webhooks/evolution/whatsapp \
  -H "Content-Type: application/json" \
  --data @samples/evolution-webhook-text.json
```

## Observacao importante

Essa abordagem usa conexao baseada em WhatsApp Web. Ela permite manter o numero atual e continuar usando o app, mas e menos oficial do que a Meta Cloud API e pode ter mais instabilidade.
