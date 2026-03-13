import os
from dotenv import load_dotenv

load_dotenv()

TUYA_ACCESS_ID = os.getenv("TUYA_ACCESS_ID")
TUYA_ACCESS_SECRET = os.getenv("TUYA_ACCESS_SECRET")
TUYA_BASE_URL = os.getenv("TUYA_BASE_URL", "https://openapi.tuyaeu.com")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Девайс для моніторингу електрики (перевірка кожні 15 сек)
ELECTRICITY_DEVICE_ID = os.getenv("ELECTRICITY_DEVICE_ID")
# Девайс для температури (тільки за запитом)
TEMPERATURE_DEVICE_ID = os.getenv("TEMPERATURE_DEVICE_ID")

# Інтервал перевірки електрики (секунди)
MONITOR_INTERVAL = int(os.getenv("MONITOR_INTERVAL", "30"))

# DTEK графік
DTEK_CITY = os.getenv("DTEK_CITY", "Забір")
DTEK_STREET = os.getenv("DTEK_STREET", "Перемоги")
DTEK_HOUSE_NUM = os.getenv("DTEK_HOUSE_NUM", "21")
SCHEDULE_MONITOR_INTERVAL = int(os.getenv("SCHEDULE_MONITOR_INTERVAL", "1800"))  # 30 хв