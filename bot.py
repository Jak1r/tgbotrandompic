import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, InlineQueryResultArticle, InputTextMessageContent
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
from io import BytesIO

# Импортируем общую логику
from shared_logic import *

load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
PORT = int(os.getenv('PORT', 8080))

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не задан в переменных окружения")

print(f"🚀 Запуск inline бота...")
print(f"📸 API фото: {', '.join(available_apis)}")
if GIPHY_API_KEY:
    print(f"🎬 GIPHY API: доступен")
print(f"🎲 Эмодзи в базе: {len(ALL_EMOJIS)}")

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
app = Flask(__name__)

current_api_index = 0
temp_images = {}

def generate_unique_id(prefix="img"):
    timestamp = int(time.time() * 1000)
    random_part = random.randint(10000, 99999)
    unique_str = str(uuid.uuid4()).replace('-', '')[:8]
    return f"{prefix}_{timestamp}_{random_part}_{unique_str}"

def cleanup_temp_images():
    """Очистка старых изображений"""
    while True:
        time.sleep(600)
        now = time.time()
        to_delete = [k for k, (_, ts) in temp_images.items() if now - ts > 900]
        for k in to_delete:
            del temp_images[k]
        if to_delete:
            print(f"🧹 Очищено {len(to_delete)} старых файлов")

threading.Thread(target=cleanup_temp_images, daemon=True).start()

def setup_webhook():
    hostname = os.getenv("RAILWAY_PUBLIC_DOMAIN")
    if not hostname:
        print("RAILWAY_PUBLIC_DOMAIN не найден → локальный режим")
        return

    webhook_path = f"/{TELEGRAM_TOKEN}"
    webhook_url = f"https://{hostname}{webhook_path}"

    try:
        current = bot.get_webhook_info()
        if current.url != webhook_url:
            bot.remove_webhook()
            time.sleep(1)
            success = bot.set_webhook(url=webhook_url)
            print(f"Webhook {'установлен' if success else 'ОШИБКА'}: {webhook_url}")
        else:
            print(f"Webhook уже установлен: {webhook_url}")
    except Exception as e:
        print(f"Webhook error: {e}")

@bot.message_handler(commands=['start', 'help'])
def start_command(message):
    available_commands = list(PHRASES.keys())
    commands_text = '\n'.join([f'• `@randompikcha2_bot {cmd}` — фраза из "{cmd}"' for cmd in available_commands])
    
    gif_help = "• `@randompikcha2_bot gif` — случайная гифка\n" if GIPHY_API_KEY else ""
    
    help_text = (
        '🎨 Привет! Я бот для случайных картинок.\n\n'
        '📸 Как пользоваться (inline режим):\n'
        '• Просто имя бота — случайная картинка\n'
        '• `@randompikcha2_bot cats` — картинка по теме\n'
        '• `@randompikcha2_bot 3` — 3 картинки на выбор\n\n'
        '📝 Текст на картинке:\n'
        '• `@randompikcha2_bot "Привет мир"` — картинка с текстом\n'
        '• `@randompikcha2_bot "Привет" cats 3` — 3 картинки котов с текстом\n\n'
        '🎭 Фразы:\n'
        f'{commands_text}\n\n'
        '🎲 Случайные фразы:\n'
        '• `@randompikcha2_bot randtext` — картинка + осмысленная фраза\n'
        '• `@randompikcha2_bot randtext природа 2` — 2 картинки природы с фразой\n\n'
        '🎭 Мемы:\n'
        '• `@randompikcha2_bot meme` — случайный мем\n'
        '• `@randompikcha2_bot meme 3` — 3 мема на выбор\n'
        '• `@randompikcha2_bot meme "текст"` — мем с текстом\n'
        '• `@randompikcha2_bot meme randtext` — мем с фразой\n'
        '• `@randompikcha2_bot meme papich` — мем с фразой из категории\n'
        '• `@randompikcha2_bot meme кот 2` — 2 мема про котов\n\n'
        '🎲 Эмодзи дня:\n'
        '• `@randompikcha2_bot emoji` — твоё персональное эмодзи на сегодня\n'
        '  (обновляется каждый день в 00:00 по Москве)\n\n'
    )
    
    if gif_help:
        help_text += '🎬 Гифки:\n' + gif_help + '\n'
    
    help_text += f'📸 API фото: {", ".join(available_apis)}'
    if GIPHY_API_KEY:
        help_text += '\n🎬 GIPHY: ✅ (100 запросов/час)'
    
    bot.reply_to(message, help_text, parse_mode='Markdown')

@bot.message_handler(func=lambda message: True)
def handle_mention(message):
    bot_username = bot.get_me().username
    if f'@{bot_username}' in message.text:
        markup = InlineKeyboardMarkup()
        button = InlineKeyboardButton('📸 Случайная картинка', callback_data='send_random_img')
        markup.add(button)
        bot.reply_to(message, 'Что хочешь?', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data == 'send_random_img':
        bot.answer_callback_query(call.id, "Загружаю...")
        image_url, _ = get_random_image()
        if image_url:
            try:
                bot.send_photo(call.message.chat.id, image_url)
            except Exception as e:
                bot.send_message(call.message.chat.id, '❌ Не удалось отправить')
                print(f"Ошибка фото: {e}")
        else:
            bot.send_message(call.message.chat.id, '❌ Картинка не найдена')

@bot.inline_handler(lambda query: True)
def inline_handler(inline_query):
    query_text = inline_query.query.strip()
    user_id = inline_query.from_user.id
    
    print(f"📨 Запрос: '{query_text}' от {user_id}")
    
    # Умная задержка
    if not query_text:
        pass
    elif len(query_text) < 3:
        time.sleep(0.2)
    else:
        hash_input = f"{user_id}_{query_text}".encode()
        hash_value = int(hashlib.md5(hash_input).hexdigest(), 16)
        delay = 0.3 + (hash_value % 5) / 10
        time.sleep(delay)
    
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
        
        # Ищем число в конце (количество картинок)
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
                    parse_mode='HTML'
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
                    # Текст в кавычках: meme "привет"
                    if re.match(r'^".+"', ' '.join(parts[1:])):
                        text_match = re.search(r'"([^"]+)"', original_text)
                        if text_match:
                            text_to_add = text_match.group(1)
                            remaining = re.sub(r'"[^"]+"', '', original_text.replace('meme', '', 1)).strip()
                            if remaining and remaining.split() and remaining.split()[-1].isdigit():
                                remaining = ' '.join(remaining.split()[:-1])
                            search_query = remaining if remaining else None
                            print(f"  → текст на меме: {text_to_add[:30]}...")
                    
                    # randtext: meme randtext
                    elif parts[1] == 'randtext':
                        is_randtext = True
                        text_to_add = get_russian_phrase()
                        search_query = ' '.join(parts[2:]) if len(parts) > 2 else None
                        print(f"  → фраза на меме: {text_to_add[:30]}...")
                    
                    # Категории фраз: meme papich, meme tehnik
                    elif parts[1] in PHRASES:
                        phrase_category = parts[1]
                        text_to_add = get_random_phrase(phrase_category)
                        search_query = ' '.join(parts[2:]) if len(parts) > 2 else None
                        print(f"  → категория на меме: {phrase_category} -> '{text_to_add[:30]}...'")
                    
                    # Обычный поиск: meme кот
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
                    # Текст в кавычках: gif "привет"
                    if re.match(r'^".+"', ' '.join(parts[1:])):
                        text_match = re.search(r'"([^"]+)"', original_text)
                        if text_match:
                            text_to_add = text_match.group(1)
                            remaining = re.sub(r'"[^"]+"', '', original_text.replace('gif', '', 1)).strip()
                            if remaining and remaining.split() and remaining.split()[-1].isdigit():
                                remaining = ' '.join(remaining.split()[:-1])
                            search_query = remaining if remaining else None
                            print(f"  → текст на GIF: {text_to_add[:30]}...")
                    
                    # randtext: gif randtext
                    elif parts[1] == 'randtext':
                        is_randtext = True
                        text_to_add = get_russian_phrase()
                        search_query = ' '.join(parts[2:]) if len(parts) > 2 else None
                        print(f"  → фраза на GIF: {text_to_add[:30]}...")
                    
                    # Категории фраз: gif papich
                    elif parts[1] in PHRASES:
                        phrase_category = parts[1]
                        text_to_add = get_random_phrase(phrase_category)
                        search_query = ' '.join(parts[2:]) if len(parts) > 2 else None
                        print(f"  → категория на GIF: {phrase_category} -> '{text_to_add[:30]}...'")
                    
                    # Обычный поиск: gif кот
                    else:
                        search_query = ' '.join(parts[1:])
                        text_to_add = None
                        print(f"  → поиск GIF по тегу: {search_query}")
            
            # ФОТО
            else:
                # randtext для фото
                if parts and parts[0] == 'randtext':
                    is_randtext = True
                    print(f"  → режим randtext для фото")
                    text_to_add = get_russian_phrase()
                    search_query = ' '.join(parts[1:]) if len(parts) > 1 else None
                
                # Категории фраз для фото
                elif parts and parts[0] in PHRASES:
                    phrase_category = parts[0]
                    text_to_add = get_random_phrase(phrase_category)
                    search_query = ' '.join(parts[1:]) if len(parts) > 1 else None
                    print(f"  → категория фото: {phrase_category} -> '{text_to_add[:30]}...'")
                
                # Текст в кавычках для фото
                elif re.match(r'^".+"', query_text) or (parts and parts[0].startswith('"')):
                    text_match = re.search(r'"([^"]+)"', original_text)
                    if text_match:
                        text_to_add = text_match.group(1)
                        remaining = re.sub(r'"[^"]+"', '', original_text).strip()
                        if remaining and remaining.split() and remaining.split()[-1].isdigit():
                            remaining = ' '.join(remaining.split()[:-1])
                        search_query = remaining if remaining else None
                        print(f"  → текст на фото: {text_to_add[:30]}...")
                
                # Обычный поиск для фото
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
                        caption="Powered by GIPHY"  # 👈 Добавьте эту строку
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

# Эндпоинт для получения файлов
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

@app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        try:
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return 'OK', 200
        except Exception as e:
            print(f"Ошибка обработки: {e}")
            return 'Error', 500
    abort(403)

@app.route('/')
def index():
    hostname = os.getenv("RAILWAY_PUBLIC_DOMAIN", "localhost")
    gif_status = "✅ GIPHY" if GIPHY_API_KEY else "❌ Не настроен"
    emoji_count = len(ALL_EMOJIS)
    return (
        f'🤖 Inline Bot работает на Railway<br>'
        f'📸 API фото: {", ".join(available_apis)}<br>'
        f'🎬 GIF API: {gif_status}<br>'
        f'🎲 Эмодзи в базе: {emoji_count}<br>'
        f'🎭 Мемы: ✅<br>'
        f'📦 Файлов в памяти: {len(temp_images)}<br>'
        f'📝 Фраз: {sum(len(v) for v in PHRASES.values())}<br>'
        f'🌐 Домен: https://{hostname}'
    ), 200

@app.route('/health')
def health():
    return 'OK', 200

if __name__ == '__main__':
    print("🚀 Запуск inline бота...")
    setup_webhook()
    app.run(host='0.0.0.0', port=PORT, debug=False)
else:
    setup_webhook()