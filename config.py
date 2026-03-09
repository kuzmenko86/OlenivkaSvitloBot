import os
from dotenv import load_dotenv

load_dotenv()

TUYA_ACCESS_ID = os.getenv("TUYA_ACCESS_ID")
TUYA_ACCESS_SECRET = os.getenv("TUYA_ACCESS_SECRET")
TUYA_BASE_URL = os.getenv("TUYA_BASE_URL", "https://openapi.tuyaeu.com")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Девайс для моніторингу електрики (перевірка кожні 15 сек)
ELECTRICITY_DEVICE_ID = "bf70d61101eed4bb33ozul"

# Девайс для температури (тільки за запитом)
TEMPERATURE_DEVICE_ID = "bf1a175a6afde53ff4g0jn"

# Інтервал перевірки електрики (секунди)
MONITOR_INTERVAL = 15