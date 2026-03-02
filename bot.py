import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import random
import requests
from flask import Flask, request, abort, send_file, redirect
from dotenv import load_dotenv
import time
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import re
import threading
import json
import uuid
import sys
import traceback

print("=== START bot.py ===")
print(f"Python version: {sys.version}")
print(f"Working directory: {os.getcwd()}")

load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
UNSPLASH_ACCESS_KEY = os.getenv('UNSPLASH_ACCESS_KEY')
PEXELS_API_KEY = os.getenv('PEXELS_API_KEY')
PIXABAY_API_KEY = os.getenv('PIXABAY_API_KEY')

PORT = int(os.getenv('PORT', 8080))

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не задан в переменных окружения")

available_apis = []
if UNSPLASH_ACCESS_KEY: available_apis.append('unsplash')
if PEXELS_API_KEY: available_apis.append('pexels')
if PIXABAY_API_KEY: available_apis.append('pixabay')

if not available_apis:
    raise ValueError("Нет доступных API ключей!")

print(f"🔑 Доступно API: {', '.join(available_apis)}")

# Фразы
def load_phrases():
    try:
        with open('phrases.json', 'r', encoding='utf-8') as f:
            phrases = json.load(f)
        print(f"✅ Загружено {sum(len(v) for v in phrases.values())} фраз")
        return phrases
    except FileNotFoundError:
        print("⚠️ phrases.json не найден → создаём дефолтный")
        default = {
            "papich": ["Хорош, хорош!", "Это база!", "Красавчик!", "Топчик!"],
            "tehnik": ["Техника - молодёжь!", "Погнали!", "Здарова, пацаны!"],
            "random": ["Удача", "Красота", "Счастье", "Сила"]
        }
        with open('phrases.json', 'w', encoding='utf-8') as f:
            json.dump(default, f, ensure_ascii=False)
        return default
    except Exception as e:
        print(f"Ошибка загрузки phrases.json: {e}")
        return {}

PHRASES = load_phrases()

RANDOM_QUERIES = [
    'nature', 'city', 'abstract', 'people', 'animals', 'food',
    'travel', 'space', 'art', 'technology', 'mountain', 'ocean',
    'forest', 'sunset', 'flowers', 'architecture', 'beach', 'winter'
]

# ========== НОВАЯ ФУНКЦИЯ ДЛЯ ПОЛУЧЕНИЯ ФРАЗ ==========
def get_russian_phrase():
    """Получает случайную русскую фразу из Fucking Great Advice API"""
    try:
        print("Запрашиваем фразу из Fucking Great Advice...")
        
        # Пробуем получить фразу из API
        response = requests.get(
            'https://fucking-great-advice.ru/api/random',
            timeout=5,
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        
        if response.status_code == 200:
            data = response.json()
            phrase = data.get('text', '').strip()
            
            # Проверяем, что фраза не пустая и на русском
            if phrase and len(phrase) > 5:
                print(f"✅ Получена фраза: {phrase[:50]}...")
                return phrase
            
    except Exception as e:
        print(f"⚠️ Ошибка получения фразы из API: {e}")
    
    # Если API не сработало, используем запасные фразы
    print("⚠️ Используем запасные фразы")
    return get_backup_phrase()

def get_backup_phrase():
    """Запасные фразы на случай недоступности API"""
    backup_phrases = [
        "Всё будет хорошо!",
        "Жизнь прекрасна!",
        "Улыбнись новому дню!",
        "Верь в лучшее!",
        "Ты справишься!",
        "Никогда не сдавайся!",
        "Дорогу осилит идущий!",
        "Сегодня твой день!",
        "У тебя всё получится!",
        "Мечты сбываются!",
        "Живи ярко!",
        "Будь счастлив!",
        "Цени момент!",
        "Всё в твоих руках!",
        "Действуй!",
        "Не останавливайся!",
        "Вперёд к мечте!",
        "Ты уникален!",
        "Продолжай двигаться!",
        "Выше только небо!"
    ]
    return random.choice(backup_phrases)

# ========== КОНЕЦ НОВОЙ ФУНКЦИИ ==========

words_cache = []

def fetch_russian_words():
    global words_cache
    if words_cache:
        return words_cache

    print("Загружаем русские слова...")
    try:
        r = requests.get("https://raw.githubusercontent.com/danakt/russian-words/master/russian.txt", timeout=12)
        if r.ok:
            words = r.text.splitlines()
            good = [w.lower() for w in words if 3 <= len(w) <= 15 and all('а' <= c <= 'я' or c == 'ё' for c in w.lower())]
            words_cache = list(set(good))
            print(f"Загружено {len(words_cache)} слов")
    except Exception as e:
        print(f"Ошибка: {e}")
        words_cache = ['мир', 'дом', 'лес', 'река', 'кот']

    return words_cache

fetch_russian_words()

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
app = Flask(__name__)
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

@app.before_request
def before_request():
    # Перенаправляем HTTP на HTTPS
    if not request.is_secure and not request.headers.get('X-Forwarded-Proto', 'http') == 'https':
        if request.url.startswith('http://'):
            url = request.url.replace('http://', 'https://', 1)
            return redirect(url, code=301)

current_api_index = 0
temp_images = {}

def generate_unique_id(prefix="img"):
    timestamp = int(time.time() * 1000)
    random_part = random.randint(10000, 99999)
    unique_str = str(uuid.uuid4()).replace('-', '')[:8]
    return f"{prefix}_{timestamp}_{random_part}_{unique_str}"

def get_random_phrase(category="random"):
    if category in PHRASES and PHRASES[category]:
        return random.choice(PHRASES[category])
    return "Случайная фраза"

def cleanup_temp_images():
    while True:
        time.sleep(600)
        now = time.time()
        to_delete = [k for k, (_, ts) in temp_images.items() if now - ts > 900]
        for k in to_delete:
            del temp_images[k]
        if to_delete:
            print(f"Очищено {len(to_delete)} изображений")

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

def get_unsplash_image(query):
    url = f'https://api.unsplash.com/photos/random?query={query}&client_id={UNSPLASH_ACCESS_KEY}'
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 429:
            print("⚠️ Unsplash rate limit")
            return None, None, True
        r.raise_for_status()
        data = r.json()
        urls = data.get('urls', {})
        return urls.get('regular'), urls.get('thumb'), False
    except Exception as e:
        print(f"Unsplash error: {e}")
        return None, None, False

def get_pexels_image(query):
    url = f'https://api.pexels.com/v1/search?query={query}&per_page=1&page={random.randint(1, 100)}'
    headers = {'Authorization': PEXELS_API_KEY}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 429:
            print("⚠️ Pexels rate limit")
            return None, None, True
        r.raise_for_status()
        data = r.json()
        photos = data.get('photos', [])
        if photos:
            photo = photos[0]
            return photo['src']['large'], photo['src']['small'], False
        return None, None, False
    except Exception as e:
        print(f"Pexels error: {e}")
        return None, None, False

def get_pixabay_image(query):
    url = f'https://pixabay.com/api/?key={PIXABAY_API_KEY}&q={query}&image_type=photo&per_page=3&page={random.randint(1, 50)}'
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 429:
            print("⚠️ Pixabay rate limit")
            return None, None, True
        r.raise_for_status()
        data = r.json()
        hits = data.get('hits', [])
        if hits:
            photo = random.choice(hits)
            return photo['largeImageURL'], photo['previewURL'], False
        return None, None, False
    except Exception as e:
        print(f"Pixabay error: {e}")
        return None, None, False

def get_random_image(custom_query=None):
    global current_api_index
    query = custom_query or random.choice(RANDOM_QUERIES)
    for _ in range(len(available_apis)):
        api_name = available_apis[current_api_index]
        print(f"Попытка #{_ + 1}: {api_name.upper()}")
        image_url, thumb_url, rate_limited = None, None, False
        if api_name == 'unsplash':
            image_url, thumb_url, rate_limited = get_unsplash_image(query)
        elif api_name == 'pexels':
            image_url, thumb_url, rate_limited = get_pexels_image(query)
        elif api_name == 'pixabay':
            image_url, thumb_url, rate_limited = get_pixabay_image(query)
        if image_url and thumb_url:
            current_api_index = (current_api_index + 1) % len(available_apis)
            return image_url, thumb_url
        if rate_limited:
            current_api_index = (current_api_index + 1) % len(available_apis)
            continue
        current_api_index = (current_api_index + 1) % len(available_apis)
    print(f"Все API не дали результат для '{query}'")
    return None, None

def add_text_to_image(image_url, text):
    try:
        print(f"Добавляем текст: '{text}'")
        r = requests.get(image_url, timeout=10)
        img = Image.open(BytesIO(r.content)).convert('RGB')
        
        max_size = 1200
        if img.width > max_size or img.height > max_size:
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
        draw = ImageDraw.Draw(img)
        font_size = int(img.height * 0.12)
        font = None
        
        font_paths = [
           '/app/fonts/Impact.ttf',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        ]
        for font_path in font_paths:
            try:
                font = ImageFont.truetype(font_path, font_size)
                print(f"Шрифт загружен: {font_path}")
                break
            except Exception as font_err:
                print (f"Шрифт {font_path} не найден: {font_err}")
                pass
        
        if font is None:
            font = ImageFont.load_default()
            print("Используем дефолтный шрифт")
        
        max_width = img.width - 40
        words = text.split()
        lines = []
        current_line = []
        
        for word in words:
            test_line = ' '.join(current_line + [word])
            bbox = draw.textbbox((0, 0), test_line, font=font)
            if bbox[2] - bbox[0] <= max_width:
                current_line.append(word)
            else:
                lines.append(' '.join(current_line))
                current_line = [word]
        
        if current_line:
            lines.append(' '.join(current_line))
        
        y_offset = img.height - 60
        
        for line in reversed(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            x = (img.width - tw) // 2
            y = y_offset - th
            
            outline_range = 3
            for dx in range(-outline_range, outline_range + 1):
                for dy in range(-outline_range, outline_range + 1):
                    draw.text((x + dx, y + dy), line, font=font, fill='black')
            
            draw.text((x, y), line, font=font, fill='white')
            y_offset = y - 10
        
        full_output = BytesIO()
        img.save(full_output, format='JPEG', quality=90, optimize=True)
        full_output.seek(0)
        
        print("Текст добавлен")
        return full_output
        
    except Exception as e:
        print(f"Ошибка текста: {e}")
        traceback.print_exc()
        return None

@bot.message_handler(commands=['start', 'help'])
def start_command(message):
    available_commands = list(PHRASES.keys())
    commands_text = '\n'.join([f'• `@твойбот {cmd}` — фраза из "{cmd}"' for cmd in available_commands])
    
    help_text = (
        '🎨 Привет! Я бот для случайных картинок.\n\n'
        '📸 Как пользоваться:\n'
        '• Просто имя бота — случайная картинка\n'
        '• `@твойбот cats` — картинка по теме\n\n'
        '📝 Текст на картинке:\n'
        '• `@твойбот text "Привет мир"` — картинка с текстом\n'
        '• `@твойбот text "Привет" cats` — текст + тема\n\n'
        '🎭 Фразы:\n'
        f'{commands_text}\n\n'
        '🎲 Случайные фразы:\n'
        '• `@твойбот randtext` — картинка + осмысленная фраза из Fucking Great Advice\n'
        '• `@твойбот randtext 3` — 3 фразы на одной картинке\n'
        '• `@твойбот randtext природа` — фраза + картинка по теме\n'
        f'API: {", ".join(available_apis)}'
    )
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
    print(f"Inline-запрос: '{inline_query.query}' от {inline_query.from_user.id}")
    print(f"Temp images: {len(temp_images)}")

    query_text = inline_query.query.strip().lower()
    results = []

    try:
        text_to_add = None
        search_query = query_text
        is_randtext = False
        phrase_category = None

        parts = query_text.split()

        # ========== ОБНОВЛЕННЫЙ БЛОК RANDTEXT ==========
        if parts and parts[0] == 'randtext':
            is_randtext = True
            text_to_add = None
            phrase_count = 1  # по умолчанию одна фраза
            
            # Проверяем аргументы
            if len(parts) > 1:
                if parts[1].isdigit():
                    # randtext 3 - несколько фраз
                    phrase_count = min(int(parts[1]), 3)  # максимум 3 фразы
                    search_query = ' '.join(parts[2:]) if len(parts) > 2 else None
                else:
                    # randtext природа - одна фраза + тема
                    search_query = ' '.join(parts[1:])
            
            # Получаем нужное количество фраз
            if phrase_count > 1:
                phrases = []
                for i in range(phrase_count):
                    print(f"Получаем фразу {i+1} из {phrase_count}...")
                    phrase = get_russian_phrase()
                    phrases.append(phrase)
                    if i < phrase_count - 1:  # не ждем после последней
                        time.sleep(0.5)  # небольшая задержка между запросами
                text_to_add = ' | '.join(phrases)  # разделяем фразы символом |
            else:
                text_to_add = get_russian_phrase()
        
        # ========== ОСТАЛЬНЫЕ БЛОКИ БЕЗ ИЗМЕНЕНИЙ ==========
        elif parts and parts[0] == 'text':
            text_match = re.search(r'text\s+"([^"]+)"', query_text, re.IGNORECASE)
            if text_match:
                text_to_add = text_match.group(1)
                remaining = re.sub(r'text\s+"[^"]+"', '', query_text, flags=re.IGNORECASE).strip()
                search_query = remaining if remaining else None

        elif parts and parts[0] in PHRASES:
            phrase_category = parts[0]
            text_to_add = get_random_phrase(phrase_category)
            search_query = ' '.join(parts[1:]) if len(parts) > 1 else None

        elif query_text:
            search_query = query_text

        # ========== ОТПРАВКА РЕЗУЛЬТАТОВ ==========
        if is_randtext or text_to_add:
            image_url, _ = get_random_image(search_query)
            
            if image_url:
                full = add_text_to_image(image_url, text_to_add)
                if full:
                    image_id = generate_unique_id("randtext" if is_randtext else "text")
                    temp_images[image_id] = (full.getvalue(), time.time())
                    
                    hostname = os.getenv("RAILWAY_PUBLIC_DOMAIN", "localhost")
                    url = f"https://{hostname}/image/{image_id}"
                    
                    # Определяем заголовок
                    if is_randtext and phrase_count > 1:
                        title = f"{phrase_count} фразы"
                    else:
                        title = text_to_add[:30] + "..." if len(text_to_add) > 30 else text_to_add
                    
                    result = telebot.types.InlineQueryResultPhoto(
                        id=image_id,
                        photo_url=url,
                        thumbnail_url=url,
                        title=title,
                        description=text_to_add
                    )
                    results.append(result)

        else:
            image_url, thumb_url = get_random_image(search_query)
            
            if image_url and thumb_url:
                result_id = generate_unique_id("img")
                
                title = search_query or "Случайная картинка"
                
                result = telebot.types.InlineQueryResultPhoto(
                    id=result_id,
                    photo_url=image_url,
                    thumbnail_url=thumb_url,
                    photo_width=1080,
                    photo_height=720,
                    title=title,
                    description="Нажми отправить"
                )
                results.append(result)

    except Exception as e:
        print(f"Inline ошибка: {e}")
        traceback.print_exc()

    try:
        if results:
            bot.answer_inline_query(inline_query.id, results, cache_time=0, is_personal=True)
            print(f"Отправлено {len(results)} результатов")
        else:
            bot.answer_inline_query(inline_query.id, [], cache_time=0)
            print("Нет результатов")
    except Exception as e:
        print(f"Ошибка ответа inline: {e}")

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
    return (
        f'🤖 Bot работает на Railway<br>'
        f'API: {", ".join(available_apis)}<br>'
        f'Изображений в памяти: {len(temp_images)}<br>'
        f'Фраз: {sum(len(v) for v in PHRASES.values())}<br>'
        f'Домен: https://{hostname}'
    ), 200

@app.route('/health')
def health():
    return 'OK', 200

@app.route('/image/<image_id>', methods=['GET', 'HEAD'])
def serve_image(image_id):
    print(f"Запрос изображения {image_id}")
    
    if image_id in temp_images:
        image_data, timestamp = temp_images[image_id]
        
        if request.method == 'HEAD':
            response = app.make_response('')
            response.headers['Content-Type'] = 'image/jpeg'
            response.headers['Content-Length'] = str(len(image_data))
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Cache-Control'] = 'public, max-age=3600'
            # Добавляем заголовки для HTTPS
            response.headers['Content-Security-Policy'] = "default-src 'self'"
            response.headers['X-Content-Type-Options'] = 'nosniff'
            return response
        
        # Создаем ответ с изображением
        response = send_file(
            BytesIO(image_data),
            mimetype='image/jpeg',
            as_attachment=False,
            download_name=f'{image_id}.jpg'
        )
        
        # Добавляем заголовки для HTTPS
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Cache-Control'] = 'public, max-age=3600'
        response.headers['Content-Security-Policy'] = "default-src 'self'"
        response.headers['X-Content-Type-Options'] = 'nosniff'
        
        return response
        
    print(f"Изображение {image_id} не найдено")
    abort(404)

if __name__ == '__main__':
    setup_webhook()
    app.run(host='0.0.0.0', port=PORT, debug=False)
else:
    setup_webhook()