import unittest

from dtek_schedule import DtekScheduleService
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

    def test_day_rollover_only_notifies_for_actual_schedule_changes(self):
        service = DtekScheduleService("Забір", "Перемоги", "21")

        def payload(today_date, tomorrow_date=None, today_status="off"):
            schedule = [{
                "day": f"на сьогодні {today_date}",
                "slots": [{"hour": "00-01", "status": today_status}],
            }]
            if tomorrow_date is not None:
                schedule.append({
                    "day": f"на завтра {tomorrow_date}",
                    "slots": [{"hour": "00-01", "status": "off"}],
                })
            return {
                "schedule": schedule,
                "today_signature": service.make_day_signature(schedule[0]),
                "tomorrow_signature": service.make_day_signature(
                    schedule[1] if len(schedule) > 1 else None
                ),
                "telegram_text": service.build_schedule_text({"schedule": schedule}),
            }

        initial = payload("08.11.26", "09.11.26")
        for current, expected_title in [
            (payload("09.11.26"), None),
            (payload("09.11.26", "10.11.26"), "Графік на завтра змінився"),
            (payload("09.11.26", today_status="on"), "Графік змінився"),
            (payload("09.11.26", "10.11.26", today_status="on"), "Графік змінився"),
        ]:
            with self.subTest(current=current):
                bot = FakeBot()
                monitor = ScheduleMonitor(
                    bot=bot,
                    chat_id="chat",
                    service=FakeScheduleService([initial, current, current]),
                )
                monitor.refresh_now()
                self.assertEqual(bot.messages, [])
                self.assertEqual(monitor.refresh_now(), current)
                monitor.refresh_now()

                if expected_title is None:
                    self.assertEqual(bot.messages, [])
                else:
                    self.assertEqual(len(bot.messages), 1)
                    self.assertIn(expected_title, bot.messages[0][1])
                    self.assertIn(current["telegram_text"], bot.messages[0][1])
                    self.assertTrue(bot.messages[0][2]["disable_notification"])
                self.assertTrue(monitor.get_cached_text().startswith(current["telegram_text"]))

    def test_missing_schedules_do_not_count_as_unchanged_rollover(self):
        initial = {
            "today_signature": "old",
            "tomorrow_signature": None,
            "telegram_text": "Старий графік",
        }
        current = {
            "today_signature": None,
            "tomorrow_signature": None,
            "telegram_text": "Даних по графіку немає",
        }
        bot = FakeBot()
        monitor = ScheduleMonitor(
            bot=bot,
            chat_id="chat",
            service=FakeScheduleService([initial, current]),
        )

        monitor.refresh_now()
        monitor.refresh_now()

        self.assertEqual(len(bot.messages), 1)


if __name__ == "__main__":
    unittest.main()
