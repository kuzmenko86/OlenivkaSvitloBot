from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_main_keyboard() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⚡ Шо по електриці?", callback_data="electricity"))
    markup.add(InlineKeyboardButton("🌡️ Шо по температурі?", callback_data="temperature"))
    markup.add(InlineKeyboardButton("📅 Шо по графіках?", callback_data="schedule"))
    markup.add(InlineKeyboardButton("⏰ Це давно уже так?", callback_data="last_change"))
    return markup