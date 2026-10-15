import unittest

from schedule_monitor import ScheduleMonitor


class FakeBot:
    def __init__(self):
        self.messages = []

    def send_message(self, chat_id, text, **kwargs):
        self.messages.append((chat_id, text, kwargs))


class FakeScheduleService:
    def __init__(self, payloads):
        self.payloads = iter(payloads)

    def get_payload(self):
        return next(self.payloads)


class ScheduleMonitorRefreshTests(unittest.TestCase):
    def test_immediate_refresh_notifies_before_returning_changed_schedule(self):
        initial_payload = {
            "today_signature": "old",
            "tomorrow_signature": "tomorrow",
            "telegram_text": "Старий графік",
        }
        changed_payload = {
            "today_signature": "new",
            "tomorrow_signature": "tomorrow",
            "telegram_text": "Новий графік",
        }
        bot = FakeBot()
        monitor = ScheduleMonitor(
            bot=bot,
            chat_id="chat",
            service=FakeScheduleService([initial_payload, changed_payload]),
        )

        monitor.refresh_now()
        result = monitor.refresh_now()

        self.assertEqual(result, changed_payload)
        self.assertEqual(len(bot.messages), 1)
        self.assertEqual(bot.messages[0][0], "chat")
        self.assertIn("Графік змінився", bot.messages[0][1])
        self.assertIn("Новий графік", bot.messages[0][1])
        self.assertEqual(monitor.get_cached_text().splitlines()[0], "Новий графік")

    def test_unchanged_immediate_refresh_does_not_send_message(self):
        payload = {
            "today_signature": "same",
            "tomorrow_signature": "tomorrow",
            "telegram_text": "Поточний графік",
        }
        bot = FakeBot()
        monitor = ScheduleMonitor(
            bot=bot,
            chat_id="chat",
            service=FakeScheduleService([payload, payload]),
        )

        monitor.refresh_now()
        monitor.refresh_now()

        self.assertEqual(bot.messages, [])


if __name__ == "__main__":
    unittest.main()
