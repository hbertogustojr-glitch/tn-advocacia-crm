import re


class ConversationSubjectService:
    @staticmethod
    def clean(subject: str | None) -> str:
        cleaned = re.sub(r"\s+", " ", subject or "").strip(" \t\r\n\"'.,:;!?")
        cleaned = re.sub(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b", "", cleaned)
        cleaned = re.sub(r"\b\d{8,}\b", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -–—.,:;")
        if not cleaned:
            return "Atendimento inicial"
        cleaned = cleaned[:120].rstrip()
        return cleaned[0].upper() + cleaned[1:]

    @classmethod
    def from_message(cls, message_text: str) -> str:
        normalized = re.sub(r"\s+", " ", message_text).strip()
        lowered = normalized.lower()
        categories = [
            (("thiago",), "Atendimento com Thiago"),
            (("camilla",), "Atendimento com Camilla"),
            (("divorcio", "divórcio"), "Divórcio"),
            (("trabalhista", "trabalho", "demissao", "demissão"), "Questão trabalhista"),
            (("previdenciario", "previdenciário", "inss", "aposentadoria"), "Questão previdenciária"),
            (("processo", "sentenca", "sentença", "recurso"), "Informações sobre processo"),
            (("audiencia", "audiência"), "Audiência"),
            (("contrato",), "Análise de contrato"),
            (("honorario", "honorário", "valor", "preco", "preço"), "Honorários e valores"),
            (("acordo",), "Proposta de acordo"),
            (("documento", "documentacao", "documentação", "comprovante"), "Envio de documentos"),
            (("cpf", "rg"), "Identificação do cliente"),
            (("agendar", "agendamento", "consulta"), "Agendamento de consulta"),
        ]
        for terms, title in categories:
            if any(
                re.search(rf"(?<!\w){re.escape(term)}(?!\w)", lowered)
                for term in terms
            ):
                return title

        without_greeting = re.sub(
            r"^(?:(?:oi|ol[aá]|bom dia|boa tarde|boa noite|tudo bem)[!,.? ]*)+",
            "",
            normalized,
            flags=re.IGNORECASE,
        ).strip()
        if not without_greeting:
            return "Atendimento inicial"
        words = without_greeting.split()
        return cls.clean(" ".join(words[:8]))
