from datetime import datetime
import pytz

KYIV_TZ = pytz.timezone("Europe/Kyiv")


def is_night_kyiv() -> bool:
    """True якщо в Києві зараз ніч (22:00 - 08:00)."""
    hour = datetime.now(KYIV_TZ).hour
    return hour >= 22 or hour < 8


def kyiv_now() -> datetime:
    """Повертає поточний час у Києві."""
    return datetime.now(KYIV_TZ)
