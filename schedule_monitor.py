import threading
import time
from dtek_schedule import DtekScheduleService
from keyboards import get_group_keyboard
from utils import kyiv_now


class ScheduleMonitor:
    """
    Раз на N секунд оновлює графік у фоні.
    При натисканні кнопки повертає вже готовий результат з кешу.
    """

    def __init__(self, bot, chat_id: str, service: DtekScheduleService, interval_sec: int = 1800):
        self.bot = bot
        self.chat_id = chat_id
        self.service = service
        self.interval_sec = interval_sec

        # Кеш
        self._cached_payload: dict | None = None
        self._last_today_signature: str | None = None
        self._last_tomorrow_signature: str | None = None
        self._has_previous_payload = False
        self._last_updated: str = "ще не оновлювалось"
        self._lock = threading.Lock()
        self._running = False
        self._thread = None

    def get_cached_text(self) -> str:
        """
        Повертає останній збережений текст графіка.
        Викликається при натисканні кнопки — миттєво, без запиту на сайт.
        """
        with self._lock:
            if self._cached_payload is None:
                return "⏳ Графік ще збирається, спробуй через хвилину..."
            text = self._cached_payload.get("telegram_text", "⚠️ Даних по графіку немає.")
            return f"{text}\n\n🔄 Оновлено: {self._last_updated}"

    def _refresh(self):
        """
        Завантажує свіжий графік з сайту і оновлює кеш.
        """
        try:
            print("📅 Оновлюю графік...")
            payload = self.service.get_payload()
            current_today_signature = payload.get("today_signature")
            current_tomorrow_signature = payload.get("tomorrow_signature")

            with self._lock:
                today_changed = (
                    self._has_previous_payload
                    and current_today_signature != self._last_today_signature
                )
                tomorrow_changed = (
                    self._has_previous_payload
                    and current_tomorrow_signature != self._last_tomorrow_signature
                )

                if today_changed or tomorrow_changed:
                    text = payload.get("telegram_text", "⚠️ Даних немає.")
                    title = "📣 *Графік змінився*" if today_changed else "📣 *Графік на завтра змінився*"
                    self.bot.send_message(
                        self.chat_id,
                        f"{title}\n\n{text}",
                        parse_mode="Markdown",
                        reply_markup=get_group_keyboard(),
                        disable_notification=True,
                    )
                    print("📨 Надіслано оновлення графіка")

                self._cached_payload = payload
                self._last_today_signature = current_today_signature
                self._last_tomorrow_signature = current_tomorrow_signature
                self._has_previous_payload = True
                self._last_updated = kyiv_now().strftime("%d.%m %H:%M")

            print(f"✅ Графік оновлено о {self._last_updated}")

        except Exception as e:
            print(f"⚠️ Помилка оновлення графіка: {e}")

    def _loop(self):
        print(f"📅 Моніторинг графіка запущено (кожні {self.interval_sec} сек)...")
        while self._running:
            self._refresh()
            time.sleep(self.interval_sec)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False