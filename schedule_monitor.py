import threading
import time
from dtek_schedule import DtekScheduleService


class ScheduleMonitor:
    """
    Раз на N секунд перевіряє графік.
    Якщо графік змінився — шле повідомлення в Telegram.
    """

    def __init__(self, bot, chat_id: str, service: DtekScheduleService, interval_sec: int = 3600):
        self.bot = bot
        self.chat_id = chat_id
        self.service = service
        self.interval_sec = interval_sec
        self.last_signature = None
        self._running = False
        self._thread = None

    def check_and_notify(self):
        try:
            payload = self.service.get_payload()
            current_signature = payload.get("signature")
            text = payload.get("telegram_text", "⚠️ Даних по графіку немає.")

            # Перша ініціалізація — не шлемо, тільки запам'ятовуємо
            if self.last_signature is None:
                self.last_signature = current_signature
                print("📅 Початковий стан графіка збережено")
                return

            if current_signature != self.last_signature:
                self.last_signature = current_signature
                self.bot.send_message(
                    self.chat_id,
                    f"📣 *Графік змінився*\n\n{text}",
                    parse_mode="Markdown",
                )
                print("📨 Надіслано оновлення графіка")
        except Exception as e:
            print(f"⚠️ Помилка моніторингу графіка: {e}")

    def _loop(self):
        print(f"📅 Моніторинг графіка запущено (кожні {self.interval_sec} сек)...")
        while self._running:
            self.check_and_notify()
            time.sleep(self.interval_sec)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False