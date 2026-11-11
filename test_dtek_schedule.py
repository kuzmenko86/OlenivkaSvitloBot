import unittest
from datetime import datetime

from dtek_schedule import DtekScheduleService
from utils import KYIV_TZ


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

    def test_power_window_runs_from_previous_outage_end_to_next_start(self):
        when = KYIV_TZ.localize(datetime(2026, 10, 13, 10, 5))
        self.assertEqual(
            self.service.find_power_window(self.payload, when),
            (
                KYIV_TZ.localize(datetime(2026, 10, 13, 10)),
                KYIV_TZ.localize(datetime(2026, 10, 13, 18, 30)),
            ),
        )

    def test_power_window_finds_next_outage_tomorrow(self):
        self.payload["schedule"].append({
            "day": "на завтра 14.10.26",
            "slots": [{"hour": "00-01", "status": "off"}],
        })
        when = KYIV_TZ.localize(datetime(2026, 10, 13, 22))
        self.assertEqual(
            self.service.find_power_window(self.payload, when),
            (
                KYIV_TZ.localize(datetime(2026, 10, 13, 20, 30)),
                KYIV_TZ.localize(datetime(2026, 10, 14)),
            ),
        )

    def test_power_window_does_not_invent_next_outage(self):
        when = KYIV_TZ.localize(datetime(2026, 10, 13, 22))
        self.assertEqual(
            self.service.find_power_window(self.payload, when),
            (KYIV_TZ.localize(datetime(2026, 10, 13, 20, 30)), None),
        )
        self.assertIsNone(self.service.find_power_window({"schedule": []}, when))


class NextOutageTests(unittest.TestCase):
    def setUp(self):
        self.service = DtekScheduleService("Забір", "Перемоги", "21")
        self.payload = {
            "schedule": [{
                "day": "на сьогодні 11.11.26",
                "slots": [
                    {"status": (
                        "off" if 3 <= hour < 7 or 14 <= hour < 21
                        else "first_half_off" if hour == 7
                        else "second_half_off" if hour == 13 else "on"
                    )}
                    for hour in range(24)
                ],
            }],
        }

    def at(self, hour, minute=0, day=11):
        return KYIV_TZ.localize(datetime(2026, 11, day, hour, minute))

    def test_selects_active_or_next_interval_with_exclusive_end(self):
        for hour, minute, expected in [
            (1, 12, (self.at(3), self.at(7, 30))),
            (3, 0, (self.at(3), self.at(7, 30))),
            (5, 0, (self.at(3), self.at(7, 30))),
            (7, 30, (self.at(13, 30), self.at(21))),
            (10, 30, (self.at(13, 30), self.at(21))),
            (13, 30, (self.at(13, 30), self.at(21))),
            (14, 0, (self.at(13, 30), self.at(21))),
            (21, 0, None),
            (22, 0, None),
        ]:
            with self.subTest(hour=hour, minute=minute):
                self.assertEqual(
                    self.service.find_next_outage(self.payload, self.at(hour, minute)),
                    expected,
                )

    def test_selects_tomorrow_and_does_not_relabel_stale_today(self):
        self.payload["schedule"].append({
            "day": "на завтра 12.11.2026",
            "slots": [{"status": "off"}],
        })
        expected = (self.at(0, day=12), self.at(1, day=12))
        self.assertEqual(
            self.service.find_next_outage(self.payload, self.at(22)), expected,
        )
        self.assertIsNone(self.service.find_next_outage(self.payload, self.at(22, day=12)))

    def test_sorts_days_and_accepts_date_without_year(self):
        self.payload["schedule"].insert(0, {
            "day": "на завтра 12.11",
            "slots": [{"status": "off"}],
        })
        self.assertEqual(
            self.service.find_next_outage(self.payload, self.at(1)),
            (self.at(3), self.at(7, 30)),
        )

    def test_missing_schedule_does_not_invent_an_interval(self):
        for payload in [{}, {"schedule": []}, {"schedule": [{"day": "невідомо"}]}]:
            with self.subTest(payload=payload):
                self.assertIsNone(self.service.find_next_outage(payload, self.at(1)))

    def test_relative_labels_without_date(self):
        self.payload["schedule"][0]["day"] = "на сьогодні"
        self.assertEqual(
            self.service.find_next_outage(self.payload, self.at(10, 30)),
            (self.at(13, 30), self.at(21)),
        )


class DaySignatureTests(unittest.TestCase):
    def setUp(self):
        self.service = DtekScheduleService("Забір", "Перемоги", "21")

    def test_signature_is_unchanged_when_tomorrow_becomes_today(self):
        slots = [{"hour": "00-01", "status": "off"}]
        tomorrow = {"day": "на завтра 09.11.26", "slots": slots}
        today = {"day": "на сьогодні 09.11.26", "slots": slots}

        self.assertEqual(
            self.service.make_day_signature(tomorrow),
            self.service.make_day_signature(today),
        )

    def test_signature_distinguishes_dates_and_slot_changes(self):
        original = {
            "day": "на завтра 09.11.26",
            "slots": [{"hour": "00-01", "status": "off"}],
        }
        for changed in [
            {**original, "day": "на завтра 10.11.26"},
            {**original, "day": "на завтра 09.11.27"},
            {**original, "slots": [{"hour": "00-01", "status": "on"}]},
        ]:
            with self.subTest(changed=changed):
                self.assertNotEqual(
                    self.service.make_day_signature(original),
                    self.service.make_day_signature(changed),
                )


if __name__ == "__main__":
    unittest.main()
