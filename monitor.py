import os
import json
import threading
import time
from dataclasses import asdict
from datetime import datetime, timedelta
from tuya_api import TuyaAPI
from config import ELECTRICITY_DEVICE_ID, MONITOR_INTERVAL
from keyboards import get_group_keyboard
from outage_messages import next_outage_message
from power_progress import PowerEvent, PowerMessage, POWER_MESSAGE_UPDATE_SECONDS, format_duration
from schedule_monitor import ScheduleMonitor
from utils import KYIV_TZ, is_night_kyiv, kyiv_now

OFFLINE_SINCE_FILE = os.path.join(os.path.dirname(__file__), "offline_since.txt")
SCHEDULE_TOLERANCE_MINUTES = 30
POWER_MESSAGE_STATE_FILE = os.path.join(os.path.dirname(__file__), "power_message_state.json")


class ElectricityMonitor:
    def __init__(
        self,
        bot,
        chat_id: str,
        schedule_monitor: ScheduleMonitor,
        on_status_change=None,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.schedule_monitor = schedule_monitor
        self.tuya = TuyaAPI()
        self.device_id = ELECTRICITY_DEVICE_ID
        self.last_online_status = None
        self._on_status_change = on_status_change
        self._running = False
        self._thread = None
        self._message = self._read_message_state()
        self._events = self._message.events if self._message else []

    @staticmethod
    def _read_message_state() -> PowerMessage | None:
        try:
            with open(POWER_MESSAGE_STATE_FILE, encoding="utf-8") as f:
                return PowerMessage.from_dict(json.load(f))
        except FileNotFoundError:
            return None
        except (OSError, ValueError, TypeError) as e:
            print(f"⚠️ Не вдалося прочитати стан повідомлення про світло: {e}")
            return None

    def _save_message_state(self):
        if self._message is None:
            try:
                os.remove(POWER_MESSAGE_STATE_FILE)
            except FileNotFoundError:
                pass
            return
        temp_file = f"{POWER_MESSAGE_STATE_FILE}.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(asdict(self._message), f, ensure_ascii=False)
        os.replace(temp_file, POWER_MESSAGE_STATE_FILE)

    @staticmethod
    def _save_offline_since(ts: float):
        with open(OFFLINE_SINCE_FILE, "w") as f:
            f.write(str(ts))

    @staticmethod
    def _read_offline_since() -> float | None:
        try:
            with open(OFFLINE_SINCE_FILE) as f:
                return float(f.read().strip())
        except (FileNotFoundError, ValueError):
            return None

    @staticmethod
    def _clear_offline_since():
        try:
            os.remove(OFFLINE_SINCE_FILE)
        except FileNotFoundError:
            pass

    @staticmethod
    def _format_duration(seconds: float) -> str:
        return format_duration(seconds)

    def _build_power_lost_message(self, payload: dict | None, planned_segment: tuple[int, int] | None) -> str:
        joke = next_outage_message()
        title = f"📣 {joke}\n\n"
        if payload is None:
            return (
                f"{title}"
                "🔴 ⚠️ *Світло зникло!*\n\n"
                "Не вдалося перевірити, чи відповідає відключення графіку.\n\n"
                "Можете перевірити графік у боті."
            )

        if planned_segment:
            segment_text = self.schedule_monitor.service.format_outage_segment(planned_segment)
            return (
                f"{title}"
                "🔴 ⚠️ *Світло зникло!*\n\n"
                f"У рамках планового відключення: *{segment_text}*\n\n"
                "Можете перевірити графік у боті."
            )

        schedule_text = payload.get("telegram_text", "⚠️ Даних по графіку немає.")
        return (
            f"{title}"
            "🔴 🔴 🔴 *Світло зникло!*\n\n"
            "*НЕ ЗА ГРАФІКОМ!*\n\n"
            f"{schedule_text}"
        )

    def _prepare_message(self, online: bool, voltage: float | None, when: datetime):
        timestamp = when.timestamp()
        payload = self.schedule_monitor.refresh_now()
        start = timestamp
        end = None
        if online:
            duration_text = ""
            offline_since = self._read_offline_since()
            if offline_since is not None:
                duration_text = f"\n\n⏱ Світла не було: *{self._format_duration(timestamp - offline_since)}*"
            base_text = (
                f"💡⚡ *Світло дали!*\n\n"
                f"🔌 Напруга в мережі: *{voltage} Вольт*"
                f"{duration_text}"
            )
            if payload is not None:
                window = self.schedule_monitor.service.find_power_window(payload, when)
                if window is not None:
                    start = window[0].timestamp()
                    end = window[1].timestamp() if window[1] is not None else None
                    if end is None:
                        start = min(start, timestamp)
        else:
            planned_segment = None
            if payload is not None:
                planned_segment = self.schedule_monitor.service.find_planned_outage(
                    payload, when, tolerance_minutes=SCHEDULE_TOLERANCE_MINUTES,
                )
            base_text = self._build_power_lost_message(payload, planned_segment)
            if planned_segment:
                midnight = datetime.combine(when.date(), datetime.min.time())
                start = KYIV_TZ.localize(midnight + timedelta(minutes=planned_segment[0])).timestamp()
                end = KYIV_TZ.localize(midnight + timedelta(minutes=planned_segment[1])).timestamp()
        self._message = PowerMessage(online, timestamp, base_text, start, end, list(self._events))
        self._save_message_state()
        if online:
            self._clear_offline_since()

    def _publish_message(self, timestamp: float):
        message = self._message
        if message is None:
            return
        if message.message_id is not None and timestamp - message.updated_at < POWER_MESSAGE_UPDATE_SECONDS:
            return
        text = message.render(timestamp)
        if message.message_id is None:
            sent = self.bot.send_message(
                self.chat_id,
                text,
                parse_mode="Markdown",
                reply_markup=get_group_keyboard(),
                disable_notification=is_night_kyiv(),
            )
            message.message_id = sent.message_id
            print(f"📨 Повідомлення надіслано: {'Світло дали' if message.online else 'Світло зникло'}")
        elif text != message.last_text:
            self.bot.edit_message_text(
                text,
                chat_id=self.chat_id,
                message_id=message.message_id,
                parse_mode="Markdown",
                reply_markup=get_group_keyboard(),
            )
            print("📝 Оновлено шкалу світла")
        message.updated_at = timestamp
        message.last_text = text
        self._save_message_state()

    def _finish_message(self, message: PowerMessage | None, timestamp: float):
        if message is None or message.message_id is None:
            return
        message.events = list(self._events)
        try:
            self.bot.edit_message_text(
                message.render(timestamp, finished=True),
                chat_id=self.chat_id,
                message_id=message.message_id,
                parse_mode="Markdown",
                reply_markup=get_group_keyboard(),
            )
        except Exception as e:
            print(f"⚠️ Не вдалося завершити попередню шкалу світла: {e}")

    def check_and_notify(self):
        """Перевіряє статус і надсилає повідомлення якщо статус змінився."""
        try:
            info = self.tuya.get_electricity_info(self.device_id)
            current_online = info["online"]
            when = kyiv_now()
            timestamp = when.timestamp()

            # Перша перевірка — просто запам'ятовуємо статус
            if self.last_online_status is None:
                self.last_online_status = current_online
                status_text = "🟢 Онлайн" if current_online else "🔴 Офлайн"
                print(f"📡 Початковий статус [{info['name']}]: {status_text}")
                if self._message is not None and self._message.online == current_online:
                    self._publish_message(timestamp)
                else:
                    self._events = [PowerEvent(timestamp, current_online)]
                    if self._message is not None:
                        self._message = None
                        self._save_message_state()
                return

            if not self._events or self._events[-1].online != current_online:
                self._events.append(PowerEvent(timestamp, current_online))

            # Статус змінився!
            if current_online != self.last_online_status:
                changed_at = self._events[-1].timestamp
                cutoff = timestamp - 2 * 24 * 3600
                while len(self._events) > 1 and self._events[1].timestamp < cutoff:
                    self._events.pop(0)

                if not current_online:
                    self._save_offline_since(changed_at)
                previous_message = self._message
                self._prepare_message(
                    current_online,
                    info["voltage"] if current_online else None,
                    datetime.fromtimestamp(changed_at, KYIV_TZ),
                )
                self.last_online_status = current_online
                self._finish_message(previous_message, changed_at)

                if self._on_status_change:
                    self._on_status_change(current_online)

            if self._message is not None:
                self._message.events = list(self._events)
            self._publish_message(timestamp)
        except Exception as e:
            print(f"⚠️ Помилка моніторингу: {e}")

    def _loop(self):
        """Цикл моніторингу."""
        print(f"📡 Моніторинг запущено (кожні {MONITOR_INTERVAL} сек)...")
        while self._running:
            self.check_and_notify()
            time.sleep(MONITOR_INTERVAL)

    def start(self):
        """Запуск моніторингу в окремому потоці."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Зупинка моніторингу."""
        self._running = False