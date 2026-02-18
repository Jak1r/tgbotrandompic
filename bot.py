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
PORT = int(os.environ.get('PORT', 10000))

if not TELEGRAM_TOKEN or not UNSPLASH_ACCESS_KEY:
    raise ValueError("TELEGRAM_TOKEN или UNSPLASH_ACCESS_KEY не заданы в переменных окружения")

# Список тем для случайного выбора
RANDOM_QUERIES = [
    'nature', 'city', 'abstract', 'people', 'animals', 'food',
    'travel', 'space', 'art', 'technology', 'mountain', 'ocean',
    'forest', 'sunset', 'flowers'
]

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)

# Flask-приложение для webhook
app = Flask(__name__)

# Авто-установка webhook при запуске
def setup_webhook():
    webhook_path = f'/{TELEGRAM_TOKEN}'
    hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "tgbotrandompic.onrender.com")
    webhook_url = f'https://{hostname}{webhook_path}'
    
    try:
        current_webhook = bot.get_webhook_info()
        if current_webhook.url != webhook_url:
            bot.remove_webhook()
            time.sleep(1)
            success = bot.set_webhook(url=webhook_url)
            if success:
                print(f"✅ Webhook успешно установлен на: {webhook_url}")
            else:
                print("❌ Не удалось установить webhook")
        else:
            print(f"✅ Webhook уже установлен правильно: {webhook_url}")
    except Exception as e:
        print(f"❌ Ошибка при установке webhook: {e}")

# Функция получения случайной картинки с Unsplash
def get_random_unsplash_image(custom_query=None):
    query = custom_query or random.choice(RANDOM_QUERIES)
    url = f'https://api.unsplash.com/photos/random?query={query}&client_id={UNSPLASH_ACCESS_KEY}&orientation=landscape'
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Используем разные размеры из Unsplash API
        image_url = data.get('urls', {}).get('regular')  # Основное изображение
        thumb_url = data.get('urls', {}).get('thumb')     # Маленькое превью (200x200)
        
        print(f"✅ Unsplash вернул URL: {image_url}")
        print(f"✅ Thumbnail URL: {thumb_url}")
        
        return image_url, thumb_url
    except Exception as e:
        print(f"❌ Ошибка при запросе к Unsplash: {e}")
        return None, None

# Команда /start
@bot.message_handler(commands=['start'])
def start_command(message):
    bot.reply_to(message, 
        'Привет! Я бот для отправки случайных картинок из Unsplash.\n\n'
        '🔹 Упомяни меня в чате для кнопки с картинкой\n'
        '🔹 Используй меня в inline-режиме: напиши мой юзернейм в любом чате\n'
        '🔹 Можешь добавить запрос после имени (например: @bot cats)'
    )

# Обычный режим — упоминание бота
@bot.message_handler(func=lambda message: True)
def handle_mention(message):
    bot_username = bot.get_me().username
    if f'@{bot_username}' in message.text:
        markup = InlineKeyboardMarkup()
        button = InlineKeyboardButton('📸 Отправить случайную картинку', callback_data='send_random_img')
        markup.add(button)
        bot.reply_to(message, 'Что хочешь сделать?', reply_markup=markup)

# Обработка нажатия кнопки в обычном режиме
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data == 'send_random_img':
        bot.answer_callback_query(call.id, "Загружаю картинку...")
        image_url, _ = get_random_unsplash_image()
        if image_url:
            try:
                bot.send_photo(call.message.chat.id, image_url)
            except Exception as e:
                bot.send_message(call.message.chat.id, '❌ Не удалось скачать изображение')
                print(f"❌ Ошибка отправки фото: {e}")
        else:
            bot.send_message(call.message.chat.id, '❌ Не удалось найти картинку. Попробуй позже!')

# Inline-режим — когда набирают @bot в любом чате
@bot.inline_handler(lambda query: True)
def inline_handler(inline_query):
    print(f"📥 Получен inline-запрос: '{inline_query.query}' от пользователя {inline_query.from_user.id}")

    query_text = inline_query.query.strip()
    results = []

    # Генерируем ОДНУ картинку
    try:
        custom_query = query_text if query_text else None
        image_url, thumb_url = get_random_unsplash_image(custom_query)
        
        if image_url and thumb_url:
            result_id = f"{int(time.time())}_{random.randint(1000, 9999)}"
            title = "Случайная картинка из Unsplash" if not query_text else f"Картинка: {query_text}"
            
            results.append(
                telebot.types.InlineQueryResultPhoto(
                    id=result_id,
                    photo_url=image_url,
                    thumbnail_url=thumb_url,
                    title=title,
                    description="Нажми, чтобы отправить"
                )
            )
            print(f"✅ Создан результат: {result_id}")
        else:
            print(f"⚠️ Не удалось получить картинку")
    except Exception as e:
        print(f"❌ Ошибка при создании результата: {e}")

    # Отвечаем Telegram
    try:
        if results:
            bot.answer_inline_query(
                inline_query.id, 
                results, 
                cache_time=1,  # Минимальный кэш для максимальной случайности
                is_personal=True
            )
            print(f"✅ Отправлен результат для inline-запроса '{query_text}'")
        else:
            bot.answer_inline_query(inline_query.id, [], cache_time=1)
            print(f"⚠️ Отправлен пустой результат - не удалось получить картинку")
    except Exception as e:
        print(f"❌ Ошибка при ответе на inline-запрос: {e}")

# Роуты Flask
@app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    print("📨 Получен POST-запрос от Telegram!")
    
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        try:
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return 'OK', 200
        except Exception as e:
            print(f"❌ Ошибка обработки update: {e}")
            return 'Error', 500
    else:
        abort(403)

@app.route('/')
def index():
    return '🤖 Bot is running!', 200

@app.route('/health')
def health():
    return 'OK', 200

# Инициализация при запуске
if __name__ != '__main__':
    setup_webhook()