import threading
import time
from dtek_schedule import DtekScheduleService


class ScheduleMonitor:
    """
    Раз на N секунд оновлює графік у фоні.
    При натисканні кнопки повертає вже готовий результат з кешу.
    """

    def __init__(self, bot, chat_id: str, service: DtekScheduleService, interval_sec: int = 900):
        self.bot = bot
        self.chat_id = chat_id
        self.service = service
        self.interval_sec = interval_sec

        # Кеш
        self._cached_payload: dict | None = None
        self._last_signature: str | None = None
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
            current_signature = payload.get("signature")

            with self._lock:
                # Якщо графік змінився — шлемо повідомлення
                if self._last_signature is not None and current_signature != self._last_signature:
                    text = payload.get("telegram_text", "⚠️ Даних немає.")
                    self.bot.send_message(
                        self.chat_id,
                        f"📣 *Графік змінився*\n\n{text}",
                        parse_mode="Markdown",
                    )
                    print("📨 Надіслано оновлення графіка")

                self._cached_payload = payload
                self._last_signature = current_signature

                from datetime import datetime
                import pytz
                kyiv = pytz.timezone("Europe/Kyiv")
                self._last_updated = datetime.now(kyiv).strftime("%d.%m %H:%M")

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