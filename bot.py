import time
from datetime import datetime
import pytz
import telebot
from telebot.apihelper import ApiTelegramException
from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TELEGRAM_OWNER_ID,
    TEMPERATURE_DEVICE_ID,
    ELECTRICITY_DEVICE_ID,
    DTEK_CITY,
    DTEK_STREET,
    DTEK_HOUSE_NUM,
    SCHEDULE_MONITOR_INTERVAL,
)
from tuya_api import TuyaAPI
from monitor import ElectricityMonitor
from dtek_schedule import DtekScheduleService
from schedule_monitor import ScheduleMonitor
from keyboards import get_main_keyboard, get_group_keyboard
from utils import is_night_kyiv

# Як запустити:
# source venv/bin/activate
# python3 bot.py

# Створюємо екземпляр бота з токеном з .env
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# Створюємо екземпляр API Tuya для запитів до девайсів
tuya = TuyaAPI()
schedule_service = DtekScheduleService(
    city=DTEK_CITY,
    street=DTEK_STREET,
    house_num=DTEK_HOUSE_NUM,
)

# Тут зберігаємо інформацію про останню зміну статусу електрики.
# Ці змінні оновлюються з monitor.py коли статус змінюється.
# status_change_time — timestamp (число) коли змінився статус
# status_change_type — "online" (дали світло) або "offline" (вимкнули)
status_change_time = None
status_change_type = None


# ==================== ХЕЛПЕРИ ====================
# Допоміжні функції, які формують клавіатуру та тексти повідомлень.
# Винесені окремо, щоб не дублювати код у кожному обробнику.

def _safe_edit(call, text, markup=None):
    """Редагує повідомлення, ігноруючи помилку 'message is not modified'."""
    try:
        bot.edit_message_text(
            text, call.message.chat.id, call.message.message_id,
            parse_mode="Markdown", reply_markup=markup or get_main_keyboard(),
        )
    except ApiTelegramException as e:
        if "message is not modified" not in str(e):
            raise


def electricity_text():
    """
    Запитує Tuya API і формує текст про стан електрики.
    Повертає готовий рядок з Markdown-розміткою.
    """
    info = tuya.get_electricity_info(ELECTRICITY_DEVICE_ID)
    status = "🟢 Є!, ну і слава Богу!" if info["online"] else "🔴 Відсутня, (йо🤬на русня)"
    return (
        f"⚡ *Наявність електрики:*\n"
        f"\n{status}\n\n"

    )

def temp_icon(raw_temp):
    """Іконка + температура: ❄️ < 0 | 🍃 0–24 | 🥵 25+"""
    try:
        t = float(raw_temp)
    except (TypeError, ValueError):
        return f"🌡️ {raw_temp}°C"

    if t < 0:
        icon = "❄️"
    elif t < 25:
        icon = "🍃"
    else:
        icon = "🥵"
    return f"{icon} {t:g}°C"

def temperature_text():
    """
    Запитує Tuya API і формує текст про температуру, вологість і батарейку.
    Використовує temp_icon() для красивого відображення температури.
    Додає поточну дату і час (Київ), щоб було видно коли саме зроблено запит.
    Повертає готовий рядок з Markdown-розміткою.
    """
    info = tuya.get_temperature_info(TEMPERATURE_DEVICE_ID)
    online = "🟢 шось там міряє" if info["online"] else "🔴 вирубився"

    # Витягуємо окремі параметри зі статусу девайса
    s = info.get("status", {})
    temperature = s.get("va_temperature", "—")
    humidity = s.get("va_humidity", "—")
    battery = s.get("va_battery", "—")

    # Назви місяців українською для красивого відображення дати
    months_ua = {
        1: "січня", 2: "лютого", 3: "березня", 4: "квітня",
        5: "травня", 6: "червня", 7: "липня", 8: "серпня",
        9: "вересня", 10: "жовтня", 11: "листопада", 12: "грудня",
    }
    
    # Київський час
    kyiv_tz = pytz.timezone("Europe/Kyiv")
    now = datetime.now(kyiv_tz)
    date_str = f"{now.day} {months_ua[now.month]} {now.strftime('%H:%M')}"

    return (
        f"🌡️ *Температура на зараз ({date_str}):*\n\n"
        f"Статус термометра: {online}\n\n"
        f"🌡️ Температура: *{temp_icon(temperature)}*\n"
        f"💧 Вологість: *{humidity}%*\n\n"
        f"🔋 Батарейка термометра: *{battery}%*"
    )


def last_change_text():
    """
    Формує текст про останню зміну статусу електрики.
    Якщо бот щойно запустився і змін ще не було — каже що даних немає.
    Інакше показує час і тип зміни (дали / вимкнули) у київському часі.
    """
    if status_change_time is None:
        return "⏰ *Зміна статусу*\n\nДаних про зміну статусу ще немає. Чекаємо..."

    # Конвертуємо timestamp в київський час
    kyiv_tz = pytz.timezone("Europe/Kyiv")
    kyiv_time = datetime.fromtimestamp(status_change_time, tz=kyiv_tz)
    time_str = kyiv_time.strftime("%H:%M")

    if status_change_type == "online":
        return f"⏰ *Остання зміна:*\n\n💡 Дали світло о *{time_str}*"
    else:
        return f"⏰ *Остання зміна:*\n\n🔴 Вимкнули світло о *{time_str}*, Чекаємо..."


# ==================== КОМАНДИ ====================
# Обробники текстових команд, які юзер може написати в чат.


@bot.message_handler(commands=["start"])
def cmd_start(message):
    """
    Команда /start — вітальне повідомлення при першому запуску бота.
    Відразу показує клавіатуру з кнопками.
    В групі — тільки привітання без кнопок.
    """
    # Якщо це група — не показуємо меню
    if message.chat.type != "private":
        return

    bot.reply_to(
        message,
        "Привіт! Я Оленівський Котик-Ботик 🤖\n\n"
        "📡 Моніторю електроенергію автоматично кожні 5 хвилин.\n"
        "Я сам буду повідомляти в чат (t.me/OlenivkaSvitlo) коли світло з'явиться або зникне.\n\n"
        "👇 Ну, а поки натискай кнопочки нижче, щоб перевірити інформацію прямо зараз:",
        reply_markup=get_main_keyboard(),
    )


@bot.message_handler(commands=["chatid"])
def cmd_chatid(message):
    """
    Команда /chatid — показує Chat ID.
    Потрібна, щоб дізнатися ID і записати його в .env файл
    для автоматичних повідомлень моніторингу.
    """
    chat_id = message.chat.id
    chat_type = message.chat.type  # "private", "group", "supergroup"

    if chat_type == "private":
        text = (
            f"👤 Твій особистий Chat ID: `{chat_id}`\n\n"
            f"⚠️ Якщо хочеш, щоб *усі в групі* бачили повідомлення — "
            f"напиши /chatid *в груповому чаті* і використай той ID."
        )
    else:
        text = (
            f"👥 Chat ID цієї групи: `{chat_id}`\n\n"
            f"✅ Встав це значення в `TELEGRAM_CHAT_ID` в `.env`, "
            f"і всі учасники групи будуть бачити повідомлення."
        )

    bot.reply_to(message, text, parse_mode="Markdown")


@bot.message_handler(commands=["say"])
def cmd_say(message):
    """
    Команда /say — дозволяє власнику надіслати повідомлення в групу від імені бота.
    Використання: /say Привіт усім!
    """
    if not TELEGRAM_OWNER_ID or str(message.from_user.id) != TELEGRAM_OWNER_ID:
        return

    if message.chat.type != "private":
        return

    text = message.text.partition("/say")[2].strip()
    if not text:
        bot.reply_to(message, "Напиши текст після /say\nНаприклад: `/say Привіт усім!`", parse_mode="Markdown")
        return

    if TELEGRAM_CHAT_ID:
        bot.send_message(TELEGRAM_CHAT_ID, text, parse_mode="Markdown", reply_markup=get_group_keyboard(), disable_notification=is_night_kyiv())
        bot.reply_to(message, "✅ Надіслано в групу!")
    else:
        bot.reply_to(message, "❌ TELEGRAM_CHAT_ID не задано")


# ==================== КНОПКИ (CALLBACKS) ====================
# Обробники натискань інлайн-кнопок.
# Коли юзер тисне кнопку — Telegram шле callback з відповідним data.
# Ми ловимо цей callback і оновлюємо текст повідомлення (edit_message_text),
# щоб не спамити новими повідомленнями, а просто міняти вміст існуючого.


@bot.callback_query_handler(func=lambda call: call.data == "electricity")
def cb_electricity(call):
    """
    Кнопка "Шо по електриці?" — показує онлайн/офлайн + напругу.
    Замінює текст поточного повідомлення на актуальний статус.
    """
    try:
        text = electricity_text()
        _safe_edit(call, text)
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Помилка: {e}", show_alert=True)


@bot.callback_query_handler(func=lambda call: call.data == "temperature")
def cb_temperature(call):
    """
    Кнопка "Шо по температурі?" — показує температуру, вологість, батарейку.
    Замінює текст поточного повідомлення на актуальні дані з термометра.
    """
    try:
        text = temperature_text()
        _safe_edit(call, text)
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Помилка: {e}", show_alert=True)


@bot.callback_query_handler(func=lambda call: call.data == "last_change")
def cb_last_change(call):
    """
    Кнопка "Це давно уже так?" — показує коли востаннє змінився статус.
    Наприклад: "Дали світло о 14:32" або "Вимкнули світло о 03:15".
    """
    _safe_edit(call, last_change_text())


@bot.callback_query_handler(func=lambda call: call.data == "schedule")
def cb_schedule(call):
    """
    Кнопка "Шо по графіках?" — показує поточний графік ДТЕК по адресі.
    """
    try:
        bot.answer_callback_query(call.id)
        text = schedule_monitor.get_cached_text()
        _safe_edit(call, text)
    except Exception as e:
        short_err = str(e)[:100]
        bot.send_message(
            call.message.chat.id,
            f"❌ Помилка графіка:\n{short_err}",
            reply_markup=get_main_keyboard(),
        )


# ==================== ЗАПУСК ====================

if __name__ == "__main__":
    if TELEGRAM_CHAT_ID:
        def on_status_change(is_online):
            global status_change_time, status_change_type
            status_change_time = time.time()
            status_change_type = "online" if is_online else "offline"

        monitor = ElectricityMonitor(bot, TELEGRAM_CHAT_ID, on_status_change=on_status_change)
        monitor.start()
        print("📡 Моніторинг електрики запущено")

        schedule_monitor = ScheduleMonitor(
            bot=bot,
            chat_id=TELEGRAM_CHAT_ID,
            service=schedule_service,
            interval_sec=SCHEDULE_MONITOR_INTERVAL,
        )
        schedule_monitor.start()
        print("📅 Моніторинг графіка запущено")
    else:
        print("⚠️ TELEGRAM_CHAT_ID не задано! Напиши боту /chatid")

    print("🤖 Бот запущено...")
    bot.infinity_polling()