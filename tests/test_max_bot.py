import unittest

from app.interfaces.max_bot import MaxBotClient, parse_max_update


class MaxBotTest(unittest.TestCase):
    def test_parses_message_created(self) -> None:
        incoming = parse_max_update(
            {
                "update_type": "message_created",
                "message": {
                    "sender": {"user_id": 42},
                    "recipient": {"chat_id": 77},
                    "body": {"mid": "m1", "text": "Какие специальности?"},
                },
            }
        )
        self.assertIsNotNone(incoming)
        self.assertEqual(incoming.user_id, "42")
        self.assertEqual(incoming.chat_id, "77")
        self.assertEqual(incoming.event_id, "m1")

    def test_keyboard_uses_callback_payloads(self) -> None:
        attachment = MaxBotClient._keyboard(
            [{"label": "Специальности", "action": "kait_specialties"}]
        )
        button = attachment[0]["payload"]["buttons"][0][0]
        self.assertEqual(button["type"], "callback")
        self.assertEqual(button["payload"], "kait_specialties")

    def test_parses_callback_with_nested_message(self) -> None:
        incoming = parse_max_update(
            {
                "update_type": "message_callback",
                "callback": {
                    "callback_id": "cb1",
                    "payload": "kait_contacts",
                    "user": {"user_id": 42},
                    "message": {"recipient": {"chat_id": 77}},
                },
            }
        )
        self.assertIsNotNone(incoming)
        self.assertEqual(incoming.chat_id, "77")
        self.assertEqual(incoming.action, "kait_contacts")

    def test_long_text_is_split_under_platform_limit(self) -> None:
        chunks = MaxBotClient._split_text("слово " * 1500)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 4000 for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
