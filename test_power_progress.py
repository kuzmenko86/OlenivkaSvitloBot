from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from dtek_schedule import DtekScheduleService
from monitor import ElectricityMonitor
from power_progress import PowerEvent, PowerMessage
from utils import KYIV_TZ


def when(hour, minute=0, day=9):
    return KYIV_TZ.localize(datetime(2026, 11, day, hour, minute))


class PowerProgressTests(unittest.TestCase):
    def message(self, events=None, online=False, start=None, end=None):
        return PowerMessage(
            online=online,
            since=when(11, 22).timestamp(),
            base_text="Світло дали!" if online else "Світло зникло!",
            start=(start or when(10)).timestamp(),
            end=(end or when(16, 30)).timestamp(),
            events=events or [
                PowerEvent(when(9).timestamp(), True),
                PowerEvent(when(11, 22).timestamp(), False),
            ],
        )

    def test_fixed_layout_only_colors_completed_cells(self):
        message = self.message()
        for hour, expected in [
            (10, "⬜⬜⬜⬜⬜⬜⬜"),
            (11, "🟩⬜⬜⬜⬜⬜⬜"),
            (12, "🟩🟥⬜⬜⬜⬜⬜"),
            (16, "🟩🟥🟥🟥🟥🟥⬜"),
        ]:
            with self.subTest(hour=hour):
                self.assertIn(f"*10:00* {expected} *16:30*", message.render(when(hour).timestamp()))
        self.assertIn(
            "*10:00* 🟩🟥🟥🟥🟥🟥🟥 *16:30*",
            message.render(when(16, 30).timestamp()),
        )

    def test_hour_color_requires_strictly_more_than_forty_minutes_of_power(self):
        for minute, expected in [(39, "🟥"), (40, "🟥"), (41, "🟩")]:
            message = self.message(events=[
                PowerEvent(when(10).timestamp(), True),
                PowerEvent(when(10, minute).timestamp(), False),
            ])
            with self.subTest(minute=minute):
                self.assertIn(f"*10:00* {expected}", message.render(when(11).timestamp()))

    def test_half_hour_threshold_and_multiple_transitions(self):
        for minute, expected in [(20, "🟥"), (21, "🟩")]:
            message = self.message(
                start=when(16), end=when(16, 30),
                events=[
                    PowerEvent(when(16).timestamp(), True),
                    PowerEvent(when(16, minute).timestamp(), False),
                ],
            )
            with self.subTest(minute=minute):
                self.assertIn(f"*16:00* {expected} *16:30*", message.render(when(16, 30).timestamp()))
        message = self.message(events=[
            PowerEvent(when(10).timestamp(), True),
            PowerEvent(when(10, 20).timestamp(), False),
            PowerEvent(when(10, 30).timestamp(), True),
        ])
        self.assertIn("*10:00* 🟩", message.render(when(11).timestamp()))

    def test_extra_time_preserves_main_bar_and_separator(self):
        text = self.message().render(when(18).timestamp())
        self.assertIn("*16:30* | 🟥🟥 *18:00*", text)
        self.assertIn("Екстра — понад графік: *1 год 30 хв*", text)
        self.assertIn("Без світла: *6 год 38 хв*", text)

    def test_scheduled_half_hour_uses_square_without_legend(self):
        message = self.message(
            start=when(6), end=when(14, 30),
            events=[PowerEvent(when(6).timestamp(), False)],
        )
        text = message.render(when(14).timestamp())
        self.assertIn("*06:00* 🟥🟥🟥🟥🟥🟥🟥🟥⬜ *14:30*", text)
        self.assertNotIn("Квадрат =", text)
        self.assertNotIn("кружечок", text)
        self.assertNotIn("⚪", text)

    def test_extra_endpoint_rounds_down_but_duration_keeps_minutes(self):
        message = self.message(
            online=True, start=when(0), end=when(3),
            events=[PowerEvent(when(0).timestamp(), True)],
        )
        message.since = when(1, 12).timestamp()
        text = message.render(when(9, 13).timestamp())
        self.assertIn("*03:00* | 🟩🟩🟩🟩🟩🟩 *09:00*", text)
        self.assertNotIn("*09:13*", text)
        self.assertIn("Зі світлом: *8 год 1 хв*", text)
        self.assertIn("Екстра — зі світлом понад графік: *6 год 13 хв*", text)

    def test_extra_bar_waits_until_clock_hour_after_scheduled_end(self):
        text = self.message().render(when(16, 45).timestamp())
        self.assertNotIn(" | ", text)
        self.assertIn("Екстра — понад графік: *15 хв*", text)

    def test_unknown_schedule_does_not_end_before_it_starts(self):
        message = self.message(
            start=when(11, 22),
            events=[PowerEvent(when(11, 22).timestamp(), False)],
        )
        message.end = None
        text = message.render(when(11, 40).timestamp())
        self.assertIn("*11:22* … *11:22*", text)
        self.assertNotIn("*11:00*", text)
        self.assertIn("Без світла: *18 хв*", text)

    def test_green_window_includes_late_restoration_in_red(self):
        message = self.message(
            online=True, start=when(16, 30), end=when(19, 30),
            events=[
                PowerEvent(when(10).timestamp(), False),
                PowerEvent(when(17, 22).timestamp(), True),
            ],
        )
        text = message.render(when(18, 30).timestamp())
        self.assertIn("*16:30* 🟥🟩⬜ *19:30*", text)
        self.assertIn("До наступного відключення: *1 год 0 хв*", text)
        self.assertIn("*19:30* | 🟩 *20:00*", message.render(when(20).timestamp()))

    def test_unknown_schedule_has_no_predicted_end(self):
        for online, expected in [(False, "🟥"), (True, "🟩")]:
            message = self.message(
                online=online, start=when(10),
                events=[PowerEvent(when(10).timestamp(), online)],
            )
            message.end = None
            text = message.render(when(11, 30).timestamp())
            with self.subTest(online=online):
                self.assertIn(f"*10:00* {expected} *11:00*", text)
                self.assertIn("невідом", text)
                self.assertNotIn("⌛", text)

    def test_unknown_history_is_not_reported_as_red_or_green(self):
        message = self.message(events=[PowerEvent(when(11, 22).timestamp(), False)])
        self.assertIn("*10:00* ❔❔", message.render(when(12).timestamp()))

    def test_midnight_dates_and_long_extra_are_bounded(self):
        message = self.message(start=when(22), end=when(0, day=10))
        self.assertIn("*10.11 00:00* |", message.render(when(1, day=10).timestamp()))
        text = message.render(when(23, day=14).timestamp())
        self.assertIn("…", text)
        self.assertLess(len(text), 1000)

    def test_state_round_trip_and_invalid_history(self):
        message = self.message()
        restored = PowerMessage.from_dict(json.loads(json.dumps(asdict(message))))
        self.assertEqual(restored, message)
        for invalid in [
            None,
            {**asdict(message), "events": []},
            {**asdict(message), "message_id": "12"},
            {**asdict(message), "end": message.start - 1},
            {**asdict(message), "since": float("nan")},
        ]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                PowerMessage.from_dict(invalid)

    def test_finished_message_keeps_bar_without_stale_countdown(self):
        text = self.message().render(when(16, 30).timestamp(), finished=True)
        self.assertIn("*10:00* 🟩🟥🟥🟥🟥🟥🟥 *16:30*", text)
        self.assertIn("Світла не було: *5 год 8 хв*", text)
        self.assertIn("Світло відновлено о *16:30*", text)
        self.assertNotIn("⌛", text)
        self.assertNotIn("невідом", text)


class FakeBot:
    def __init__(self):
        self.sent = []
        self.edited = []
        self.fail_send = False
        self.fail_edit = False

    def send_message(self, chat_id, text, **kwargs):
        if self.fail_send:
            raise RuntimeError("send failed")
        self.sent.append((chat_id, text, kwargs))
        return SimpleNamespace(message_id=len(self.sent))

    def edit_message_text(self, text, **kwargs):
        if self.fail_edit:
            raise RuntimeError("edit failed")
        self.edited.append((text, kwargs))


class FakeScheduleMonitor:
    def __init__(self):
        self.service = DtekScheduleService("Забір", "Перемоги", "21")
        slots = [{"hour": str(hour), "status": "on"} for hour in range(24)]
        for hour in range(10, 16):
            slots[hour]["status"] = "off"
        slots[16]["status"] = "first_half_off"
        slots[19]["status"] = "second_half_off"
        for hour in range(20, 24):
            slots[hour]["status"] = "off"
        self.payload = {"schedule": [{"day": "на сьогодні 09.11.26", "slots": slots}]}
        self.payload["telegram_text"] = self.service.build_schedule_text(self.payload)
        self.refreshes = 0
        self.fail = False

    def refresh_now(self):
        self.refreshes += 1
        if self.fail:
            raise RuntimeError("schedule failed")
        return self.payload


class PowerMessageEditingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.state_path = root / "state.json"
        self.offline_path = root / "offline.txt"
        self.patches = [
            patch("monitor.POWER_MESSAGE_STATE_FILE", str(self.state_path)),
            patch("monitor.OFFLINE_SINCE_FILE", str(self.offline_path)),
            patch("monitor.TuyaAPI"),
            patch("monitor.next_outage_message", return_value="А бодай йому грець!"),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.bot = FakeBot()
        self.schedule = FakeScheduleMonitor()
        self.monitor = ElectricityMonitor(self.bot, "chat", self.schedule)

    def check(self, hour, minute=0, online=False, monitor=None):
        target = monitor or self.monitor
        target.tuya.get_electricity_info.return_value = {
            "online": online, "voltage": 230, "name": "Meter",
        }
        with patch("monitor.kyiv_now", return_value=when(hour, minute)):
            target.check_and_notify()

    def start_outage(self):
        self.check(9, online=True)
        self.check(11, 22)

    def test_hourly_edit_does_not_publish_or_refetch_schedule(self):
        self.start_outage()
        self.assertEqual(len(self.bot.sent), 1)
        self.check(11, 59)
        self.assertEqual(self.bot.edited, [])
        self.check(12)
        self.check(12, 1)
        self.check(12, 59)
        self.assertEqual(len(self.bot.sent), 1)
        self.assertEqual(len(self.bot.edited), 1)
        text, kwargs = self.bot.edited[0]
        self.assertIn("*10:00* 🟩🟥⬜⬜⬜⬜⬜ *16:30*", text)
        self.assertIn("Без світла: *38 хв*", text)
        self.assertEqual(kwargs["message_id"], 1)
        self.assertEqual(kwargs["chat_id"], "chat")
        self.assertIn("reply_markup", kwargs)
        self.assertEqual(self.schedule.refreshes, 1)
        self.assertEqual(self.bot.sent[0][2]["parse_mode"], "Markdown")
        self.assertIn("А бодай йому грець!", text)

    def test_restoration_starts_new_message_and_only_edits_that_message(self):
        self.start_outage()
        self.check(16, 30, online=True)
        self.assertEqual(len(self.bot.sent), 2)
        restored = self.bot.sent[1][1]
        self.assertIn("Світло дали!", restored)
        self.assertIn("230 Вольт", restored)
        self.assertIn("Світла не було: *5 год 8 хв*", restored)
        self.assertIn("*16:30* ⬜⬜⬜ *19:30*", restored)
        self.assertFalse(self.offline_path.exists())
        self.assertIn("Світло відновлено о *16:30*", self.bot.edited[0][0])
        self.assertEqual(self.bot.edited[0][1]["message_id"], 1)
        self.check(17, 30, online=True)
        self.assertIn("*16:30* 🟩⬜⬜ *19:30*", self.bot.edited[-1][0])
        self.assertEqual(self.bot.edited[-1][1]["message_id"], 2)
        self.check(19, 30, online=True)
        self.check(20, 30, online=True)
        self.assertIn("*19:30* | 🟩 *20:00*", self.bot.edited[-1][0])
        self.assertEqual(len(self.bot.sent), 2)

    def test_restart_resumes_same_message_without_sending_a_new_one(self):
        self.start_outage()
        restarted = ElectricityMonitor(self.bot, "chat", self.schedule)
        self.check(12, 22, monitor=restarted)
        self.assertEqual(len(self.bot.sent), 1)
        self.assertEqual(self.bot.edited[-1][1]["message_id"], 1)
        self.assertIn("🟩🟥", self.bot.edited[-1][0])

    def test_delayed_hourly_check_uses_round_endpoint_and_does_not_repeat(self):
        self.schedule.payload = None
        self.start_outage()
        self.check(12, 3)
        self.assertEqual(len(self.bot.edited), 1)
        self.assertIn("*12:00*", self.bot.edited[0][0])
        self.assertIn("Без світла: *41 хв*", self.bot.edited[0][0])
        self.check(12, 59)
        self.assertEqual(len(self.bot.edited), 1)
        self.check(13)
        self.assertEqual(len(self.bot.edited), 2)

    def test_restart_in_same_clock_hour_waits_for_next_hour(self):
        self.start_outage()
        restarted = ElectricityMonitor(self.bot, "chat", self.schedule)
        self.check(11, 59, monitor=restarted)
        self.assertEqual(self.bot.edited, [])
        self.check(12, monitor=restarted)
        self.assertEqual(len(self.bot.edited), 1)

    def test_hourly_edit_crosses_midnight(self):
        self.check(22, online=True)
        self.check(23, 59)
        with patch("monitor.kyiv_now", return_value=when(0, day=10)):
            self.monitor.check_and_notify()
        self.assertEqual(len(self.bot.sent), 1)
        self.assertEqual(len(self.bot.edited), 1)
        self.assertIn("*10.11 00:00*", self.bot.edited[0][0])

    def test_restart_with_different_status_does_not_edit_stale_message(self):
        self.start_outage()
        restarted = ElectricityMonitor(self.bot, "chat", self.schedule)
        self.check(12, 22, online=True, monitor=restarted)
        self.assertEqual(self.bot.edited, [])
        self.assertFalse(self.state_path.exists())

    def test_send_and_edit_failures_retry_without_advancing_update_time(self):
        self.bot.fail_send = True
        self.start_outage()
        self.assertEqual(self.bot.sent, [])
        self.bot.fail_send = False
        self.check(11, 23)
        self.assertEqual(len(self.bot.sent), 1)
        self.bot.fail_edit = True
        self.check(12, 23)
        self.assertEqual(self.monitor._message.updated_at, when(11, 23).timestamp())
        self.bot.fail_edit = False
        self.check(12, 24)
        self.assertEqual(len(self.bot.edited), 1)
        self.assertEqual(len(self.bot.sent), 1)

    def test_failed_preparation_retries_original_transition(self):
        self.check(9, online=True)
        self.schedule.fail = True
        self.check(11, 22)
        self.assertEqual(self.bot.sent, [])
        self.assertTrue(self.monitor.last_online_status)
        self.schedule.fail = False
        self.check(11, 23)
        self.assertEqual(len(self.bot.sent), 1)
        self.assertEqual(self.monitor._message.since, when(11, 22).timestamp())
        self.assertEqual(len(self.monitor._events), 2)

    def test_failed_preparation_followed_by_recovery_keeps_actual_history(self):
        self.check(9, online=True)
        self.schedule.fail = True
        self.check(10)
        self.check(10, 30, online=True)
        self.assertEqual(
            [event.online for event in self.monitor._events],
            [True, False, True],
        )
        self.schedule.fail = False
        self.check(11)
        self.check(12)
        self.assertIn("*10:00* 🟥🟥", self.bot.edited[-1][0])

    def test_failed_final_edit_does_not_block_restoration_notification(self):
        self.start_outage()
        self.bot.fail_edit = True
        self.check(16, 30, online=True)
        self.assertEqual(len(self.bot.sent), 2)
        self.assertIn("Світло дали!", self.bot.sent[-1][1])

    def test_unknown_schedule_still_updates_elapsed_time(self):
        self.schedule.payload = None
        self.start_outage()
        self.assertIn("Не вдалося перевірити", self.bot.sent[0][1])
        self.check(12, 22)
        self.assertIn("Без світла: *1 год 0 хв*", self.bot.edited[0][0])
        self.assertNotIn("⌛", self.bot.edited[0][0])

    def test_initial_status_without_saved_message_does_not_publish(self):
        self.check(10)
        self.check(11)
        self.assertEqual(self.bot.sent, [])
        self.assertEqual(self.bot.edited, [])


if __name__ == "__main__":
    unittest.main()
