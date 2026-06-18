from app.services.conversation_subject_service import ConversationSubjectService


def test_subject_uses_legal_category_instead_of_raw_message() -> None:
    assert (
        ConversationSubjectService.from_message("Oi, preciso de ajuda com meu divórcio")
        == "Divórcio"
    )


def test_subject_keeps_greeting_generic_until_topic_arrives() -> None:
    assert ConversationSubjectService.from_message("Oi, tudo bem?") == "Atendimento inicial"


def test_subject_does_not_expose_cpf() -> None:
    subject = ConversationSubjectService.clean("CPF 123.456.789-00 para consulta")
    assert "123" not in subject


def test_subject_identifies_requested_lawyer() -> None:
    assert (
        ConversationSubjectService.from_message("Quero falar com o Thiago")
        == "Atendimento com Thiago"
    )


def test_short_document_term_does_not_match_inside_another_word() -> None:
    assert ConversationSubjectService.from_message("É urgente") == "É urgente"
