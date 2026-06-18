# Publicacao na HostGator VPS

Este roteiro considera uma VPS Linux com acesso root por SSH. Hospedagem compartilhada
ou apenas registro de dominio nao sao suficientes para executar esta arquitetura.

## Dados necessarios

- nome exato do plano HostGator;
- endereco IP da VPS;
- acesso SSH da VPS;
- acesso ao DNS do dominio;
- subdominio escolhido, por exemplo `crm.tnadvocacia.com`;
- nova chave da API Anthropic;
- credenciais permanentes da Meta, quando o WhatsApp oficial for conectado.

Nunca envie senhas, chaves ou tokens por mensagem. Cadastre esses valores diretamente
no arquivo `.env.production` dentro da VPS.

## 1. Instalar Docker na VPS

Entre por SSH e instale Docker Engine e o plugin Docker Compose conforme a documentacao
oficial do Docker para a distribuicao Linux instalada na VPS.

Confirme a instalacao:

```bash
docker --version
docker compose version
```

## 2. Enviar o projeto

Mantenha o codigo em um repositorio GitHub privado e clone na VPS:

```bash
git clone URL_DO_REPOSITORIO legal-assistant
cd legal-assistant
```

## 3. Configurar os segredos

```bash
cp .env.production.example .env.production
chmod 600 .env.production
```

Gere os segredos no servidor:

```bash
openssl rand -hex 32
```

Edite `.env.production` e substitua todos os valores de exemplo. Use senhas
alfanumericas no MySQL para evitar a necessidade de codificacao na URL de conexao.

Em producao, mantenha obrigatoriamente:

```env
APP_ENV=production
CRM_SELF_REGISTRATION_ENABLED=false
CRM_SEED_DEMO_USERS=false
```

## 4. Configurar o dominio

No DNS, crie um registro `A` para o subdominio escolhido apontando para o IP da VPS.

Exemplo:

```text
Tipo: A
Nome: crm
Valor: IP_DA_VPS
```

As portas TCP 80 e 443 devem estar liberadas. O Caddy obtera e renovara o certificado
HTTPS automaticamente depois que o DNS estiver apontando corretamente.

## 5. Publicar

```bash
docker compose --env-file .env.production -f compose.production.yml up -d --build
```

Verifique os containers e os logs:

```bash
docker compose --env-file .env.production -f compose.production.yml ps
docker compose --env-file .env.production -f compose.production.yml logs --tail=100 app caddy
```

Teste:

```text
https://SEU_SUBDOMINIO/health
https://SEU_SUBDOMINIO/crm/login
```

## 6. Backup diario

O script conserva os ultimos 14 dias de backup local:

```bash
chmod +x scripts/backup_mysql.sh
./scripts/backup_mysql.sh
```

Agende no `cron` da VPS e copie os arquivos da pasta `backups` para outro provedor.
Um backup mantido somente na mesma VPS nao protege contra perda total do servidor.

## 7. Atualizacoes

```bash
git pull
docker compose --env-file .env.production -f compose.production.yml up -d --build
```

Antes de atualizar, execute um backup e confirme a saude da aplicacao depois da subida.
