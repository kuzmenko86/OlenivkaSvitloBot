import telebot

#python3 main.py

TOKEN = '8703561563:AAEStEQJ8Zwz3sMbpMpIgeYhuU3J5Q1eklg'
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def send_welcome(msg):
    bot.reply_to(msg, "Привіт! Я TeOlenBot 🤖")

@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.reply_to(message, message.text)

print("Бот запущено...")
bot.infinity_polling()