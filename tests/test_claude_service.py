from app.services.claude_service import ClaudeService, LEGAL_SYSTEM_PROMPT


def test_new_client_fallback_uses_requested_welcome() -> None:
    reply = ClaudeService._fallback_reply(
        client_name="Joao",
        is_first_message=True,
        greeting="bom dia",
    )

    assert reply == (
        "Bom dia. Seja bem-vindo(a) à TNA advocacia. "
        "Me conta como posso te ajudar hoje."
    )


def test_regular_legal_topics_do_not_force_immediate_handoff() -> None:
    assert not ClaudeService._requires_handoff_by_keyword("Quero saber sobre rescisão indireta")
    assert not ClaudeService._requires_handoff_by_keyword("Tenho um processo e quero entender o valor")


def test_real_urgency_still_forces_immediate_handoff() -> None:
    assert ClaudeService._requires_handoff_by_keyword("Tenho uma audiência hoje")
    assert ClaudeService._requires_handoff_by_keyword("O prazo venceu ontem")


def test_prompt_prioritizes_orientation_and_minimal_questions() -> None:
    assert "de uma orientacao inicial util antes de fazer perguntas" in LEGAL_SYSTEM_PROMPT
    assert "Faca apenas UMA pergunta por mensagem" in LEGAL_SYSTEM_PROMPT
    assert "Nao peca CPF, RG, endereco completo" in LEGAL_SYSTEM_PROMPT
    assert "nao diga que um contrato ja foi fechado" in LEGAL_SYSTEM_PROMPT


def test_prompt_identifies_related_rights_and_judicial_paths() -> None:
    normalized_prompt = " ".join(LEGAL_SYSTEM_PROMPT.split())

    assert "outros direitos" in normalized_prompt
    assert "podem ser cobrados judicialmente" in normalized_prompt
    assert "fundamentar um pedido de rescisao indireta" in normalized_prompt
    assert 'resolvido "administrativamente"' in normalized_prompt
