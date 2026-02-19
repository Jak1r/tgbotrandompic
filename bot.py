import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, InlineQueryResultArticle, InputTextMessageContent
import random
import requests
from flask import Flask, request, abort, send_file
from dotenv import load_dotenv
import time
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import re
import threading
import json
import uuid

# Загружаем переменные окружения
load_dotenv()

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
UNSPLASH_ACCESS_KEY = os.environ.get('UNSPLASH_ACCESS_KEY')
PEXELS_API_KEY = os.environ.get('PEXELS_API_KEY')
PIXABAY_API_KEY = os.environ.get('PIXABAY_API_KEY')
PORT = int(os.environ.get('PORT', 10000))

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не задан в переменных окружения")

# Проверяем какие API ключи доступны
available_apis = []
if UNSPLASH_ACCESS_KEY:
    available_apis.append('unsplash')
    print("✅ Unsplash API доступен")
if PEXELS_API_KEY:
    available_apis.append('pexels')
    print("✅ Pexels API доступен")
if PIXABAY_API_KEY:
    available_apis.append('pixabay')
    print("✅ Pixabay API доступен")

if not available_apis:
    raise ValueError("Нет доступных API ключей!")

print(f"🔑 Доступно API: {', '.join(available_apis)}")

# Загружаем фразы из JSON
def load_phrases():
    try:
        with open('phrases.json', 'r', encoding='utf-8') as f:
            phrases = json.load(f)
        print(f"✅ Загружено {sum(len(v) for v in phrases.values())} фраз из phrases.json")
        return phrases
    except FileNotFoundError:
        print("⚠️ Файл phrases.json не найден, создаем дефолтный")
        default_phrases = {
            "random": ["Удача", "Красота", "Счастье", "Любовь", "Дружба", "Мечта", "Успех", "Победа", "Радость", "Вдохновение"]
        }
        with open('phrases.json', 'w', encoding='utf-8') as f:
            json.dump(default_phrases, f, ensure_ascii=False, indent=2)
        return default_phrases
    except Exception as e:
        print(f"❌ Ошибка загрузки phrases.json: {e}")
        return {"random": ["Случайная фраза"]}

PHRASES = load_phrases()

# Список тем для случайного выбора
RANDOM_QUERIES = [
    'nature', 'city', 'abstract', 'people', 'animals', 'food',
    'travel', 'space', 'art', 'technology', 'mountain', 'ocean',
    'forest', 'sunset', 'flowers', 'architecture', 'beach', 'winter'
]

# Кэш для русских слов
words_cache = []

def fetch_russian_words():
    """Загружает русские слова из интернета"""
    global words_cache
    
    if words_cache:
        return words_cache
    
    try:
        print("🌐 Загружаем русские слова из интернета...")
        
        sources = [
            "https://raw.githubusercontent.com/danakt/russian-words/master/russian.txt"
        ]
        
        all_words = []
        for source in sources:
            try:
                response = requests.get(source, timeout=10)
                if response.status_code == 200:
                    words = response.text.splitlines()
                    russian_words = [w.lower() for w in words 
                                   if w and len(w) >= 3 and len(w) <= 15 
                                   and all('а' <= c <= 'я' or c == 'ё' for c in w.lower())]
                    all_words.extend(russian_words[:2000])
                    print(f"✅ Загружено {len(russian_words[:2000])} слов")
            except Exception as e:
                print(f"⚠️ Ошибка загрузки: {e}")
        
        if all_words:
            words_cache = list(set(all_words))
            return words_cache
        else:
            words_cache = ['мир', 'дом', 'лес', 'река', 'гора', 'море', 'солнце', 'небо']
            return words_cache
            
    except Exception as e:
        print(f"❌ Ошибка загрузки слов: {e}")
        return ['случайные', 'русские', 'слова']

def get_meme_image():
    """Получает случайный мем"""
    try:
        response = requests.get("https://api.imgflip.com/get_memes", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data['success']:
                memes = data['data']['memes']
                meme = random.choice(memes)
                return meme['url'], meme['url']
        
        return None, None
    except Exception as e:
        print(f"❌ Ошибка получения мема: {e}")
        return None, None

# Инициализируем слова
fetch_russian_words()

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
app = Flask(__name__)

# Счетчик для ротации API
current_api_index = 0

# Временное хранилище для сгенерированных картинок
temp_images = {}

def generate_unique_id(prefix="img"):
    """Генерирует уникальный ID для inline результата"""
    timestamp = int(time.time() * 1000)
    random_part = random.randint(10000, 99999)
    return f"{prefix}_{timestamp}_{random_part}"

def get_random_phrase():
    """Возвращает случайную фразу из категории random"""
    if "random" in PHRASES and PHRASES["random"]:
        return random.choice(PHRASES["random"])
    return "Случайная фраза"

def get_random_russian_words(count=3):
    """Возвращает случайные русские слова"""
    global words_cache
    if not words_cache:
        words_cache = fetch_russian_words()
    
    if words_cache and len(words_cache) >= count:
        selected = random.sample(words_cache, count)
        return ' '.join(selected)
    return "случайные слова"

def cleanup_temp_images():
    """Очищает старые картинки из памяти каждые 10 минут"""
    while True:
        time.sleep(600)
        current_time = time.time()
        to_delete = []
        
        for image_id, (data, timestamp) in temp_images.items():
            if current_time - timestamp > 900:
                to_delete.append(image_id)
        
        for image_id in to_delete:
            del temp_images[image_id]
            
        if to_delete:
            print(f"🧹 Очищено {len(to_delete)} старых картинок")

cleanup_thread = threading.Thread(target=cleanup_temp_images, daemon=True)
cleanup_thread.start()

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
                print(f"✅ Webhook установлен на: {webhook_url}")
            else:
                print("❌ Не удалось установить webhook")
        else:
            print(f"✅ Webhook уже установлен")
    except Exception as e:
        print(f"❌ Ошибка при установке webhook: {e}")

# Функции для работы с API
def get_unsplash_image(query):
    url = f'https://api.unsplash.com/photos/random?query={query}&client_id={UNSPLASH_ACCESS_KEY}'
    
    try:
        response = requests.get(url, timeout=10)
        
        if response.status_code == 429:
            return None, None, True
        
        response.raise_for_status()
        data = response.json()
        
        urls = data.get('urls', {})
        image_url = urls.get('regular')
        thumb_url = urls.get('thumb')
        
        return image_url, thumb_url, False
        
    except Exception as e:
        print(f"❌ Ошибка Unsplash: {e}")
        return None, None, False

def get_pexels_image(query):
    url = f'https://api.pexels.com/v1/search?query={query}&per_page=1&page={random.randint(1, 100)}'
    
    headers = {
        'Authorization': PEXELS_API_KEY
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 429:
            return None, None, True
        
        response.raise_for_status()
        data = response.json()
        
        if data.get('photos') and len(data['photos']) > 0:
            photo = data['photos'][0]
            image_url = photo['src']['large']
            thumb_url = photo['src']['small']
            
            return image_url, thumb_url, False
        else:
            return None, None, False
            
    except Exception as e:
        print(f"❌ Ошибка Pexels: {e}")
        return None, None, False

def get_pixabay_image(query):
    url = f'https://pixabay.com/api/?key={PIXABAY_API_KEY}&q={query}&image_type=photo&per_page=3&page={random.randint(1, 50)}'
    
    try:
        response = requests.get(url, timeout=10)
        
        if response.status_code == 429:
            return None, None, True
        
        response.raise_for_status()
        data = response.json()
        
        if data.get('hits') and len(data['hits']) > 0:
            photo = random.choice(data['hits'])
            image_url = photo['largeImageURL']
            thumb_url = photo['previewURL']
            
            return image_url, thumb_url, False
        else:
            return None, None, False
            
    except Exception as e:
        print(f"❌ Ошибка Pixabay: {e}")
        return None, None, False

def get_random_image(custom_query=None, meme_mode=False):
    global current_api_index
    
    if meme_mode:
        return get_meme_image()
    
    query = custom_query or random.choice(RANDOM_QUERIES)
    
    for attempt in range(len(available_apis)):
        api_name = available_apis[current_api_index]
        
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
    
    return None, None

# Функции для работы с изображениями
def add_text_to_image(image_url, text):
    """Добавляет текст на картинку"""
    try:
        response = requests.get(image_url, timeout=10)
        img = Image.open(BytesIO(response.content))
        
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        max_size = 1200
        if img.width > max_size or img.height > max_size:
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
        draw = ImageDraw.Draw(img)
        
        font_size = int(img.height * 0.08)
        font = None
        
        font_paths = [
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
            '/System/Library/Fonts/Helvetica.ttc',
            'C:\\Windows\\Fonts\\Arial.ttf',
        ]
        
        for font_path in font_paths:
            try:
                font = ImageFont.truetype(font_path, font_size)
                break
            except:
                continue
        
        if font is None:
            font = ImageFont.load_default()
        
        # Разбиваем текст на строки
        max_width = img.width - 40
        words = text.split()
        lines = []
        current_line = []
        
        for word in words:
            test_line = ' '.join(current_line + [word])
            bbox = draw.textbbox((0, 0), test_line, font=font)
            text_width = bbox[2] - bbox[0]
            
            if text_width <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
        
        if current_line:
            lines.append(' '.join(current_line))
        
        # Рисуем текст
        y_offset = img.height - 60
        
        for line in reversed(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            x = (img.width - text_width) // 2
            y = y_offset - text_height
            
            # Обводка
            outline_range = 3
            for adj_x in range(-outline_range, outline_range + 1):
                for adj_y in range(-outline_range, outline_range + 1):
                    draw.text((x + adj_x, y + adj_y), line, font=font, fill='black')
            
            draw.text((x, y), line, font=font, fill='white')
            y_offset = y - 10
        
        thumb = img.copy()
        thumb.thumbnail((200, 200), Image.Resampling.LANCZOS)
        
        full_output = BytesIO()
        img.save(full_output, format='JPEG', quality=90)
        full_output.seek(0)
        
        thumb_output = BytesIO()
        thumb.save(thumb_output, format='JPEG', quality=70)
        thumb_output.seek(0)
        
        return full_output, thumb_output
        
    except Exception as e:
        print(f"❌ Ошибка добавления текста: {e}")
        return None, None

@bot.message_handler(commands=['start', 'help'])
def start_command(message):
    help_text = (
        '🎨 *Привет! Я бот для работы с картинками.*\n\n'
        '📸 *Как пользоваться:*\n'
        '• Введи `@имя_бота` и выбери действие из меню\n\n'
        '📋 *Доступные действия:*\n'
        '• 🖼️ *Случайная* — случайная картинка\n'
        '• 😂 *Мем* — случайный мем\n'
        '• 📝 *Рандом текст* — картинка со случайной фразой\n'
        '• 🎲 *Рандом слова* — картинка со случайными словами\n\n'
        f'🔑 Используемые API: {", ".join(available_apis)}'
    )
    bot.reply_to(message, help_text, parse_mode='Markdown')

@bot.inline_handler(lambda query: True)
def inline_handler(inline_query):
    print(f"📥 Получен inline-запрос: '{inline_query.query}'")

    query_text = inline_query.query.strip().lower()
    results = []

    # Всегда показываем меню с 4 кнопками
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    # 4 основные кнопки
    btn1 = InlineKeyboardButton("🖼️ Случайная", switch_inline_query_current_chat="random")
    btn2 = InlineKeyboardButton("😂 Мем", switch_inline_query_current_chat="mem")
    btn3 = InlineKeyboardButton("📝 Рандом текст", switch_inline_query_current_chat="phrase")
    btn4 = InlineKeyboardButton("🎲 Рандом слова", switch_inline_query_current_chat="words")
    
    keyboard.add(btn1, btn2)
    keyboard.add(btn3, btn4)
    
    # Добавляем статью с кнопками
    menu_result = InlineQueryResultArticle(
        id="menu",
        title="📋 Меню команд",
        description="Выберите действие: случайная, мем, текст или слова",
        input_message_content=InputTextMessageContent(
            "Выберите действие в меню ниже 👇\n\n"
            "🖼️ Случайная - случайная картинка\n"
            "😂 Мем - случайный мем\n"
            "📝 Рандом текст - картинка со случайной фразой\n"
            "🎲 Рандом слова - картинка со случайными словами"
        ),
        reply_markup=keyboard
    )
    results.append(menu_result)

    # Если есть текст запроса, обрабатываем команды
    if query_text:
        try:
            text_to_add = None
            is_meme = False
            
            # Определяем тип запроса
            if query_text == 'mem':
                is_meme = True
            elif query_text == 'phrase':
                text_to_add = get_random_phrase()
            elif query_text == 'words':
                text_to_add = get_random_russian_words(3)
            elif query_text == 'random':
                pass  # просто случайная картинка
            
            # Получаем картинку
            image_url, thumb_url = get_random_image(meme_mode=is_meme)
            
            if image_url:
                if text_to_add:
                    # Картинка с текстом
                    img_full, img_thumb = add_text_to_image(image_url, text_to_add)
                    if img_full and img_thumb:
                        image_id = generate_unique_id("text")
                        thumb_id = f"thumb_{image_id}"
                        
                        temp_images[image_id] = (img_full.getvalue(), time.time())
                        temp_images[thumb_id] = (img_thumb.getvalue(), time.time())
                        
                        hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "tgbotrandompic.onrender.com")
                        img_url = f"https://{hostname}/image/{image_id}"
                        thumb_url = f"https://{hostname}/image/{thumb_id}"
                        
                        # Определяем заголовок
                        if query_text == 'phrase':
                            title = "📝 Случайная фраза"
                        else:
                            title = "🎲 Случайные слова"
                        
                        result = telebot.types.InlineQueryResultPhoto(
                            id=image_id,
                            photo_url=img_url,
                            thumbnail_url=thumb_url,
                            title=title,
                            description=text_to_add
                        )
                        results.append(result)
                else:
                    # Обычная картинка
                    result_id = generate_unique_id("img")
                    title = "😂 Мем" if is_meme else "🖼️ Случайная картинка"
                    
                    result = telebot.types.InlineQueryResultPhoto(
                        id=result_id,
                        photo_url=image_url,
                        thumbnail_url=thumb_url or image_url,
                        title=title,
                        description="Нажми, чтобы отправить"
                    )
                    results.append(result)
                    
        except Exception as e:
            print(f"❌ Ошибка: {e}")

    try:
        bot.answer_inline_query(inline_query.id, results, cache_time=0, is_personal=True)
        print(f"✅ Отправлено {len(results)} результатов")
    except Exception as e:
        print(f"❌ Ошибка ответа: {e}")

# Flask роуты
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
    else:
        abort(403)

@app.route('/')
def index():
    return f'🤖 Bot is running! APIs: {", ".join(available_apis)}', 200

@app.route('/health')
def health():
    return 'OK', 200

@app.route('/image/<image_id>', methods=['GET', 'HEAD'])
def serve_image(image_id):
    if image_id in temp_images:
        image_data, _ = temp_images[image_id]
        
        if request.method == 'HEAD':
            response = app.make_response('')
            response.headers['Content-Type'] = 'image/jpeg'
            response.headers['Content-Length'] = str(len(image_data))
            response.headers['Access-Control-Allow-Origin'] = '*'
            return response
        
        response = send_file(
            BytesIO(image_data),
            mimetype='image/jpeg',
            as_attachment=False
        )
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
    
    abort(404)

if __name__ != '__main__':
    setup_webhook()