import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import random
import requests
from flask import Flask, request, abort
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
UNSPLASH_ACCESS_KEY = os.environ.get('UNSPLASH_ACCESS_KEY')

if not TELEGRAM_TOKEN or not UNSPLASH_ACCESS_KEY:
    raise ValueError("TELEGRAM_TOKEN или UNSPLASH_ACCESS_KEY не заданы в переменных окружения")

# Список тем для случайного выбора
RANDOM_QUERIES = [
    'nature', 'city', 'abstract', 'people', 'animals', 'food',
    'travel', 'space', 'art', 'technology', 'mountain', 'ocean',
    'forest', 'sunset', 'flowers'
]

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)

# Функция получения случайной картинки с Unsplash
def get_random_unsplash_image(custom_query=None):
    query = custom_query or random.choice(RANDOM_QUERIES)
    url = f'https://api.unsplash.com/photos/random?query={query}&client_id={UNSPLASH_ACCESS_KEY}&orientation=landscape'
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        image_url = data.get('urls', {}).get('regular')
        return image_url
    except Exception as e:
        print(f"Ошибка при запросе к Unsplash: {e}")
        return None


# Обычный режим — упоминание бота
@bot.message_handler(func=lambda message: True)
def handle_mention(message):
    bot_username = bot.get_me().username
    if f'@{bot_username}' in message.text:
        markup = InlineKeyboardMarkup()
        button = InlineKeyboardButton('Отправить случайную картинку', callback_data='send_random_img')
        markup.add(button)
        bot.reply_to(message, 'Что хочешь сделать?', reply_markup=markup)


# Обработка нажатия кнопки в обычном режиме
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data == 'send_random_img':
        image_url = get_random_unsplash_image()
        if image_url:
            try:
                response = requests.get(image_url, timeout=10)
                response.raise_for_status()
                bot.send_photo(call.message.chat.id, response.content)
            except Exception as e:
                bot.reply_to(call.message, 'Не удалось скачать изображение :(')
                print(f"Ошибка отправки фото: {e}")
        else:
            bot.reply_to(call.message, 'Не удалось найти картинку. Попробуй позже!')


# Inline-режим — когда набирают @bot в любом чате
@bot.inline_handler(lambda query: True)
def inline_handler(inline_query):
    query_text = inline_query.query.strip()

    results = []

    # Если запрос пустой — одна случайная картинка
    if not query_text:
        image_url = get_random_unsplash_image()
        if image_url:
            results.append(
                telebot.types.InlineQueryResultPhoto(
                    id="random_default",
                    photo_url=image_url,
                    thumb_url=image_url,
                    title="Случайная красивая картинка",
                    description="Нажми, чтобы отправить"
                )
            )

    # Если есть текст — используем его как запрос к Unsplash
    else:
        image_url = get_random_unsplash_image(query_text)
        if image_url:
            results.append(
                telebot.types.InlineQueryResultPhoto(
                    id="query_result",
                    photo_url=image_url,
                    thumb_url=image_url,
                    title=f"По запросу: {query_text}",
                    description="Отправить в чат"
                )
            )

    # Отвечаем Telegram
    if results:
        bot.answer_inline_query(inline_query.id, results, cache_time=1)
    else:
        bot.answer_inline_query(inline_query.id, [])


# Flask-приложение для webhook
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
    return 'Bot is running', 200


#if __name__ == '__main__':
    # Только для локального тестирования
 #   print("Запуск в режиме разработки (локально)")
 #   app.run(host='0.0.0.0', port=5000, debug=True)