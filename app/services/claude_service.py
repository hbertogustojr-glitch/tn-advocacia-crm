import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from anthropic import Anthropic, AnthropicError

from app.core.config import settings
from app.schemas.whatsapp import AiRoutingDecision
from app.services.conversation_subject_service import ConversationSubjectService


LEGAL_SYSTEM_PROMPT = """
Voce e o assistente virtual do escritorio de advocacia TN Advocacia.
Seu papel e analisar mensagens de clientes no WhatsApp, responder quando possivel,
escalar para o advogado quando necessario, e gerenciar encerramento e retomada
de conversas de forma natural e profissional.

Contexto fixo do escritorio:
- Nome do escritorio: TN Advocacia.
- Atendimento em horario comercial.
- Atendimento em todo o Brasil.
- Responsaveis humanos disponiveis: Camilla e Thiago.

Regras de saudacao:
- Use "bom dia", "boa tarde" ou "boa noite" conforme informado no contexto.
- Mencione "TN Advocacia" somente na primeira mensagem da conversa.
- Diga "seja bem-vindo" somente na primeira mensagem da conversa.
- Em mensagens seguintes, responda direto e nao repita saudacao de boas-vindas.

Responda voce mesmo quando:
- For duvida simples ou informacao geral sobre o escritorio.
- O cliente quiser agendar uma consulta.
- For confirmacao, saudacao ou retomada de conversa apos periodo inativo.
- For coleta de dados iniciais.
- A resposta estiver disponivel no contexto do CRM.

Para novo atendimento, quando fizer sentido, colete aos poucos:
nome completo, estado civil, nome da mae, RG, CPF e endereco completo.

Escale para o advogado quando:
- Envolver decisao ou orientacao juridica especifica.
- O cliente mencionar urgencia real, como audiencia hoje, pessoa presa ou prazo vencendo.
- For negociacao, proposta, valores, honorarios ou acordo.
- A mensagem for sensivel, como reclamacao seria, ameaca ou situacao emocional.
- O cliente repetiu a mesma duvida 2 vezes e voce nao conseguiu resolver.
- Voce nao tiver certeza absoluta sobre a resposta.
- O cliente pedir informacoes de processo que nao estejam claramente no contexto do CRM.

Regras de encerramento:
- Encerre a conversa quando o cliente se despedir explicitamente, como "obrigado, ate logo",
  "ok entendido", "tchau" ou frases equivalentes.
- Encerre quando o assunto foi resolvido.
- Se escalar para o advogado, marque o status como "aguardando_advogado".
- Apos escalar, o humano assume.
- Ao encerrar, nao force despedidas formais nem pergunte "posso ajudar em mais alguma coisa?".
- Se resolveu, confirme brevemente. Exemplo: "Perfeito, Joao! Qualquer duvida e so chamar."
- Se escalou, informe de forma curta que o atendimento sera encaminhado.

Regras de retomada:
- Se o cliente mandar nova mensagem apos conversa encerrada, trate como nova conversa,
  cumprimente e use o contexto do CRM.
- Se houver contexto anterior relevante no CRM, use e nao peca informacoes repetidas.
- Nao mencione que a conversa havia encerrado; continue naturalmente.

Tom e formato:
- Tom profissional, cordial e direto, como um assistente humano de um escritorio serio.
- Chame o cliente pelo primeiro nome sempre que souber.
- Respostas curtas e objetivas, adequadas para WhatsApp.
- Nunca use emojis.
- Nunca invente informacoes juridicas.
- Nunca prometa prazos nao confirmados.
- Se precisar de mais informacao, faca apenas UMA pergunta por vez.

Responda SEMPRE em JSON valido, sem markdown e sem texto fora do JSON.

Schema obrigatorio:
{
  "acao": "responder",
  "mensagem": "texto da resposta para o cliente",
  "assunto_conversa": "titulo curto de 3 a 8 palavras",
  "status_conversa": "ativa",
  "motivo_escalonamento": null,
  "resumo_para_advogado": null
}

Se precisar encaminhar para humano, use:
{
  "acao": "escalar",
  "mensagem": null,
  "assunto_conversa": "titulo curto de 3 a 8 palavras",
  "status_conversa": "aguardando_advogado",
  "motivo_escalonamento": "motivo resumido",
  "resumo_para_advogado": "contexto completo para o advogado agir"
}

Se precisar encerrar sem advogado, use:
{
  "acao": "encerrar",
  "mensagem": "texto curto para encerrar a conversa",
  "assunto_conversa": "titulo curto de 3 a 8 palavras",
  "status_conversa": "encerrada",
  "motivo_escalonamento": null,
  "resumo_para_advogado": null
}

Regras para assunto_conversa:
- Resuma o tema principal em 3 a 8 palavras, por exemplo "Divorcio consensual".
- Nao use saudacoes como assunto.
- Nunca inclua CPF, RG, telefone, endereco, numero de processo ou outro dado sensivel.
- Se ainda nao houver tema alem de uma saudacao, use "Atendimento inicial".
"""


class ClaudeService:
    def __init__(self) -> None:
        self.client = Anthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None

    def decide_response(
        self,
        client_name: str | None,
        message_text: str,
        is_first_message: bool,
        greeting: str,
        crm_status: str = "desconhecido",
        active_processes: str = "Nenhum processo informado no CRM.",
        recent_history: str = "Sem historico recente.",
        conversation_status: str = "ativa",
        last_interaction: str = "Sem ultima interacao registrada.",
    ) -> AiRoutingDecision:
        if self._requires_handoff_by_keyword(message_text):
            return AiRoutingDecision(
                action="handoff",
                handoff_reason="Mensagem contem sinal de urgencia, risco ou tema juridico sensivel.",
                lawyer_summary=(
                    f"Cliente: {client_name or 'nao identificado'}. "
                    f"Status CRM: {crm_status}. Mensagem: {message_text}"
                ),
                conversation_status="waiting_human",
                conversation_subject=ConversationSubjectService.from_message(message_text),
                confidence=0.9,
            )

        if not self.client:
            return AiRoutingDecision(
                action="reply",
                reply_text=self._fallback_reply(client_name, is_first_message, greeting),
                conversation_subject=ConversationSubjectService.from_message(message_text),
                confidence=0.55,
            )

        try:
            response = self.client.messages.create(
                model=settings.claude_model,
                max_tokens=500,
                temperature=settings.ai_temperature,
                system=LEGAL_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Cliente: {client_name or 'nao identificado'}\n"
                            f"Status no CRM: {crm_status}\n"
                            f"Processos ativos no CRM: {active_processes}\n"
                            f"Historico recente da conversa:\n{recent_history}\n\n"
                            f"Status da conversa: {conversation_status}\n"
                            f"Ultima interacao: {last_interaction}\n"
                            f"Mensagem: {message_text}\n"
                            f"Primeira mensagem da conversa: {'sim' if is_first_message else 'nao'}\n"
                            f"Saudacao adequada para o horario: {greeting}\n"
                            f"Nome do escritorio: {settings.office_name}"
                        ),
                    }
                ],
            )
        except AnthropicError:
            return AiRoutingDecision(
                action="handoff",
                handoff_reason="Falha ao consultar o Claude. Atendimento encaminhado para humano.",
                conversation_subject=ConversationSubjectService.from_message(message_text),
                confidence=0.5,
            )

        raw_text = response.content[0].text
        try:
            data = json.loads(self._extract_json_object(raw_text))
            decision = self._parse_decision(data)
            decision.conversation_subject = ConversationSubjectService.clean(
                decision.conversation_subject
                or ConversationSubjectService.from_message(message_text)
            )
            if decision.reply_text:
                decision.reply_text = self.clean_reply_text(
                    decision.reply_text,
                    is_first_message=is_first_message,
                )
            return decision
        except (json.JSONDecodeError, ValueError):
            return AiRoutingDecision(
                action="handoff",
                handoff_reason="Claude retornou uma resposta fora do formato esperado.",
                lawyer_summary=f"Mensagem do cliente: {message_text}",
                conversation_subject=ConversationSubjectService.from_message(message_text),
                confidence=0.6,
            )

    @staticmethod
    def _parse_decision(data: dict) -> AiRoutingDecision:
        if "acao" in data:
            action_map = {
                "responder": "reply",
                "escalar": "handoff",
                "encerrar": "close",
            }
            status_map = {
                "ativa": "active",
                "encerrada": "closed",
                "aguardando_advogado": "waiting_human",
            }
            action = action_map.get(data.get("acao"), "handoff")
            return AiRoutingDecision(
                action=action,
                reply_text=data.get("mensagem"),
                handoff_reason=data.get("motivo_escalonamento"),
                lawyer_summary=data.get("resumo_para_advogado"),
                conversation_subject=data.get("assunto_conversa"),
                conversation_status=status_map.get(data.get("status_conversa"), "active"),
                confidence=0.85,
            )
        return AiRoutingDecision(**data)

    @staticmethod
    def _requires_handoff_by_keyword(message_text: str) -> bool:
        risky_terms = [
            "audiencia",
            "audiência",
            "prazo",
            "urgente",
            "liminar",
            "sentenca",
            "sentença",
            "recurso",
            "processo",
            "contrato",
            "valor",
            "honorario",
            "honorário",
            "indenizacao",
            "indenização",
            "acordo",
            "chance de ganhar",
            "estrategia",
            "estratégia",
        ]
        normalized = message_text.lower()
        return any(term in normalized for term in risky_terms)

    @staticmethod
    def _fallback_reply(
        client_name: str | None,
        is_first_message: bool,
        greeting: str,
    ) -> str:
        if is_first_message:
            name_part = f", {client_name}" if client_name else ""
            return (
                f"{greeting.capitalize()}{name_part}. Seja bem-vindo(a) à {settings.office_name}. "
                "Como podemos ajudar?"
            )
        return (
            "Recebi sua mensagem. Para manter seu atendimento seguro, "
            "vou registrar e encaminhar quando for necessario."
        )

    @staticmethod
    def clean_reply_text(reply_text: str, is_first_message: bool) -> str:
        cleaned = reply_text.strip()
        cleaned = re.sub(r"\ba TN Advocacia\b", "à TN Advocacia", cleaned)
        if not is_first_message:
            cleaned = re.sub(
                r"^(bom dia|boa tarde|boa noite|ol[aá]|oi)[!,. ]+",
                "",
                cleaned,
                flags=re.IGNORECASE,
            ).strip()
            cleaned = re.sub(
                r"^seja bem-vind[oa]\s*(?:\(a\))?\s*(?:à|a|ao)?\s*TN Advocacia[!,. ]*",
                "",
                cleaned,
                flags=re.IGNORECASE,
            ).strip()
        cleaned = re.sub(
            r"das\s+\d{1,2}h(?:\s*(?:às|as|-)\s*\d{1,2}h)?",
            "em horario comercial",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"de\s+segunda\s+a\s+sexta-feira,\s*em horario comercial",
            "em horario comercial",
            cleaned,
            flags=re.IGNORECASE,
        )
        return cleaned

    @staticmethod
    def greeting_for_now() -> str:
        local_now = datetime.now(ZoneInfo(settings.local_timezone))
        if 5 <= local_now.hour < 12:
            return "bom dia"
        if 12 <= local_now.hour < 18:
            return "boa tarde"
        return "boa noite"

    @staticmethod
    def _extract_json_object(raw_text: str) -> str:
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return raw_text
        return raw_text[start : end + 1]
