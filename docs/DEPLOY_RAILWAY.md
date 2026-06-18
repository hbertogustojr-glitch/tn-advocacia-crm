# Publicacao no Railway

O projeto usa dois servicos no mesmo projeto Railway:

- `app`: FastAPI construida pelo `Dockerfile`;
- `MySQL`: banco criado pelo template oficial do Railway.

## 1. Criar o projeto

1. Entre no Railway usando a conta GitHub do proprietario do sistema.
2. Crie um projeto a partir do repositorio privado `tn-advocacia-crm`.
3. Adicione um banco pelo menu `New` e escolha `MySQL`.

## 2. Variaveis da API

Cadastre no servico `app`:

```env
APP_ENV=production
OFFICE_NAME=TN Advocacia
LOCAL_TIMEZONE=America/Maceio
DATABASE_URL=${{MySQL.MYSQL_URL}}
ANTHROPIC_API_KEY=CHAVE_NOVA_DO_CLAUDE
CLAUDE_MODEL=claude-sonnet-4-6
DEFAULT_ORGANIZATION_ID=1
AI_TEMPERATURE=0.2
AUTO_REPLY_ENABLED=true
FOLLOW_UP_ENABLED=true
FOLLOW_UP_DELAY_HOURS=1
CRM_SESSION_SECRET=SEGREDO_ALEATORIO
CRM_SELF_REGISTRATION_ENABLED=false
CRM_ADMIN_EMAIL=EMAIL_DO_ADMINISTRADOR
CRM_ADMIN_PASSWORD=SENHA_FORTE_DO_ADMINISTRADOR
CRM_SEED_DEMO_USERS=false
META_GRAPH_API_VERSION=v23.0
META_WHATSAPP_VERIFY_TOKEN=TOKEN_ALEATORIO
META_WHATSAPP_ACCESS_TOKEN=
META_WHATSAPP_PHONE_NUMBER_ID=
META_SEND_HANDOFF_ACK=true
EVOLUTION_ENABLED=false
```

Gere `CRM_SESSION_SECRET` e `META_WHATSAPP_VERIFY_TOKEN` separadamente com:

```bash
openssl rand -hex 32
```

## 3. Dominio e HTTPS

Gere primeiro um dominio publico do Railway no servico `app`. Depois adicione o
subdominio definitivo nas configuracoes de rede, por exemplo:

```text
crm.tnadvocacia.com
```

O Railway informa o registro DNS que deve ser criado e gerencia o certificado HTTPS.

## 4. Atualizacoes

Cada envio para a branch principal do GitHub inicia um deploy automatico. O arquivo
`railway.toml` executa a inicializacao do banco antes de publicar e verifica `/health`
antes de trocar a versao ativa.

Antes de atualizar producao:

1. testar localmente;
2. executar backup do banco;
3. enviar a alteracao ao GitHub;
4. conferir o healthcheck e os logs do deploy.

## 5. Limite de gastos

Configure um alerta e um limite de uso no Railway. Se o limite rigido for atingido,
os servicos podem ficar offline; use o alerta como primeira protecao e acompanhe o
consumo da primeira semana.
