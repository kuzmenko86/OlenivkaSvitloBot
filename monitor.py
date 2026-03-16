import threading
import time
from datetime import datetime
from tuya_api import TuyaAPI
from config import ELECTRICITY_DEVICE_ID, MONITOR_INTERVAL
from keyboards import get_group_keyboard


class ElectricityMonitor:
    def __init__(self, bot, chat_id: str):
        self.bot = bot
        self.chat_id = chat_id
        self.tuya = TuyaAPI()
        self.device_id = ELECTRICITY_DEVICE_ID
        self.last_online_status = None
        self._running = False
        self._thread = None

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

                # Оновлюємо глобальні змінні в bot.py
                import bot as bot_module
                bot_module.status_change_time = time.time()
                bot_module.status_change_type = "online" if current_online else "offline"

                if current_online:
                    # Світло дали ✅
                    voltage = info["voltage"]
                    message = (
                        f"💡⚡ *Світло дали!*\n\n"
                        f"🔌 Напруга в мережі: *{voltage} Вольт*"
                    )
                else:
                    # Світло зникло ❌
                    message = (
                        f"🔴💀 *Світло зникло!*\n\n"
                        #f"📱 {info['name']}\n"
                        f"Девайс перейшов в офлайн."
                    )

                # Додаємо кнопку-посилання на бота
                self.bot.send_message(
                    self.chat_id,
                    message,
                    parse_mode="Markdown",
                    reply_markup=get_group_keyboard(),
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