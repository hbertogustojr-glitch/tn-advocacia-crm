import unittest

from app.services.followup_service import FollowUpService


class FollowUpReasonTests(unittest.TestCase):
    def test_recognizes_document_commitment_variations(self) -> None:
        messages = [
            "Vou separar e enviar os documentos depois.",
            "Vou providenciar a documentacao.",
            "Mando os documentos mais tarde.",
            "Envio o RG depois.",
        ]

        for message in messages:
            with self.subTest(message=message):
                self.assertEqual(
                    FollowUpService._followup_reason(message),
                    "Cliente ficou de enviar documentacao solicitada.",
                )

    def test_does_not_schedule_for_document_question(self) -> None:
        self.assertIsNone(
            FollowUpService._followup_reason("Quais documentos preciso enviar?"),
        )


if __name__ == "__main__":
    unittest.main()
