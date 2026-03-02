import telebot
import os
from dotenv import load_dotenv

load_dotenv()
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Очищаем старый webhook (очень важно!)
bot.remove_webhook()

# Твой реальный URL с Render + путь с токеном
webhook_url = 'https://tgbotrandompic.onrender.com/' + TELEGRAM_TOKEN

success = bot.set_webhook(url=webhook_url)
if success:
    print(f"Webhook успешно установлен на: {webhook_url}")
    # Проверь сразу
    info = bot.get_webhook_info()
    print("Текущая информация о webhook:", info)
else:
    print("Ошибка установки webhook!")