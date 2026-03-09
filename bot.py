import json
import time
from datetime import datetime
import pytz
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TEMPERATURE_DEVICE_ID,
    ELECTRICITY_DEVICE_ID,
)
from tuya_api import TuyaAPI
from monitor import ElectricityMonitor

# Як запустити:
# source venv/bin/activate
# python3 bot.py

# Створюємо екземпляр бота з токеном з .env
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# Створюємо екземпляр API Tuya для запитів до девайсів
tuya = TuyaAPI()

# Тут зберігаємо інформацію про останню зміну статусу електрики.
# Ці змінні оновлюються з monitor.py коли статус змінюється.
# status_change_time — timestamp (число) коли змінився статус
# status_change_type — "online" (дали світло) або "offline" (вимкнули)
status_change_time = None
status_change_type = None


# ==================== ХЕЛПЕРИ ====================
# Допоміжні функції, які формують клавіатуру та тексти повідомлень.
# Винесені окремо, щоб не дублювати код у кожному обробнику.


def get_keyboard():
    """
    Створює інлайн-клавіатуру з трьома кнопками.
    Ця клавіатура додається до кожного повідомлення бота,
    щоб користувач завжди міг натиснути потрібну кнопку.
    """
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⚡ Шо по електриці?", callback_data="electricity"))
    markup.add(InlineKeyboardButton("🌡️ Шо по температурі?", callback_data="temperature"))
    markup.add(InlineKeyboardButton("⏰ Це давно уже так?", callback_data="last_change"))
    return markup



def electricity_text():
    """
    Запитує Tuya API і формує текст про стан електрики.
    Повертає готовий рядок з Markdown-розміткою.
    """
    info = tuya.get_electricity_info(ELECTRICITY_DEVICE_ID)
    status = "🟢 Є!, ну і слава Богу!" if info["online"] else "🔴 Нема (й***на русня)"
    return (
        f"⚡ *Наявність електрики:*\n"
        f"{status}\n\n"
        f"🔌 Напруга: *{info['voltage']} В*\n\n"
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
    """
    bot.reply_to(
        message,
        "Привіт! Я Оленівський Котик-Ботик 🤖\n\n"
        "📡 Моніторю електроенергію автоматично.\n"
        "Я сам буду повідомляти коли світло з'явиться або зникне.\n\n"
        "👇 Ну, а поки жмакай кнопочки нижче:",
        reply_markup=get_keyboard(),
    )


@bot.message_handler(commands=["chatid"])
def cmd_chatid(message):
    """
    Команда /chatid — показує Chat ID користувача.
    Потрібна, щоб дізнатися свій ID і записати його в .env файл
    для автоматичних повідомлень моніторингу.
    """
    bot.reply_to(message, f"Твій Chat ID: `{message.chat.id}`", parse_mode="Markdown")


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
        bot.edit_message_text(
            text, call.message.chat.id, call.message.message_id,
            parse_mode="Markdown", reply_markup=get_keyboard(),
        )
    except Exception as e:
        # Показуємо помилку як спливаюче повідомлення (alert)
        bot.answer_callback_query(call.id, f"❌ Помилка: {e}", show_alert=True)


@bot.callback_query_handler(func=lambda call: call.data == "temperature")
def cb_temperature(call):
    """
    Кнопка "Шо по температурі?" — показує температуру, вологість, батарейку.
    Замінює текст поточного повідомлення на актуальні дані з термометра.
    """
    try:
        text = temperature_text()
        bot.edit_message_text(
            text, call.message.chat.id, call.message.message_id,
            parse_mode="Markdown", reply_markup=get_keyboard(),
        )
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Помилка: {e}", show_alert=True)


@bot.callback_query_handler(func=lambda call: call.data == "last_change")
def cb_last_change(call):
    """
    Кнопка "Це давно уже так?" — показує коли востаннє змінився статус.
    Наприклад: "Дали світло о 14:32" або "Вимкнули світло о 03:15".
    """
    text = last_change_text()
    bot.edit_message_text(
        text, call.message.chat.id, call.message.message_id,
        parse_mode="Markdown", reply_markup=get_keyboard(),
    )


# ==================== ЗАПУСК ====================

if __name__ == "__main__":
    # Запускаємо фоновий моніторинг електрики.
    # Він кожні N секунд перевіряє статус девайса через Tuya API.
    # Якщо статус змінився (було онлайн → стало офлайн або навпаки),
    # monitor.py сам відправить повідомлення в чат з кнопками.
    if TELEGRAM_CHAT_ID:
        monitor = ElectricityMonitor(bot, TELEGRAM_CHAT_ID)
        monitor.start()
        print("📡 Моніторинг електрики запущено")
    else:
        print("⚠️ TELEGRAM_CHAT_ID не задано! Напиши боту /chatid")

    # Запускаємо прослуховування повідомлень від Telegram.
    # infinity_polling() = безкінечний цикл, бот не зупиниться поки не вб'єш процес.
    print("🤖 Бот запущено...")
    bot.infinity_polling()