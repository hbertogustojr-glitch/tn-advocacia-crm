from dataclasses import dataclass


@dataclass(frozen=True)
class RoutingRuleResult:
    action: str
    reason: str
    reply_text: str | None = None
    assigned_human_name: str | None = None


class RoutingRules:
    HUMAN_NAMES = {
        "camilla": "Camilla",
        "thiago": "Thiago",
    }

    LEGAL_SENSITIVE_TERMS = [
        "processo",
        "prazo",
        "audiencia",
        "audiência",
        "liminar",
        "sentenca",
        "sentença",
        "recurso",
        "acordo",
        "honorario",
        "honorário",
        "indenizacao",
        "indenização",
        "estrategia",
        "estratégia",
        "chance de ganhar",
        "valor da causa",
        "decisao",
        "decisão",
    ]

    DOCUMENT_TERMS = [
        "documento",
        "documentacao",
        "documentação",
        "rg",
        "cpf",
        "comprovante",
        "certidao",
        "certidão",
    ]

    CLOSING_TERMS = [
        "obrigado",
        "obrigada",
        "muito obrigado",
        "muito obrigada",
        "ok obrigado",
        "ok obrigada",
        "ta bom obrigado",
        "ta bom obrigada",
        "tá bom obrigado",
        "tá bom obrigada",
        "valeu",
        "beleza",
        "era isso",
        "só isso",
        "so isso",
        "não preciso de mais nada",
        "nao preciso de mais nada",
        "não, obrigado",
        "nao, obrigado",
        "não, obrigada",
        "nao, obrigada",
        "tudo certo",
        "deu certo",
        "tchau",
        "ate mais",
        "até mais",
        "ate logo",
        "até logo",
    ]

    @classmethod
    def classify(cls, message_text: str) -> RoutingRuleResult | None:
        normalized = message_text.lower()

        selected_human = cls._selected_human(normalized)
        if selected_human:
            return RoutingRuleResult(
                action="handoff",
                reason=f"Cliente solicitou encaminhamento para {selected_human}.",
                assigned_human_name=selected_human,
            )

        if any(term in normalized for term in cls.LEGAL_SENSITIVE_TERMS):
            return RoutingRuleResult(
                action="handoff",
                reason="Mensagem envolve assunto juridico especifico e deve ser tratada por humano.",
            )

        return None

    @classmethod
    def _selected_human(cls, normalized_message: str) -> str | None:
        for key, display_name in cls.HUMAN_NAMES.items():
            if key in normalized_message:
                return display_name
        return None

    @classmethod
    def mentions_documents(cls, message_text: str) -> bool:
        normalized = message_text.lower()
        return any(term in normalized for term in cls.DOCUMENT_TERMS)

    @classmethod
    def is_closing_message(cls, message_text: str) -> bool:
        normalized = message_text.lower().strip()
        return any(term in normalized for term in cls.CLOSING_TERMS)
