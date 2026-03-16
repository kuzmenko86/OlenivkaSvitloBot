from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import TELEGRAM_BOT_USERNAME


def get_main_keyboard() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⚡ Шо по електриці?", callback_data="electricity"))
    markup.add(InlineKeyboardButton("🌡️ Температура на нижніх дачах?", callback_data="temperature"))
    markup.add(InlineKeyboardButton("📅 Покажи графік", callback_data="schedule"))
    #markup.add(InlineKeyboardButton("⏰ Остання зміна статусу?", callback_data="last_change"))
    return markup


def get_group_keyboard() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(
        "🤖 Тисни тут \n щоб перейти в бот \n і бачити більше деталей",
        url=f"https://t.me/{TELEGRAM_BOT_USERNAME}?start=menu",
    ))
    return markup