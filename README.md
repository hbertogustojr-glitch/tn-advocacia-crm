# Assistente WhatsApp para Escritório de Advocacia

Base estruturada para automatizar atendimento via WhatsApp usando n8n, FastAPI, MySQL e Claude.

## Objetivo

Responder automaticamente mensagens simples de clientes e encaminhar para atendimento humano quando houver risco jurídico, falta de informação, urgência, documento sensível ou assunto que precise de análise do escritório.

## Arquitetura

```text
WhatsApp Business / Provedor
        ↓
       n8n
        ↓
FastAPI
        ↓
Serviços de atendimento
        ↓
Claude + MySQL
        ↓
n8n envia resposta ou aciona humano
```

## Camadas do projeto

- `app/api`: endpoints HTTP usados pelo n8n e por integrações externas.
- `app/core`: configurações e regras globais.
- `app/db`: sessão e conexão com banco.
- `app/models`: modelos SQLAlchemy.
- `app/repositories`: acesso a dados.
- `app/services`: regras de negócio, IA e handoff humano.
- `app/schemas`: contratos de entrada e saída da API.
- `sql`: schema MySQL normalizado.
- `n8n`: guia do workflow.

## Banco de dados

O schema foi pensado com normalização:

- escritório separado de usuários, clientes, contatos e atendimentos;
- cliente pode ter mais de um contato;
- conversa é separada de mensagem;
- decisão da IA é auditável e não misturada no texto da mensagem;
- handoff humano tem status próprio;
- casos jurídicos são separados de conversas;
- base de conhecimento fica separada para alimentar o Claude com conteúdo aprovado.

## Fluxo principal

1. Cliente envia mensagem no WhatsApp.
2. n8n recebe webhook do provedor.
3. n8n chama `POST /webhooks/n8n/whatsapp`.
4. FastAPI identifica ou cria contato.
5. FastAPI salva mensagem recebida.
6. Serviço de atendimento consulta contexto.
7. Claude classifica e responde, ou pede handoff humano.
8. FastAPI salva decisão e resposta.
9. n8n envia mensagem pelo WhatsApp ou notifica humano.

## Rodando localmente

Crie um `.env` baseado em `.env.example`.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Teste local com Docker

Se tiver Docker Desktop instalado no Mac:

```bash
cp .env.example .env
docker compose up -d
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Em outro terminal:

```bash
curl -X POST http://127.0.0.1:8000/webhooks/n8n/whatsapp \
  -H "Content-Type: application/json" \
  --data @samples/whatsapp-inbound.json
```

## Endpoint principal

```http
POST /webhooks/n8n/whatsapp
```

Para integracao real com Meta WhatsApp Cloud API, use:

```http
GET /webhooks/meta/whatsapp
POST /webhooks/meta/whatsapp
```

Veja [docs/META_WHATSAPP.md](docs/META_WHATSAPP.md).

Para usar o numero atual via Evolution API/WhatsApp Web, veja:

```text
docs/EVOLUTION_API.md
```

Exemplo de payload:

```json
{
  "provider": "whatsapp_cloud_api",
  "organization_id": 1,
  "external_contact_id": "5511999999999",
  "phone_number": "5511999999999",
  "contact_name": "Maria Silva",
  "external_message_id": "wamid.example",
  "message_text": "Oi, queria saber o andamento do meu processo",
  "sent_at": "2026-06-15T10:00:00-03:00"
}
```

Resposta esperada:

```json
{
  "conversation_id": 10,
  "action": "reply",
  "reply_text": "Oi, Maria. Vou verificar as informações disponíveis aqui...",
  "handoff_reason": null
}
```

## Segurança para advocacia

Regras padrão:

- não dar orientação jurídica específica sem base aprovada;
- não inventar status de processo;
- não prometer prazos, resultados ou valores;
- encaminhar para humano quando houver urgência, risco, documento, prazo, cobrança complexa, reclamação, ameaça, audiência ou dúvida jurídica sensível;
- registrar histórico e decisão de IA para auditoria.
