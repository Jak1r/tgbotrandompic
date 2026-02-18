import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import random
import requests
from flask import Flask, request, abort
from dotenv import load_dotenv

# Загружаем env-переменные
load_dotenv()

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
UNSPLASH_ACCESS_KEY = os.environ.get('UNSPLASH_ACCESS_KEY')

# Список случайных тем
RANDOM_QUERIES = ['nature', 'city', 'abstract', 'people', 'animals', 'food', 'travel', 'space', 'art', 'technology']

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)  # threaded=False для Render free

# Функция для случайного изображения
def get_random_unsplash_image():
    query = random.choice(RANDOM_QUERIES)
    url = f'https://api.unsplash.com/photos/random?query={query}&client_id={UNSPLASH_ACCESS_KEY}'
    response = requests.get(url)
    if response.status_code != 200:
        return None
    data = response.json()
    image_url = data.get('urls', {}).get('regular')
    if not image_url:
        return None
    return image_url

# Обработчик упоминания
@bot.message_handler(func=lambda message: True)
def handle_mention(message):
    bot_username = bot.get_me().username
    if f'@{bot_username}' in message.text:
        markup = InlineKeyboardMarkup()
        button = InlineKeyboardButton('Отправить случайную картинку', callback_data='send_random_img')
        markup.add(button)
        bot.reply_to(message, 'Что хочешь сделать?', reply_markup=markup)

# Обработчик кнопки
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data == 'send_random_img':
        image_url = get_random_unsplash_image()
        if image_url:
            response = requests.get(image_url)
            if response.status_code == 200:
                bot.send_photo(call.message.chat.id, response.content)
            else:
                bot.reply_to(call.message, 'Не удалось скачать изображение :(')
        else:
            bot.reply_to(call.message, 'Не удалось найти картинку. Попробуй позже!')

# Flask app
app = Flask(__name__)

@app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return 'OK', 200
    else:
        abort(403)

@app.route('/')
def index():
    return 'Telegram bot is alive!', 200

# if __name__ == '__main__':
    # Для локального теста (закомментируй на Render)
    # app.run(host='0.0.0.0', port=5000, debug=True)
