import unittest
from unittest.mock import patch

from monitor import ElectricityMonitor


class FakeScheduleService:
    def __init__(self, planned_segment):
        self.planned_segment = planned_segment

    def find_planned_outage(self, payload, when, tolerance_minutes):
        return self.planned_segment

    def format_outage_segment(self, segment):
        return "❌ 06:00–08:30"


class FakeScheduleMonitor:
    def __init__(self, payload, planned_segment):
        self.payload = payload
        self.service = FakeScheduleService(planned_segment)

    def refresh_now(self):
        return self.payload


class PowerLostMessageTests(unittest.TestCase):
    def build_monitor(self, payload, planned_segment):
        monitor = ElectricityMonitor.__new__(ElectricityMonitor)
        monitor.schedule_monitor = FakeScheduleMonitor(payload, planned_segment)
        return monitor

    @patch("monitor.next_outage_message", return_value="А бодай йому грець!")
    def test_planned_outage_includes_rotating_message(self, _):
        monitor = self.build_monitor({"telegram_text": "Графік"}, (360, 510))

        message = monitor._build_power_lost_message()

        self.assertTrue(message.startswith("📣 А бодай йому грець!"))
        self.assertIn("У рамках планового відключення", message)

    @patch("monitor.next_outage_message", return_value="Йосип босий!")
    def test_unplanned_outage_includes_rotating_message(self, _):
        monitor = self.build_monitor({"telegram_text": "Поточний графік"}, None)

        message = monitor._build_power_lost_message()

        self.assertTrue(message.startswith("📣 Йосип босий!"))
        self.assertIn("НЕ ЗА ГРАФІКОМ", message)
        self.assertIn("Поточний графік", message)


if __name__ == "__main__":
    unittest.main()
