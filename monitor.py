import os
import threading
import time
from tuya_api import TuyaAPI
from config import ELECTRICITY_DEVICE_ID, MONITOR_INTERVAL
from dtek_schedule import DtekScheduleService
from keyboards import get_group_keyboard
from utils import is_night_kyiv, kyiv_now

OFFLINE_SINCE_FILE = os.path.join(os.path.dirname(__file__), "offline_since.txt")
SCHEDULE_TOLERANCE_MINUTES = 30


class ElectricityMonitor:
    def __init__(
        self,
        bot,
        chat_id: str,
        schedule_service: DtekScheduleService,
        on_status_change=None,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.schedule_service = schedule_service
        self.tuya = TuyaAPI()
        self.device_id = ELECTRICITY_DEVICE_ID
        self.last_online_status = None
        self._on_status_change = on_status_change
        self._running = False
        self._thread = None

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
        total_min = int(seconds) // 60
        hours, minutes = divmod(total_min, 60)
        if hours > 0:
            return f"{hours} год {minutes} хв"
        return f"{minutes} хв"

    def _build_power_lost_message(self) -> str:
        try:
            payload = self.schedule_service.get_payload()
        except Exception as e:
            print(f"⚠️ Не вдалося перевірити графік після зникнення світла: {e}")
            return (
                "🔴 ⚠️ *Світло зникло!*\n\n"
                "Не вдалося перевірити, чи відповідає відключення графіку.\n\n"
                "Можете перевірити графік у боті."
            )

        planned_segment = self.schedule_service.find_planned_outage(
            payload,
            kyiv_now(),
            tolerance_minutes=SCHEDULE_TOLERANCE_MINUTES,
        )
        if planned_segment:
            segment_text = self.schedule_service.format_outage_segment(planned_segment)
            return (
                "🔴 ⚠️ *Світло зникло!*\n\n"
                f"У рамках планового відключення: *{segment_text}*\n\n"
                "Можете перевірити графік у боті."
            )

        schedule_text = payload.get("telegram_text", "⚠️ Даних по графіку немає.")
        return (
            "🔴 🔴 🔴 *Світло зникло!*\n\n"
            "*НЕ ЗА ГРАФІКОМ!*\n\n"
            f"{schedule_text}"
        )

    def check_and_notify(self):
        """Перевіряє статус і надсилає повідомлення якщо статус змінився."""
        try:
            info = self.tuya.get_electricity_info(self.device_id)
            current_online = info["online"]

            # Перша перевірка — просто запам'ятовуємо статус
            if self.last_online_status is None:
                self.last_online_status = current_online
                status_text = "🟢 Онлайн" if current_online else "🔴 Офлайн"
                print(f"📡 Початковий статус [{info['name']}]: {status_text}")
                return

            # Статус змінився!
            if current_online != self.last_online_status:
                self.last_online_status = current_online

                # Повідомляємо bot.py про зміну статусу
                if self._on_status_change:
                    self._on_status_change(current_online)

                if current_online:
                    # Світло дали ✅
                    voltage = info["voltage"]
                    duration_text = ""
                    offline_since = self._read_offline_since()
                    if offline_since:
                        duration_text = f"\n\n⏱ Світла не було: *{self._format_duration(time.time() - offline_since)}*"
                    self._clear_offline_since()
                    message = (
                        f"💡⚡ *Світло дали!*\n\n"
                        f"🔌 Напруга в мережі: *{voltage} Вольт*"
                        f"{duration_text}"
                    )
                else:
                    # Світло зникло ❌
                    self._save_offline_since(time.time())
                    message = self._build_power_lost_message()

                # Додаємо кнопку-посилання на бота
                self.bot.send_message(
                    self.chat_id,
                    message,
                    parse_mode="Markdown",
                    reply_markup=get_group_keyboard(),
                    disable_notification=is_night_kyiv(),
                )
                print(f"📨 Повідомлення надіслано: {'Світло дали' if current_online else 'Світло зникло'}")

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