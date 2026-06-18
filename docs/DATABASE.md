# Modelagem do banco

## Princípios

Este banco foi desenhado para não misturar conceitos que mudam por motivos diferentes.

- `organizations`: cada escritório ou operação atendida pela plataforma.
- `users`: pessoas do escritório que podem assumir conversas.
- `clients`: cadastro jurídico/comercial do cliente.
- `contacts`: canais de comunicação, como WhatsApp.
- `client_contacts`: relação N:N entre cliente e contato.
- `legal_matters`: casos, processos ou demandas vinculadas ao cliente.
- `conversations`: atendimento em um canal.
- `messages`: mensagens de entrada e saída.
- `ai_decisions`: trilha de auditoria da decisão da IA.
- `handoff_requests`: fila de transferência para humano.
- `knowledge_articles`: base aprovada para respostas automáticas.

## Normalização

### Primeira Forma Normal

Os campos armazenam valores atômicos. Telefones, documentos, status, mensagens e decisões ficam em colunas próprias. Uma conversa não guarda uma lista de mensagens dentro dela; mensagens ficam em `messages`.

### Segunda Forma Normal

Tabelas de relação, como `client_contacts`, descrevem somente a relação entre cliente e contato. Dados do cliente ficam em `clients`; dados do canal ficam em `contacts`.

### Terceira Forma Normal

Dados que dependem de outra entidade foram separados. O status do atendimento fica em `conversations`; a decisão da IA fica em `ai_decisions`; o pedido de humano fica em `handoff_requests`. Assim, mudar uma decisão ou resolver um handoff não exige alterar o texto original da mensagem.

## Por que separar cliente de contato?

No WhatsApp, quem escreve pode ser:

- o próprio cliente;
- parente do cliente;
- funcionário de uma empresa cliente;
- alguém perguntando antes de virar cliente.

Por isso `contacts` identifica o canal e `clients` identifica o cadastro jurídico. A tabela `client_contacts` liga os dois quando essa relação for confirmada.

## Por que separar conversa de caso jurídico?

Uma conversa pode começar genérica e só depois ser vinculada a um processo. Também pode haver várias conversas sobre o mesmo caso. A coluna `legal_matter_id` em `conversations` é opcional por esse motivo.

## Auditoria da IA

Cada mensagem recebida pode gerar uma linha em `ai_decisions`. Isso permite responder perguntas como:

- por que a IA respondeu sozinha?
- por que transferiu para humano?
- qual modelo foi usado?
- qual era a confiança?
- qual prompt estava em produção?

Para escritório de advocacia, essa trilha é essencial.

