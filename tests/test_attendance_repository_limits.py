import unittest
from unittest.mock import Mock

from app.repositories.attendance_repository import AttendanceRepository


class AttendanceRepositoryLimitTests(unittest.TestCase):
    def test_ai_decision_reason_is_limited_to_database_capacity(self) -> None:
        db = Mock()
        repository = AttendanceRepository(db)

        decision = repository.create_ai_decision(
            conversation_id=1,
            inbound_message_id=1,
            action="handoff",
            confidence=0.9,
            reason="x" * 800,
            model_name="test",
        )

        self.assertEqual(len(decision.reason), 500)
        db.add.assert_called_once_with(decision)
        db.flush.assert_called_once_with()

    def test_handoff_reason_is_bounded_without_losing_normal_summaries(self) -> None:
        db = Mock()
        repository = AttendanceRepository(db)
        repository.get_conversation = Mock(return_value=None)

        handoff = repository.create_handoff(
            conversation_id=1,
            requested_by_message_id=1,
            reason="x" * 5000,
        )

        self.assertEqual(len(handoff.reason), 4000)
        db.add.assert_called_once_with(handoff)
        db.flush.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
