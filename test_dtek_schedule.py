import unittest
from datetime import datetime

from dtek_schedule import DtekScheduleService


class PlannedOutageTests(unittest.TestCase):
    def setUp(self):
        self.service = DtekScheduleService("Забір", "Перемоги", "21")
        slots = [{"hour": f"{hour:02d}-{hour + 1:02d}", "status": "on"} for hour in range(24)]
        slots[8]["status"] = "off"
        slots[9]["status"] = "off"
        slots[18]["status"] = "second_half_off"
        slots[19]["status"] = "off"
        slots[20]["status"] = "first_half_off"
        self.payload = {
            "schedule": [
                {
                    "day": "на сьогодні 13.10.26",
                    "slots": slots,
                }
            ]
        }

    def test_matches_outage_inside_planned_interval(self):
        segment = self.service.find_planned_outage(
            self.payload,
            datetime(2026, 10, 13, 8, 19),
        )

        self.assertEqual(segment, (8 * 60, 10 * 60))
        self.assertEqual(self.service.format_outage_segment(segment), "❌ 08:00–10:00")

    def test_matches_outage_within_thirty_minutes_before_interval(self):
        segment = self.service.find_planned_outage(
            self.payload,
            datetime(2026, 10, 13, 18, 5),
        )

        self.assertEqual(segment, (18 * 60 + 30, 20 * 60 + 30))

    def test_does_not_match_outage_outside_tolerance(self):
        segment = self.service.find_planned_outage(
            self.payload,
            datetime(2026, 10, 13, 17, 59),
        )

        self.assertIsNone(segment)


if __name__ == "__main__":
    unittest.main()
