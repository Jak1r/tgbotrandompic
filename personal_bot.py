import os
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from flask import Flask, request
from dotenv import load_dotenv
import time
import threading
import sys
import traceback
import random
import requests
import re
from io import BytesIO
from datetime import datetime, timedelta
import pytz

# Импортируем общую логику
from shared_logic import *

load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
PORT = int(os.getenv('PORT', 8080))

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не задан")

print("🚀 Запуск personal бота...")
print(f"📸 API фото: {', '.join(available_apis) if 'available_apis' in dir() else 'не загружены'}")
print(f"🎭 Категории фраз: {list(PHRASES.keys()) if PHRASES else 'нет'}")

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
app = Flask(__name__)

# Временное хранилище для диалогов
user_states = {}

def create_main_keyboard():
    """Создает главную клавиатуру"""
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = KeyboardButton("🖼️ Случайное фото")
    btn2 = KeyboardButton("🎭 Случайный мем")
    btn3 = KeyboardButton("🎬 Случайная GIF")
    btn4 = KeyboardButton("🎲 Эмодзи дня")
    btn5 = KeyboardButton("📝 Текст на фото")
    btn6 = KeyboardButton("📖 Помощь")
    markup.add(btn1, btn2, btn3, btn4, btn5, btn6)
    return markup

def create_text_keyboard():
    """Создает клавиатуру для выбора текста со ВСЕМИ категориями"""
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    # Собираем все категории из PHRASES
    categories = list(PHRASES.keys()) if PHRASES else []
    
    buttons = []
    # Добавляем основные кнопки
    buttons.append(KeyboardButton("✏️ Свой текст"))
    buttons.append(KeyboardButton("🎲 Случайная фраза"))
    
    # Добавляем все категории
    for category in categories:
        buttons.append(KeyboardButton(f"🎭 Категория {category}"))
    
    buttons.append(KeyboardButton("◀️ Назад"))
    
    # Размещаем кнопки
    markup.add(*buttons)
    return markup

def send_photo_with_text(chat_id, text, photo_type='photo', query=None, count=1):
    """Отправляет фото/мем/GIF с текстом"""
    try:
        if photo_type == 'gif':
            for i in range(count):
                url = get_random_gif(query)
                if url:
                    if text:
                        full = add_text_to_gif(url, text)
                    else:
                        r = requests.get(url, timeout=10)
                        full = BytesIO(r.content)
                    
                    if full:
                        # Добавляем подпись для GIF
                        caption = f"GIF {i+1}" if count > 1 else ""
                        if caption:
                            caption += "\n\nPowered by GIPHY"
                        else:
                            caption = "Powered by GIPHY"
                        
                        bot.send_animation(chat_id, full, caption=caption)
                else:
                    bot.send_message(chat_id, "❌ GIF временно недоступны. Попробуйте позже.")
        
        elif photo_type == 'meme':
            for i in range(count):
                url, thumb = get_random_meme(query)
                if url:
                    if text:
                        full = add_text_to_image(url, text)
                    else:
                        r = requests.get(url, timeout=10)
                        full = BytesIO(r.content)
                    
                    if full:
                        bot.send_photo(chat_id, full, caption=f"Мем {i+1}" if count > 1 else None)
                else:
                    bot.send_message(chat_id, "❌ Мемы временно недоступны")
        
        else:  # фото
            for i in range(count):
                url, thumb = get_random_image(query)
                if url:
                    if text:
                        full = add_text_to_image(url, text)
                    else:
                        r = requests.get(url, timeout=10)
                        full = BytesIO(r.content)
                    
                    if full:
                        bot.send_photo(chat_id, full, caption=f"Фото {i+1}" if count > 1 else None)
                else:
                    bot.send_message(chat_id, "❌ Фото временно недоступны")
                    
    except Exception as e:
        bot.send_message(chat_id, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """Приветственное сообщение"""
    help_text = (
        '🎨 Привет! Я бот для случайных картинок.\n\n'
        '📸 Доступные команды:\n'
        '• /start, /help - это сообщение\n'
        '• /photo - случайное фото\n'
        '• /meme - случайный мем\n'
        '• /gif - случайная GIF\n'
        '• /emoji - эмодзи дня\n'
        '• /text "текст" - фото с текстом\n\n'
        'Или просто пользуйся кнопками ниже! 👇'
    )
    bot.send_message(message.chat.id, help_text, reply_markup=create_main_keyboard())

# ========== ОБРАБОТЧИКИ КНОПОК ==========

@bot.message_handler(func=lambda message: message.text == "🖼️ Случайное фото")
def handle_random_photo(message):
    bot.send_message(message.chat.id, "🔍 Ищу случайное фото...")
    send_photo_with_text(message.chat.id, None, 'photo')

@bot.message_handler(func=lambda message: message.text == "🎭 Случайный мем")
def handle_random_meme(message):
    bot.send_message(message.chat.id, "🔍 Ищу случайный мем...")
    send_photo_with_text(message.chat.id, None, 'meme')

@bot.message_handler(func=lambda message: message.text == "🎬 Случайная GIF")
def handle_random_gif(message):
    bot.send_message(message.chat.id, "🔍 Ищу случайную GIF...")
    send_photo_with_text(message.chat.id, None, 'gif')

@bot.message_handler(func=lambda message: message.text == "🎲 Эмодзи дня")
def handle_emoji(message):
    emoji = get_user_emoji(message.from_user.id)
    phrase = random.choice(EMOJI_PHRASES).format(emoji=emoji)
    bot.send_message(message.chat.id, phrase)

@bot.message_handler(func=lambda message: message.text == "📝 Текст на фото")
def handle_text_menu(message):
    bot.send_message(message.chat.id, "Выберите тип текста:", reply_markup=create_text_keyboard())

@bot.message_handler(func=lambda message: message.text == "📖 Помощь")
def handle_help(message):
    send_welcome(message)

@bot.message_handler(func=lambda message: message.text == "◀️ Назад")
def handle_back(message):
    bot.send_message(message.chat.id, "Главное меню:", reply_markup=create_main_keyboard())

@bot.message_handler(func=lambda message: message.text == "✏️ Свой текст")
def handle_custom_text(message):
    msg = bot.send_message(
        message.chat.id, 
        "📝 Введите текст в кавычках, например:\n\"Привет мир\"\n\nМожно добавить тему и количество:\n\"Привет\" кот 3"
    )
    user_states[message.from_user.id] = {'state': 'waiting_for_custom_text'}

@bot.message_handler(func=lambda message: message.text == "🎲 Случайная фраза")
def handle_random_phrase(message):
    phrase = get_russian_phrase()
    msg = bot.send_message(
        message.chat.id, 
        f"🎲 Фраза: {phrase}\n\nСколько фото сделать? (1-5)"
    )
    user_states[message.from_user.id] = {'state': 'waiting_for_phrase_count', 'phrase': phrase}

# Динамические обработчики для всех категорий
for category in PHRASES.keys():
    @bot.message_handler(func=lambda message, cat=category: message.text == f"🎭 Категория {cat}")
    def handle_category(message, cat=category):
        phrase = get_random_phrase(cat)
        msg = bot.send_message(
            message.chat.id, 
            f"🎭 Фраза: {phrase}\n\nСколько фото сделать? (1-5)"
        )
        user_states[message.from_user.id] = {'state': 'waiting_for_category_count', 'phrase': phrase}

# ========== ОБРАБОТКА ВВОДА ПОЛЬЗОВАТЕЛЯ ==========

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    user_id = message.from_user.id
    
    # Проверяем, есть ли активное состояние
    if user_id in user_states:
        state = user_states[user_id]
        
        # Ожидание количества для фразы
        if state.get('state') == 'waiting_for_phrase_count' or state.get('state') == 'waiting_for_category_count':
            try:
                count = 1
                if message.text.isdigit():
                    count = min(int(message.text), 5)
                phrase = state.get('phrase', '')
                bot.send_message(message.chat.id, f"🖼️ Генерирую {count} фото...")
                send_photo_with_text(message.chat.id, phrase, 'photo', None, count)
                del user_states[user_id]
            except:
                bot.send_message(message.chat.id, "❌ Ошибка, попробуйте снова")
                del user_states[user_id]
        
        # Ожидание текста в кавычках
        elif state.get('state') == 'waiting_for_custom_text':
            try:
                text = message.text.strip()
                parts = text.lower().split()
                count = 1
                
                # Проверяем число в конце
                if parts and parts[-1].isdigit():
                    count = min(int(parts[-1]), 5)
                    text_without_count = ' '.join(parts[:-1])
                else:
                    text_without_count = text
                
                # Ищем текст в кавычках
                text_match = re.search(r'"([^"]+)"', text_without_count)
                if text_match:
                    text_to_add = text_match.group(1)
                    remaining = re.sub(r'"[^"]+"', '', text_without_count).strip()
                    
                    bot.send_message(message.chat.id, f"🖼️ Генерирую {count} фото...")
                    send_photo_with_text(message.chat.id, text_to_add, 'photo', remaining if remaining else None, count)
                else:
                    bot.send_message(message.chat.id, "❌ Нужно использовать кавычки! Пример: \"Привет\"")
                
                del user_states[user_id]
            except:
                bot.send_message(message.chat.id, "❌ Ошибка, попробуйте снова")
                del user_states[user_id]
    
    else:
        # Если нет активного состояния, проверяем команды
        if message.text.startswith('/'):
            parts = message.text.split()
            cmd = parts[0].lower()
            
            if cmd == '/photo':
                count = 1
                query = None
                if len(parts) > 1:
                    if parts[1].isdigit():
                        count = min(int(parts[1]), 5)
                    else:
                        query = ' '.join(parts[1:])
                send_photo_with_text(message.chat.id, None, 'photo', query, count)
            
            elif cmd == '/meme':
                count = 1
                query = None
                if len(parts) > 1:
                    if parts[1].isdigit():
                        count = min(int(parts[1]), 5)
                    else:
                        query = ' '.join(parts[1:])
                send_photo_with_text(message.chat.id, None, 'meme', query, count)
            
            elif cmd == '/gif':
                count = 1
                query = None
                if len(parts) > 1:
                    if parts[1].isdigit():
                        count = min(int(parts[1]), 5)
                    else:
                        query = ' '.join(parts[1:])
                send_photo_with_text(message.chat.id, None, 'gif', query, count)
            
            elif cmd == '/emoji':
                emoji = get_user_emoji(user_id)
                phrase = random.choice(EMOJI_PHRASES).format(emoji=emoji)
                bot.send_message(message.chat.id, phrase)
            
            elif cmd == '/text':
                text_match = re.search(r'"([^"]+)"', message.text)
                if text_match:
                    text_to_add = text_match.group(1)
                    remaining = re.sub(r'"[^"]+"', '', message.text).strip()
                    remaining = remaining.replace('/text', '', 1).strip()
                    
                    parts_remaining = remaining.split()
                    count = 1
                    query = None
                    
                    if parts_remaining:
                        if parts_remaining[-1].isdigit():
                            count = min(int(parts_remaining[-1]), 5)
                            query = ' '.join(parts_remaining[:-1]) if len(parts_remaining) > 1 else None
                        else:
                            query = ' '.join(parts_remaining)
                    
                    bot.send_message(message.chat.id, f"🖼️ Генерирую {count} фото...")
                    send_photo_with_text(message.chat.id, text_to_add, 'photo', query, count)
                else:
                    bot.send_message(message.chat.id, "❌ Используйте: /text \"текст\" [количество] [тема]")
            
            elif cmd in PHRASES:
                phrase = get_random_phrase(cmd)
                remaining = ' '.join(parts[1:]) if len(parts) > 1 else None
                send_photo_with_text(message.chat.id, phrase, 'photo', remaining, 1)
            
            else:
                bot.send_message(message.chat.id, "Неизвестная команда. Используйте /help")
        
        else:
            bot.send_message(message.chat.id, "Используйте кнопки или команды", reply_markup=create_main_keyboard())

# ========== НАСТРОЙКА ВЕБХУКА ==========

def setup_webhook():
    hostname = os.getenv("RAILWAY_PUBLIC_DOMAIN")
    if not hostname:
        print("Локальный режим")
        return
    
    webhook_path = f"/{TELEGRAM_TOKEN}"
    webhook_url = f"https://{hostname}{webhook_path}"
    
    try:
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url=webhook_url)
        print(f"✅ Personal webhook установлен: {webhook_url}")
    except Exception as e:
        print(f"❌ Ошибка webhook: {e}")

@app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        try:
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return 'OK', 200
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            return 'Error', 500
    abort(403)

@app.route('/')
def index():
    gif_status = "✅ Доступен" if GIPHY_API_KEY else "❌ Не настроен"
    categories = list(PHRASES.keys()) if PHRASES else []
    return (
        f'🎨 Personal Bot работает!<br>'
        f'📸 Категории фраз: {", ".join(categories) if categories else "нет"}<br>'
        f'🎬 GIPHY: {gif_status}<br>'
        f'👥 Пользователей с эмодзи: {len(user_emojis)}'
    ), 200

@app.route('/health')
def health():
    return 'OK', 200

if __name__ == '__main__':
    setup_webhook()
    app.run(host='0.0.0.0', port=PORT, debug=False)
else:
    setup_webhook()