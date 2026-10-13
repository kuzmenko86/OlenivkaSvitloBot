import hashlib
import json
import re
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Locator, TimeoutError as PlaywrightTimeoutError


class DtekScheduleService:
    """
    Сервіс для:
    1) отримання графіка з DTEK по адресі
    2) парсингу статусів по годинах
    3) формування короткого тексту для Telegram
    """

    def __init__(self, city: str, street: str, house_num: str, url: str = "https://www.dtek-krem.com.ua/ua/shutdowns"):
        self.city = city
        self.street = street
        self.house_num = house_num
        self.url = url

    def _safe_click(self, page, selector: str, timeout: int = 1200) -> bool:
        try:
            el = page.locator(selector).first
            if el.is_visible(timeout=timeout):
                el.click(timeout=timeout)
                return True
        except Exception:
            pass
        return False

    def _dismiss_overlays(self, page):
        # Закриваємо попапи / оверлеї, які блокують поля
        for sel in [
            "h6 + .modal__close",
            ".modal__close",
            ".modal .close",
            "[data-dismiss='modal']",
            ".fancybox-close-small",
            ".mfp-close",
        ]:
            self._safe_click(page, sel)

        try:
            page.keyboard.press("Escape")
        except Exception:
            pass

    def _pick_first_autocomplete(self, root: Locator, input_selector: str, value: str, list_selector: str, delay: int = 60):
        page = root.page
        self._dismiss_overlays(page)

        inp = root.locator(input_selector).first
        inp.wait_for(state="visible", timeout=15000)
        inp.click(timeout=5000)
        inp.fill("")
        inp.type(value, delay=delay)

        page.wait_for_selector(list_selector, state="visible", timeout=15000)

        first_item = page.locator(f"{list_selector} > div:first-child").first
        if first_item.count() > 0 and first_item.is_visible():
            first_item.click(timeout=5000)
        else:
            page.locator(list_selector).first.click(timeout=5000)


    def _label_from_rel(self, rel_value: str, idx: int) -> str:
        try:
            import pytz
            kyiv_tz = pytz.timezone("Europe/Kyiv")
            dt = datetime.fromtimestamp(int(rel_value), tz=kyiv_tz)
            today = datetime.now(kyiv_tz).date()
            if dt.date() == today:
                return f"на сьогодні {dt.strftime('%d.%m.%y')}"
            if (dt.date() - today).days == 1:
                return f"на завтра {dt.strftime('%d.%m.%y')}"
            return dt.strftime("%d.%m.%Y")
        except Exception:
            return f"День {idx + 1}"

    def _parse_schedule_from_html(self, html: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        result: list[dict[str, Any]] = []

        tab_labels = [re.sub(r"\s+", " ", x.get_text(" ", strip=True)) for x in soup.select(".groupstab")]
        blocks = soup.select("div.discon-fact-table")

        for idx, block in enumerate(blocks):
            table = block.select_one("table")
            if not table:
                continue

            day = tab_labels[idx] if idx < len(tab_labels) and tab_labels[idx] else self._label_from_rel(block.get("rel", ""), idx)

            hours = [x.get_text(strip=True) for x in table.select("thead th[scope='col'] div")]
            hours = [h for h in hours if h]

            row = table.select_one("tbody tr")
            if not row:
                result.append({"day": day, "slots": []})
                continue

            data_tds = [td for td in row.select("td") if not td.has_attr("colspan")]
            slots = []

            for i, td in enumerate(data_tds):
                cls = " ".join(td.get("class", []))
                hour = hours[i] if i < len(hours) else f"{i:02d}-{(i + 1):02d}"

                # ВАЖЛИВО: за легендою сайту
                # cell-non-scheduled = світло є
                # cell-scheduled = світла немає
                if "cell-non-scheduled" in cls:
                    status = "on"
                elif "cell-scheduled" in cls:
                    status = "off"
                elif "cell-first-half" in cls:
                    status = "first_half_off"
                elif "cell-second-half" in cls:
                    status = "second_half_off"
                else:
                    status = "unknown"

                slots.append({"hour": hour, "status": status})

            result.append({"day": day, "slots": slots})

        return result

    def _pick_today_schedule(self, schedule: list[dict[str, Any]]) -> dict[str, Any] | None:
        return self._pick_day_schedule(schedule, day_offset=0)

    def _pick_tomorrow_schedule(self, schedule: list[dict[str, Any]]) -> dict[str, Any] | None:
        return self._pick_day_schedule(schedule, day_offset=1)

    def _pick_day_schedule(self, schedule: list[dict[str, Any]], day_offset: int) -> dict[str, Any] | None:
        if not schedule:
            return None

        keyword = "сьогодні" if day_offset == 0 else "завтра"
        for day in schedule:
            if keyword in day.get("day", "").lower():
                return day

        try:
            import pytz

            kyiv_tz = pytz.timezone("Europe/Kyiv")
            target_date = datetime.now(kyiv_tz).date()
            target_date = target_date.fromordinal(target_date.toordinal() + day_offset)
            for day in schedule:
                match = re.search(r"(\d{2})\.(\d{2})(?:\.(\d{2,4}))?", day.get("day", ""))
                if not match:
                    continue
                day_number, month, year = match.groups()
                if year is None:
                    year = str(target_date.year)
                elif len(year) == 2:
                    year = f"20{year}"
                if datetime(int(year), int(month), int(day_number)).date() == target_date:
                    return day
        except (ImportError, ValueError):
            pass

        return schedule[day_offset] if len(schedule) > day_offset else None

    def _extract_day_short(self, day_label: str) -> str:
        m = re.search(r"(\d{2}\.\d{2})(?:\.\d{2,4})?", day_label or "")
        return m.group(1) if m else ""

    def _off_segments_from_slots(self, slots: list[dict[str, Any]]) -> list[tuple[int, int]]:
        # Переходимо в півгодинні інтервали 0..47
        off_half_hours = []
        for i, slot in enumerate(slots):
            st = slot.get("status")
            half_idx = i * 2
            if st == "off":
                off_half_hours.extend([half_idx, half_idx + 1])
            elif st == "first_half_off":
                off_half_hours.append(half_idx)
            elif st == "second_half_off":
                off_half_hours.append(half_idx + 1)

        if not off_half_hours:
            return []

        off_half_hours = sorted(set(off_half_hours))
        segments = []
        start = off_half_hours[0]
        prev = off_half_hours[0]

        for x in off_half_hours[1:]:
            if x == prev + 1:
                prev = x
            else:
                segments.append((start * 30, (prev + 1) * 30))
                start = x
                prev = x
        segments.append((start * 30, (prev + 1) * 30))
        return segments

    def _fmt_hhmm(self, minutes: int) -> str:
        if minutes >= 24 * 60:
            return "24:00"
        h = minutes // 60
        m = minutes % 60
        return f"{h:02d}:{m:02d}"

    def find_planned_outage(
        self,
        payload: dict[str, Any],
        when: datetime,
        tolerance_minutes: int = 30,
    ) -> tuple[int, int] | None:
        today = self._pick_today_schedule(payload.get("schedule", []))
        if not today:
            return None

        current_minutes = when.hour * 60 + when.minute
        for start_min, end_min in self._off_segments_from_slots(today.get("slots", [])):
            if start_min - tolerance_minutes <= current_minutes <= end_min + tolerance_minutes:
                return start_min, end_min
        return None

    def format_outage_segment(self, segment: tuple[int, int]) -> str:
        start_min, end_min = segment
        return f"❌ {self._fmt_hhmm(start_min)}–{self._fmt_hhmm(end_min)}"

    def _build_day_text(self, day: dict[str, Any], label: str) -> str:
        day_short = self._extract_day_short(day.get("day", ""))
        segments = self._off_segments_from_slots(day.get("slots", []))

        if not segments:
            return f"✅ {label} ({day_short}) без відключень! 🎉" if day_short else f"✅ {label} без відключень! 🎉"

        lines = [f"{label} ({day_short}) світло буде відсутнє:" if day_short else f"{label} світло буде відсутнє:"]
        for start_min, end_min in segments:
            lines.append(f"❌ {self._fmt_hhmm(start_min)}–{self._fmt_hhmm(end_min)}")
        return "\n".join(lines)

    def build_schedule_text(self, payload: dict[str, Any]) -> str:
        schedule = payload.get("schedule", [])
        today = self._pick_today_schedule(schedule)
        tomorrow = self._pick_tomorrow_schedule(schedule)

        if not today:
            return "⚠️ Даних по графіку немає."

        sections = [self._build_day_text(today, "Сьогодні")]
        if tomorrow:
            sections.append(self._build_day_text(tomorrow, "Завтра"))

        return "⚠️ Графік відключень ДТЕК ⚠️\n" + "\n\n──────────\n\n".join(sections)

    def build_today_text(self, payload: dict[str, Any]) -> str:
        return self.build_schedule_text(payload)

    def get_payload(self) -> dict[str, Any]:
        schedule_html = ""
        last_update = ""

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1440, "height": 1000},
                locale="uk-UA",
                timezone_id="Europe/Kyiv",
                geolocation={"latitude": 50.4501, "longitude": 30.5234},
                permissions=["geolocation"],
            )
            page = context.new_page()
            page.goto(self.url, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle")
            self._dismiss_overlays(page)

            # Працюємо тільки з формою графіка
            main_form = page.locator("#discon_schedule_form").first
            if main_form.count() == 0:
                main_form = page.locator("form:has(#street):has(#house_num)").first

            self._pick_first_autocomplete(main_form, "#city", self.city, "#cityautocomplete-list", delay=50)
            self._pick_first_autocomplete(main_form, "#street", self.street, "#streetautocomplete-list", delay=50)
            if self.house_num:
                self._pick_first_autocomplete(main_form, "#house_num", self.house_num, "#house_numautocomplete-list", delay=80)

            page.wait_for_timeout(700)

            try:
                last_update = page.text_content("span.discon-fact-info-text", timeout=10000) or ""
            except PlaywrightTimeoutError:
                pass

            try:
                schedule_html = page.inner_html("div.discon-fact-tables", timeout=10000) or ""
            except PlaywrightTimeoutError:
                pass

            # Діагностика: скріншот + лог
            try:
                page.screenshot(path="dtek_debug.png", full_page=True)
                print("📸 Скріншот збережено: dtek_debug.png")
            except Exception as e:
                print(f"⚠️ Не вдалось зберегти скріншот: {e}")

            if not schedule_html:
                print("⚠️ DTEK: schedule_html порожній!")
            else:
                td_count = schedule_html.count("<td")
                has_scheduled = "cell-scheduled" in schedule_html
                print(f"📋 DTEK: отримано HTML ({len(schedule_html)} символів, {td_count} td, has_scheduled={has_scheduled})")

            # Зберігаємо сирий HTML для аналізу
            try:
                with open("dtek_debug.html", "w", encoding="utf-8") as f:
                    f.write(schedule_html)
                print("📄 HTML збережено: dtek_debug.html")
            except Exception as e:
                print(f"⚠️ Не вдалось зберегти HTML: {e}")

            context.close()
            browser.close()

        payload = {
            "address": {"city": self.city, "street": self.street, "house_num": self.house_num},
            "last_update": last_update.strip(),
            "schedule": self._parse_schedule_from_html(schedule_html),
        }
        payload["telegram_text"] = self.build_schedule_text(payload)
        payload["today_signature"] = self.make_day_signature(self._pick_today_schedule(payload["schedule"]))
        payload["tomorrow_signature"] = self.make_day_signature(self._pick_tomorrow_schedule(payload["schedule"]))
        payload["signature"] = self.make_signature(payload)
        return payload

    def make_day_signature(self, day: dict[str, Any] | None) -> str | None:
        if day is None:
            return None
        compact = {
            "day": day.get("day"),
            "slots": day.get("slots", []),
        }
        raw = json.dumps(compact, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def make_signature(self, payload: dict[str, Any]) -> str:
        """
        Підпис стану графіка на сьогодні та завтра.
        Якщо змінився підпис — значить графік змінився.
        """
        compact = {
            "today": self.make_day_signature(self._pick_today_schedule(payload.get("schedule", []))),
            "tomorrow": self.make_day_signature(self._pick_tomorrow_schedule(payload.get("schedule", []))),
        }
        raw = json.dumps(compact, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()