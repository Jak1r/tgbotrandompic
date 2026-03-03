import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, InlineQueryResultArticle, InputTextMessageContent, ReplyKeyboardMarkup, KeyboardButton
from flask import Flask, request, abort, send_file
from dotenv import load_dotenv
import time
import threading
import json
import uuid
import sys
import traceback
import hashlib
import re
import random
import requests
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

print("🚀 Запуск объединенного бота...")
print(f"📸 API фото: {', '.join(available_apis)}")
print(f"🎬 GIPHY API: {'доступен' if GIPHY_API_KEY else 'не настроен'}")
print(f"🎭 Категории фраз: {list(PHRASES.keys()) if PHRASES else 'нет'}")
print(f"🎲 Эмодзи в базе: {len(ALL_EMOJIS)}")

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
app = Flask(__name__)

# ========== ОБЩИЕ ПЕРЕМЕННЫЕ ==========
current_api_index = 0
temp_images = {}
user_states = {}  # Для диалогов в личных сообщениях

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def generate_unique_id(prefix="img"):
    timestamp = int(time.time() * 1000)
    random_part = random.randint(10000, 99999)
    unique_str = str(uuid.uuid4()).replace('-', '')[:8]
    return f"{prefix}_{timestamp}_{random_part}_{unique_str}"

def cleanup_temp_images():
    while True:
        time.sleep(600)
        now = time.time()
        to_delete = [k for k, (_, ts) in temp_images.items() if now - ts > 900]
        for k in to_delete:
            del temp_images[k]
        if to_delete:
            print(f"🧹 Очищено {len(to_delete)} старых файлов")

threading.Thread(target=cleanup_temp_images, daemon=True).start()

# ========== ФУНКЦИИ ДЛЯ ЛИЧНЫХ СООБЩЕНИЙ ==========
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
    """Создает клавиатуру для выбора текста"""
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    categories = list(PHRASES.keys()) if PHRASES else []
    
    buttons = []
    buttons.append(KeyboardButton("✏️ Свой текст"))
    buttons.append(KeyboardButton("🎲 Случайная фраза"))
    
    for category in categories:
        buttons.append(KeyboardButton(f"🎭 Категория {category}"))
    
    buttons.append(KeyboardButton("◀️ Назад"))
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
                        caption = f"GIF {i+1}" if count > 1 else "Powered by GIPHY"
                        # Используем send_animation вместо send_document
                        bot.send_animation(
                            chat_id, 
                            full, 
                            caption=caption,
                            timeout=30  # Увеличиваем таймаут для больших файлов
                        )
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
                    
    except Exception as e:
        bot.send_message(chat_id, f"❌ Ошибка: {e}")

# ========== ОБРАБОТЧИКИ КОМАНД ==========
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """Обрабатывает /start и /help"""
    help_text = (
        '🎨 Привет! Я бот для случайных картинок.\n\n'
        '📸 **Как пользоваться:**\n'
        '• В **личных сообщениях** используй кнопки ниже 👇\n'
        '• В **любом чате** через @ упомяни меня с запросом\n\n'
        '📝 **Примеры inline запросов:**\n'
        '• `@randompikcha2_bot` - случайное фото\n'
        '• `@randompikcha2_bot кот 3` - 3 фото котов\n'
        '• `@randompikcha2_bot "привет"` - фото с текстом\n'
        '• `@randompikcha2_bot meme` - случайный мем\n'
        '• `@randompikcha2_bot gif` - случайная GIF\n'
        '• `@randompikcha2_bot emoji` - эмодзи дня\n\n'
        '🎭 **Категории фраз:**\n' +
        '\n'.join([f'• `{cmd}`' for cmd in PHRASES.keys()]) +
        '\n\nИли просто жми кнопки! 👇'
    )
    
    bot.send_message(
        message.chat.id, 
        help_text, 
        reply_markup=create_main_keyboard(),
        parse_mode='Markdown'
    )

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
def handle_emoji_button(message):
    emoji = get_user_emoji(message.from_user.id)
    phrase = random.choice(EMOJI_PHRASES).format(emoji=emoji)
    bot.send_message(message.chat.id, phrase)

@bot.message_handler(func=lambda message: message.text == "📝 Текст на фото")
def handle_text_menu(message):
    bot.send_message(message.chat.id, "Выберите тип текста:", reply_markup=create_text_keyboard())

@bot.message_handler(func=lambda message: message.text == "📖 Помощь")
def handle_help_button(message):
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
def handle_random_phrase_button(message):
    phrase = get_russian_phrase()
    msg = bot.send_message(
        message.chat.id, 
        f"🎲 Фраза: {phrase}\n\nСколько фото сделать? (1-5)"
    )
    user_states[message.from_user.id] = {'state': 'waiting_for_phrase_count', 'phrase': phrase}

# Динамические обработчики для категорий
for category in PHRASES.keys():
    @bot.message_handler(func=lambda message, cat=category: message.text == f"🎭 Категория {cat}")
    def handle_category(message, cat=category):
        phrase = get_random_phrase(cat)
        msg = bot.send_message(
            message.chat.id, 
            f"🎭 Фраза: {phrase}\n\nСколько фото сделать? (1-5)"
        )
        user_states[message.from_user.id] = {'state': 'waiting_for_category_count', 'phrase': phrase}

# ========== ОБРАБОТКА ДИАЛОГОВ ==========
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    user_id = message.from_user.id
    
    # Проверяем, есть ли активное состояние
    if user_id in user_states:
        state = user_states[user_id]
        
        if state.get('state') in ['waiting_for_phrase_count', 'waiting_for_category_count']:
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
        
        elif state.get('state') == 'waiting_for_custom_text':
            try:
                text = message.text.strip()
                parts = text.lower().split()
                count = 1
                
                if parts and parts[-1].isdigit():
                    count = min(int(parts[-1]), 5)
                    text_without_count = ' '.join(parts[:-1])
                else:
                    text_without_count = text
                
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
        # Обычный текст - показываем клавиатуру
        bot.send_message(message.chat.id, "Используйте кнопки ниже 👇", reply_markup=create_main_keyboard())

# ========== INLINE РЕЖИМ ==========
@bot.inline_handler(lambda query: True)
def inline_handler(inline_query):
    query_text = inline_query.query.strip()
    user_id = inline_query.from_user.id
    
    print(f"📨 Inline запрос: '{query_text}' от {user_id}")
    
    # Умная задержка
    if not query_text:
        print(f"  → пустой запрос, показываем меню")
        print(f"  🔍 Начинаем генерацию меню...")
        results = []
        
        # Генерируем ОДНУ базовую картинку для всех вариантов
        print(f"  ⏳ Генерируем базовую картинку...")
        base_image_url, base_thumb_url = get_random_image()
        if not base_image_url:
            print(f"  ❌ Не удалось получить базовую картинку")
            return
        
        print(f"  ✅ Базовая картинка получена: {base_image_url[:50]}...")
        
        # 1. Базовая картинка БЕЗ текста
        result1 = telebot.types.InlineQueryResultPhoto(
            id=generate_unique_id("menu_photo"),
            photo_url=base_image_url,
            thumbnail_url=base_thumb_url or base_image_url,
            photo_width=1080,
            photo_height=720,
            title="🖼️ Базовая картинка",
            description="Исходное изображение"
        )
        results.append(result1)
        print(f"  ✅ Базовая картинка без текста добавлена")
        
        # 2. Та же базовая картинка со случайной фразой
        random_phrase = get_russian_phrase()
        full = add_text_to_image(base_image_url, random_phrase)
        if full:
            image_id = generate_unique_id("menu_randtext")
            temp_images[image_id] = (full.getvalue(), time.time())
            hostname = os.getenv("RAILWAY_PUBLIC_DOMAIN", "localhost")
            url = f"https://{hostname}/image/{image_id}"
            
            result2 = telebot.types.InlineQueryResultPhoto(
                id=image_id,
                photo_url=url,
                thumbnail_url=url,
                photo_width=1080,
                photo_height=720,
                title="🎲 Случайная фраза",
                description=f"«{random_phrase[:40]}...»"
            )
            results.append(result2)
            print(f"  ✅ Randtext добавлен")
        
        # 3. Та же базовая картинка со случайной категорией
        if PHRASES:
            random_category = random.choice(list(PHRASES.keys()))
            random_phrase = get_random_phrase(random_category)
            full = add_text_to_image(base_image_url, random_phrase)
            if full:
                image_id = generate_unique_id("menu_category")
                temp_images[image_id] = (full.getvalue(), time.time())
                hostname = os.getenv("RAILWAY_PUBLIC_DOMAIN", "localhost")
                url = f"https://{hostname}/image/{image_id}"
                
                result3 = telebot.types.InlineQueryResultPhoto(
                    id=image_id,
                    photo_url=url,
                    thumbnail_url=url,
                    photo_width=1080,
                    photo_height=720,
                    title=f"🎭 {random_category.capitalize()}",
                    description=f"«{random_phrase[:40]}...»"
                )
                results.append(result3)
                print(f"  ✅ Категория {random_category} добавлена")
        
        # 4. Случайный мем
        meme_url, thumb_url = get_random_meme()
        if meme_url and thumb_url:
            result4 = telebot.types.InlineQueryResultPhoto(
                id=generate_unique_id("menu_meme"),
                photo_url=meme_url,
                thumbnail_url=thumb_url,
                photo_width=1080,
                photo_height=720,
                title="😂 Случайный мем",
                description="Поржать на сегодня"
            )
            results.append(result4)
            print(f"  ✅ Мем добавлен")

        # 👇 ЭМОДЗИ ДНЯ ТЕПЕРЬ ЗДЕСЬ (ПОСЛЕ МЕМА)
        emoji = get_user_emoji(user_id)
        emoji_phrase = random.choice(EMOJI_PHRASES).format(emoji=emoji)
        result5 = telebot.types.InlineQueryResultArticle(
            id=generate_unique_id("menu_emoji"),
            title="🎲 Эмодзи дня",
            description=emoji_phrase,
            input_message_content=telebot.types.InputTextMessageContent(
                message_text=emoji_phrase
            ),
            thumbnail_url="https://images.unsplash.com/photo-1518548419970-58e3b4079ab2?w=200",
            thumbnail_width=200,
            thumbnail_height=133
        )
        results.append(result5)
        print(f"  ✅ Эмодзи дня: {emoji}")
        
        # 6. Инструкция
        help_text = (
            "📖 **Как пользоваться:**\n\n"
            "**Основные команды:**\n"
            "• `@randompikcha2_bot` - это меню\n"
            "• `@randompikcha2_bot кот` - фото по теме\n"
            "• `@randompikcha2_bot 3` - 3 фото на выбор\n\n"
            "**Текст на фото:**\n"
            "• `@randompikcha2_bot \"Привет\"` - фото с текстом\n"
            "• `@randompikcha2_bot \"Привет\" кот 3` - 3 фото котов с текстом\n\n"
            "**Случайные фразы:**\n"
            "• `@randompikcha2_bot randtext` - фото с фразой\n\n"
            "**Категории фраз:**\n" +
            ''.join([f"• `@randompikcha2_bot {cat}`\n" for cat in PHRASES.keys()]) +
            "\n**Мемы и GIF:**\n"
            "• `@randompikcha2_bot meme` - случайный мем\n"
            "• `@randompikcha2_bot gif` - случайная GIF\n\n"
            "**Эмодзи дня:**\n"
            "• `@randompikcha2_bot emoji` - твоё эмодзи на сегодня\n\n"
            "⚡️ **Совет:** Добавляй число в конце для нескольких вариантов!"
        )
        
        result_help = telebot.types.InlineQueryResultArticle(
            id=generate_unique_id("menu_help"),
            title="📖 Инструкция",
            description="Как пользоваться ботом",
            input_message_content=telebot.types.InputTextMessageContent(
                message_text=help_text,
                parse_mode='Markdown'
            ),
            thumbnail_url="https://images.unsplash.com/photo-1486312338219-ce68d2c6f44d?w=200",
            thumbnail_width=200,
            thumbnail_height=133
        )
        results.append(result_help)
        
        print(f"📊 Всего результатов: {len(results)}")
        
        # Отправляем меню
        try:
            bot.answer_inline_query(inline_query.id, results, cache_time=0, is_personal=True)
            print(f"✅ Отправлено меню из {len(results)} пунктов")
            return
        except Exception as e:
            print(f"❌ Ошибка отправки меню: {e}")
            traceback.print_exc()
            return

    elif len(query_text) < 3:
        time.sleep(0.2)
    
    results = []

    try:
        text_to_add = None
        search_query = None
        is_randtext = False
        is_gif = False
        is_meme = False
        images_count = 1
        
        original_text = query_text
        parts = query_text.lower().split()
        
        # Ищем число в конце
        if parts and parts[-1].isdigit():
            images_count = min(int(parts[-1]), 5)
            query_text = ' '.join(parts[:-1])
            parts = query_text.lower().split()
            print(f"  → запрошено {images_count} картинок")
        
        # Эмодзи дня
        if parts and parts[0] == 'emoji':
            print(f"  → команда emoji")
            emoji = get_user_emoji(user_id)
            phrase = random.choice(EMOJI_PHRASES).format(emoji=emoji)
            result_id = generate_unique_id("emoji")
            result = InlineQueryResultArticle(
                id=result_id,
                title=f"🎲 Эмодзи дня {emoji}",
                description=phrase,
                input_message_content=InputTextMessageContent(
                    message_text=phrase,
                    parse_mode=None
                )
            )
            results.append(result)
            print(f"  → эмодзи дня для {user_id}: {emoji}")
        
        elif not query_text:
            search_query = None
            print(f"  → {images_count} случайных картинок")
        else:
            # Мемы
            if parts and parts[0] == 'meme':
                print(f"  → режим MEME")
                is_meme = True
                
                if len(parts) == 1:
                    search_query = None
                    text_to_add = None
                    print(f"  → просто мем без текста")
                else:
                    if re.match(r'^".+"', ' '.join(parts[1:])):
                        text_match = re.search(r'"([^"]+)"', original_text)
                        if text_match:
                            text_to_add = text_match.group(1)
                            remaining = re.sub(r'"[^"]+"', '', original_text.replace('meme', '', 1)).strip()
                            if remaining and remaining.split() and remaining.split()[-1].isdigit():
                                remaining = ' '.join(remaining.split()[:-1])
                            search_query = remaining if remaining else None
                            print(f"  → текст на меме: {text_to_add[:30]}...")
                    
                    elif parts[1] == 'randtext':
                        is_randtext = True
                        text_to_add = get_russian_phrase()
                        search_query = ' '.join(parts[2:]) if len(parts) > 2 else None
                        print(f"  → фраза на меме: {text_to_add[:30]}...")
                    
                    elif parts[1] in PHRASES:
                        phrase_category = parts[1]
                        text_to_add = get_random_phrase(phrase_category)
                        search_query = ' '.join(parts[2:]) if len(parts) > 2 else None
                        print(f"  → категория на меме: {phrase_category} -> '{text_to_add[:30]}...'")
                    
                    else:
                        search_query = ' '.join(parts[1:])
                        text_to_add = None
                        print(f"  → поиск мемов по теме: {search_query}")
            
            # GIF
            elif parts and parts[0] == 'gif':
                if not GIPHY_API_KEY:
                    print("❌ GIF запрос, но API не настроен")
                    return
                
                is_gif = True
                print(f"  → режим GIF")
                
                if len(parts) == 1:
                    search_query = None
                    text_to_add = None
                    print(f"  → просто GIF без текста")
                else:
                    if re.match(r'^".+"', ' '.join(parts[1:])):
                        text_match = re.search(r'"([^"]+)"', original_text)
                        if text_match:
                            text_to_add = text_match.group(1)
                            remaining = re.sub(r'"[^"]+"', '', original_text.replace('gif', '', 1)).strip()
                            if remaining and remaining.split() and remaining.split()[-1].isdigit():
                                remaining = ' '.join(remaining.split()[:-1])
                            search_query = remaining if remaining else None
                            print(f"  → текст на GIF: {text_to_add[:30]}...")
                    
                    elif parts[1] == 'randtext':
                        is_randtext = True
                        text_to_add = get_russian_phrase()
                        search_query = ' '.join(parts[2:]) if len(parts) > 2 else None
                        print(f"  → фраза на GIF: {text_to_add[:30]}...")
                    
                    elif parts[1] in PHRASES:
                        phrase_category = parts[1]
                        text_to_add = get_random_phrase(phrase_category)
                        search_query = ' '.join(parts[2:]) if len(parts) > 2 else None
                        print(f"  → категория на GIF: {phrase_category} -> '{text_to_add[:30]}...'")
                    
                    else:
                        search_query = ' '.join(parts[1:])
                        text_to_add = None
                        print(f"  → поиск GIF по тегу: {search_query}")
            
            # ФОТО
            else:
                if parts and parts[0] == 'randtext':
                    is_randtext = True
                    print(f"  → режим randtext для фото")
                    text_to_add = get_russian_phrase()
                    search_query = ' '.join(parts[1:]) if len(parts) > 1 else None
                
                elif parts and parts[0] in PHRASES:
                    phrase_category = parts[0]
                    text_to_add = get_random_phrase(phrase_category)
                    search_query = ' '.join(parts[1:]) if len(parts) > 1 else None
                    print(f"  → категория фото: {phrase_category} -> '{text_to_add[:30]}...'")
                
                elif re.match(r'^".+"', query_text) or (parts and parts[0].startswith('"')):
                    text_match = re.search(r'"([^"]+)"', original_text)
                    if text_match:
                        text_to_add = text_match.group(1)
                        remaining = re.sub(r'"[^"]+"', '', original_text).strip()
                        if remaining and remaining.split() and remaining.split()[-1].isdigit():
                            remaining = ' '.join(remaining.split()[:-1])
                        search_query = remaining if remaining else None
                        print(f"  → текст на фото: {text_to_add[:30]}...")
                
                elif query_text:
                    print(f"  → поиск фото: {query_text}")
                    search_query = query_text

        # ===== ГЕНЕРАЦИЯ =====
        if is_gif:
            print(f"🎬 Генерируем {images_count} GIF" + (" с текстом" if text_to_add else ""))
            
            gif_urls = []
            attempts = 0
            max_attempts = images_count * 5
            
            while len(gif_urls) < images_count and attempts < max_attempts:
                gif_url = get_random_gif(search_query)
                if gif_url and gif_url not in gif_urls:
                    gif_urls.append(gif_url)
                    print(f"  ✅ Найдено {len(gif_urls)}/{images_count} GIF")
                attempts += 1
            
            if len(gif_urls) == 0:
                print("❌ Не найдено ни одной GIF")
                return
            
            for i, gif_url in enumerate(gif_urls):
                print(f"  🎨 Обрабатываем GIF {i+1}/{len(gif_urls)}")
                
                if text_to_add:
                    full = add_text_to_gif(gif_url, text_to_add)
                else:
                    try:
                        r = requests.get(gif_url, timeout=10)
                        full = BytesIO(r.content)
                    except:
                        continue
                
                if full:
                    gif_id = generate_unique_id(f"gif_{i+1}")
                    temp_images[gif_id] = (full.getvalue(), time.time())
                    
                    hostname = os.getenv("RAILWAY_PUBLIC_DOMAIN", "localhost")
                    url = f"https://{hostname}/image/{gif_id}"
                    
                    result = telebot.types.InlineQueryResultGif(
                        id=gif_id,
                        gif_url=url,
                        thumbnail_url=url,
                        gif_width=480,
                        gif_height=360,
                        title=f"GIF {i+1}" + (f": {text_to_add[:20]}..." if text_to_add else ""),
                        caption="Powered by GIPHY"
                    )
                    results.append(result)
            
            print(f"✅ Сгенерировано {len(results)} GIF")

        elif is_meme:
            print(f"🎭 Генерируем {images_count} мемов" + (" с текстом" if text_to_add else ""))
            
            meme_data = []
            attempts = 0
            max_attempts = images_count * 5
            
            while len(meme_data) < images_count and attempts < max_attempts:
                meme_url, thumb_url = get_random_meme(search_query)
                if meme_url and thumb_url:
                    if not any(url == meme_url for url, _ in meme_data):
                        meme_data.append((meme_url, thumb_url))
                        print(f"  ✅ Найдено {len(meme_data)}/{images_count} мемов")
                attempts += 1
            
            if len(meme_data) == 0:
                print("❌ Не найдено ни одного мема")
                return
            
            for i, (meme_url, thumb_url) in enumerate(meme_data):
                print(f"  🎨 Обрабатываем мем {i+1}/{len(meme_data)}")
                
                if text_to_add:
                    full = add_text_to_image(meme_url, text_to_add)
                    if full:
                        meme_id = generate_unique_id(f"meme_text_{i+1}")
                        temp_images[meme_id] = (full.getvalue(), time.time())
                        
                        hostname = os.getenv("RAILWAY_PUBLIC_DOMAIN", "localhost")
                        url = f"https://{hostname}/image/{meme_id}"
                        
                        result = telebot.types.InlineQueryResultPhoto(
                            id=meme_id,
                            photo_url=url,
                            thumbnail_url=url,
                            photo_width=1080,
                            photo_height=720,
                            title=f"Мем {i+1}: {text_to_add[:30]}...",
                            description=f"Мем с текстом"
                        )
                        results.append(result)
                else:
                    meme_id = generate_unique_id(f"meme_{i+1}")
                    
                    result = telebot.types.InlineQueryResultPhoto(
                        id=meme_id,
                        photo_url=meme_url,
                        thumbnail_url=thumb_url,
                        photo_width=1080,
                        photo_height=720,
                        title=f"Мем {i+1}",
                        description=f"Случайный мем"
                    )
                    results.append(result)
            
            print(f"✅ Сгенерировано {len(results)} мемов")

        elif text_to_add or is_randtext:
            print(f"🖼️ Генерируем {images_count} картинок с текстом: '{text_to_add[:30]}...'")
            
            image_urls = []
            attempts = 0
            max_attempts = images_count * 5
            
            while len(image_urls) < images_count and attempts < max_attempts:
                image_url, _ = get_random_image(search_query)
                if image_url and image_url not in image_urls:
                    image_urls.append(image_url)
                    print(f"  ✅ Найдено {len(image_urls)}/{images_count} URL")
                attempts += 1
            
            if len(image_urls) == 0:
                print("❌ Не найдено ни одной картинки")
                return
            
            for i, image_url in enumerate(image_urls):
                print(f"  🎨 Генерируем картинку {i+1}/{len(image_urls)}")
                full = add_text_to_image(image_url, text_to_add)
                
                if full:
                    image_id = generate_unique_id(f"text_{i+1}")
                    temp_images[image_id] = (full.getvalue(), time.time())
                    
                    hostname = os.getenv("RAILWAY_PUBLIC_DOMAIN", "localhost")
                    url = f"https://{hostname}/image/{image_id}"
                    
                    result = telebot.types.InlineQueryResultPhoto(
                        id=image_id,
                        photo_url=url,
                        thumbnail_url=url,
                        photo_width=1080,
                        photo_height=720,
                        title=f"Вариант {i+1}: {text_to_add[:30]}...",
                        description=f"Нажми для отправки"
                    )
                    results.append(result)
            
            print(f"✅ Сгенерировано {len(results)} картинок")

        else:
            print(f"🖼️ Генерируем {images_count} картинок по запросу: '{search_query or 'случайная'}'")
            
            image_data = []
            attempts = 0
            max_attempts = images_count * 5
            
            while len(image_data) < images_count and attempts < max_attempts:
                image_url, thumb_url = get_random_image(search_query)
                if image_url and thumb_url:
                    if not any(url == image_url for url, _ in image_data):
                        image_data.append((image_url, thumb_url))
                        print(f"  ✅ Найдено {len(image_data)}/{images_count} картинок")
                attempts += 1
            
            for i, (image_url, thumb_url) in enumerate(image_data):
                result_id = generate_unique_id(f"img_{i+1}")
                
                result = telebot.types.InlineQueryResultPhoto(
                    id=result_id,
                    photo_url=image_url,
                    thumbnail_url=thumb_url,
                    photo_width=1080,
                    photo_height=720,
                    title=f"Вариант {i+1}",
                    description=f"Нажми для отправки"
                )
                results.append(result)
            
            print(f"✅ Сгенерировано {len(results)} картинок")

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        traceback.print_exc()

    try:
        if results:
            bot.answer_inline_query(inline_query.id, results, cache_time=0, is_personal=True)
            print(f"✅ Отправлено {len(results)} результатов")
        else:
            bot.answer_inline_query(inline_query.id, [], cache_time=0)
            print("❌ Нет результатов")
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")
        traceback.print_exc()

# ========== ЭНДПОИНТ ДЛЯ ФАЙЛОВ ==========
@app.route('/image/<image_id>', methods=['GET', 'HEAD'])
def serve_image(image_id):
    if image_id in temp_images:
        image_data, _ = temp_images[image_id]
        
        if request.method == 'HEAD':
            response = app.make_response('')
            response.headers['Content-Type'] = 'image/gif' if image_id.startswith('gif') else 'image/jpeg'
            response.headers['Content-Length'] = str(len(image_data))
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Cache-Control'] = 'public, max-age=3600'
            return response
        
        mimetype = 'image/gif' if image_id.startswith('gif') else 'image/jpeg'
        
        response = send_file(
            BytesIO(image_data),
            mimetype=mimetype,
            as_attachment=False,
            download_name=f'{image_id}.{"gif" if image_id.startswith("gif") else "jpg"}'
        )
        
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Cache-Control'] = 'public, max-age=3600'
        
        return response
        
    abort(404)

# ========== ВЕБХУК ==========
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
        success = bot.set_webhook(url=webhook_url)
        print(f"✅ Webhook установлен: {webhook_url}")
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
            print(f"❌ Ошибка обработки: {e}")
            return 'Error', 500
    abort(403)

@app.route('/')
def index():
    gif_status = "✅ Доступен" if GIPHY_API_KEY else "❌ Не настроен"
    categories = list(PHRASES.keys()) if PHRASES else []
    return (
        f'🎨 Объединенный бот работает!<br>'
        f'📸 API фото: {", ".join(available_apis)}<br>'
        f'🎬 GIPHY: {gif_status}<br>'
        f'🎭 Категории фраз: {", ".join(categories) if categories else "нет"}<br>'
        f'🎲 Эмодзи в базе: {len(ALL_EMOJIS)}<br>'
        f'📦 Файлов в памяти: {len(temp_images)}<br>'
        f'👥 Пользователей с эмодзи: {len(user_emojis)}'
    ), 200

@app.route('/health')
def health():
    return 'OK', 200

if __name__ == '__main__':
    setup_webhook()
    print(f"🚀 Сервер запущен на порту {PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=False)
else:
    setup_webhook()