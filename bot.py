import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import random
import requests
from flask import Flask, request, abort
from dotenv import load_dotenv
import time

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

# Авто-установка webhook при запуске
webhook_path = f'/{TELEGRAM_TOKEN}'
webhook_url = f'https://{os.environ.get("RENDER_EXTERNAL_HOSTNAME", "tgbotrandompic.onrender.com")}{webhook_path}'

try:
    current_webhook = bot.get_webhook_info()
    if current_webhook.url != webhook_url:
        bot.remove_webhook()
        time.sleep(1)  # пауза для Telegram
        success = bot.set_webhook(url=webhook_url)
        if success:
            print(f"Webhook успешно установлен на: {webhook_url}")
        else:
            print("Не удалось установить webhook")
    else:
        print(f"Webhook уже установлен правильно: {webhook_url}")
except Exception as e:
    print(f"Ошибка при установке webhook: {e}")

# Функция получения случайной картинки с Unsplash
def get_random_unsplash_image(custom_query=None):
    query = custom_query or random.choice(RANDOM_QUERIES)
    url = f'https://api.unsplash.com/photos/random?query={query}&client_id={UNSPLASH_ACCESS_KEY}&orientation=landscape'
    
    try:
        response = requests.get(url, timeout=5)  # уменьшил таймаут
        response.raise_for_status()
        data = response.json()
        image_url = data.get('urls', {}).get('regular')
        print(f"Unsplash вернул URL: {image_url}")  # лог для отладки
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
    print(f"Получен inline-запрос: '{inline_query.query}' от пользователя {inline_query.from_user.id}")  # лог для отладки

    query_text = inline_query.query.strip()

    results = []

    # Всегда добавляем 2-3 результата для разнообразия, даже если запрос пустой
    for i in range(3):  # 3 картинки
        custom_query = query_text if query_text else None
        image_url = get_random_unsplash_image(custom_query)
        if image_url:
            result_id = f"res_{i}_{random.randint(1, 10000)}"  # уникальный ID
            title = "Случайная картинка из Unsplash" if not query_text else f"По запросу: {query_text} ({i+1})"
            results.append(
                telebot.types.InlineQueryResultPhoto(
                    id=result_id,
                    photo_url=image_url,
                    thumb_url=image_url.replace('w=1080', 'w=200'),  # уменьшенная превью для скорости
                    title=title,
                    description="Нажми, чтобы отправить в чат"
                )
            )

    # Отвечаем Telegram
    try:
        if results:
            bot.answer_inline_query(inline_query.id, results, cache_time=60, is_personal=True)  # кэш 1 мин, персональный
            print(f"Отправлено {len(results)} результатов для inline-запроса '{query_text}'")
        else:
            bot.answer_inline_query(inline_query.id, [])
            print("Отправлен пустой результат для inline-запроса — не найдено картинок")
    except Exception as e:
        print(f"Ошибка при ответе на inline-запрос: {e}")

# Flask-приложение для webhook
app = Flask(__name__)

@app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    print("Получен POST-запрос от Telegram!")  # Лог для отладки
    print(request.headers)
    print(request.get_data(as_text=True))  # Сырой JSON

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
#    # Только для локального тестирования
#    print("Запуск в режиме разработки (локально)")
#    app.run(host='0.0.0.0', port=5000, debug=True)