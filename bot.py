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
        print(f"📚 Доступные категории: {', '.join(phrases.keys())}")
        return phrases
    except FileNotFoundError:
        print("⚠️ Файл phrases.json не найден, создаем дефолтный")
        default_phrases = {
            "papich": ["Хорош, хорош!", "Это база!", "Красавчик!", "Топчик!", "Вайб", "Хайпово"],
            "tehnik": ["Техника - молодёжь!", "Батя", "Здарова, пацаны!", "Погнали!", "Заряжай!"],
            "stethem": ["Где деньги, Лиза?", "Ты кто по жизни?", "Заберите у него тапки", "Слабоумие и отвага"],
            "mat": ["#@!$%", "***", "#$%@", "!@#$%^&"],
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

# Инициализируем слова
fetch_russian_words()

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

def get_random_phrase(category="random"):
    """Возвращает случайную фразу из указанной категории"""
    if category in PHRASES and PHRASES[category]:
        return random.choice(PHRASES[category])
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

def add_text_to_image(image_url, text):
    """Добавляет текст на картинку"""
    try:
        print(f"📝 Добавляем текст: '{text}'")
        
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
                print(f"✅ Используем шрифт: {font_path}")
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
        import traceback
        print(traceback.format_exc())
        return None, None

def create_collage(image_urls, count):
    """Создает коллаж из нескольких картинок"""
    try:
        print(f"🎨 Создаем коллаж из {count} картинок")
        
        images = []
        for url in image_urls[:count]:
            try:
                response = requests.get(url, timeout=10)
                img = Image.open(BytesIO(response.content))
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                images.append(img)
            except Exception as e:
                print(f"❌ Ошибка загрузки картинки: {e}")
                continue
        
        if not images:
            return None, None
        
        if count <= 4:
            cols = 2
            rows = (count + 1) // 2
        elif count <= 9:
            cols = 3
            rows = (count + 2) // 3
        else:
            cols = 4
            rows = (count + 3) // 4
        
        cell_width = 400
        cell_height = 400
        
        collage_width = cols * cell_width
        collage_height = rows * cell_height
        collage = Image.new('RGB', (collage_width, collage_height), 'white')
        
        for idx, img in enumerate(images):
            img.thumbnail((cell_width, cell_height), Image.Resampling.LANCZOS)
            
            col = idx % cols
            row = idx // cols
            
            x = col * cell_width + (cell_width - img.width) // 2
            y = row * cell_height + (cell_height - img.height) // 2
            
            collage.paste(img, (x, y))
        
        thumb = collage.copy()
        thumb.thumbnail((200, 200), Image.Resampling.LANCZOS)
        
        full_output = BytesIO()
        collage.save(full_output, format='JPEG', quality=85)
        full_output.seek(0)
        
        thumb_output = BytesIO()
        thumb.save(thumb_output, format='JPEG', quality=70)
        thumb_output.seek(0)
        
        return full_output, thumb_output
        
    except Exception as e:
        print(f"❌ Ошибка создания коллажа: {e}")
        return None, None

def create_collage_with_text(image_urls, count, text):
    """Создает коллаж и добавляет текст сверху"""
    try:
        collage_full, collage_thumb = create_collage(image_urls, count)
        if not collage_full:
            return None, None
        
        collage = Image.open(BytesIO(collage_full.getvalue()))
        draw = ImageDraw.Draw(collage)
        
        font_size = int(collage.height * 0.1)
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
        max_width = collage.width - 80
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
        total_text_height = 0
        line_heights = []
        
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_height = bbox[3] - bbox[1]
            line_heights.append(line_height)
            total_text_height += line_height + 10
        
        y_offset = collage.height - total_text_height - 40
        
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            
            x = (collage.width - text_width) // 2
            y = y_offset
            
            outline_range = max(3, font_size // 20)
            for adj_x in range(-outline_range, outline_range + 1):
                for adj_y in range(-outline_range, outline_range + 1):
                    draw.text((x + adj_x, y + adj_y), line, font=font, fill='black')
            
            draw.text((x, y), line, font=font, fill='white')
            y_offset += line_heights[i] + 10
        
        full_output = BytesIO()
        collage.save(full_output, format='JPEG', quality=85)
        full_output.seek(0)
        
        thumb = collage.copy()
        thumb.thumbnail((200, 200), Image.Resampling.LANCZOS)
        thumb_output = BytesIO()
        thumb.save(thumb_output, format='JPEG', quality=70)
        thumb_output.seek(0)
        
        return full_output, thumb_output
        
    except Exception as e:
        print(f"❌ Ошибка создания коллажа с текстом: {e}")
        return None, None

@bot.message_handler(commands=['start', 'help'])
def start_command(message):
    help_text = (
        '🎨 *Привет! Я бот для работы с картинками.*\n\n'
        '📸 *Inline команды:*\n'
        '• `@bot` — показать меню (4 кнопки)\n'
        '• `@bot random` — случайная картинка\n'
        '• `@bot mem` — случайный мем\n'
        '• `@bot phrase` — картинка со случайной фразой\n'
        '• `@bot words` — картинка со случайными словами\n\n'
        '📝 *Текст и коллажи:*\n'
        '• `@bot text "Привет"` — картинка с текстом\n'
        '• `@bot text "Привет" cats` — картинка с котами и текстом\n'
        '• `@bot 5` — коллаж из 5 картинок\n'
        '• `@bot 5 cats` — коллаж из 5 котов\n'
        '• `@bot 5 papich cats` — коллаж из 5 котов с фразой из papich\n\n'
        '🎭 *Категории:* ' + ', '.join([f'`{cmd}`' for cmd in PHRASES.keys() if cmd != 'random'])
    )
    bot.reply_to(message, help_text, parse_mode='Markdown')

@bot.inline_handler(lambda query: True)
def inline_handler(inline_query):
    print(f"📥 Получен inline-запрос: '{inline_query.query}'")

    query_text = inline_query.query.strip()
    results = []

    # Если запрос пустой - показываем 4 кнопки как inline результаты
    if not query_text:
        # Создаем 4 отдельных результата-кнопки
        btn1 = InlineQueryResultArticle(
            id="btn_random",
            title="🖼️ Случайная картинка",
            description="Просто случайная картинка",
            input_message_content=InputTextMessageContent("."),
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🖼️ Случайная", switch_inline_query_current_chat="random")
            )
        )
        
        btn2 = InlineQueryResultArticle(
            id="btn_mem",
            title="😂 Мем",
            description="Случайный мем",
            input_message_content=InputTextMessageContent("."),
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("😂 Мем", switch_inline_query_current_chat="mem")
            )
        )
        
        btn3 = InlineQueryResultArticle(
            id="btn_phrase",
            title="📝 Рандом текст",
            description="Картинка со случайной фразой",
            input_message_content=InputTextMessageContent("."),
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("📝 Фраза", switch_inline_query_current_chat="phrase")
            )
        )
        
        btn4 = InlineQueryResultArticle(
            id="btn_words",
            title="🎲 Рандом слова",
            description="Картинка со случайными словами",
            input_message_content=InputTextMessageContent("."),
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🎲 Слова", switch_inline_query_current_chat="words")
            )
        )
        
        results = [btn1, btn2, btn3, btn4]
        bot.answer_inline_query(inline_query.id, results, cache_time=0, is_personal=True)
        return

    # Обрабатываем команды
    try:
        # Парсим сложные команды
        collage_count = None
        text_to_add = None
        search_query = None
        is_meme = False
        is_phrase = False
        is_words = False
        category = None
        
        parts = query_text.lower().split()
        
        # Проверяем на простые команды
        if query_text == 'random':
            pass  # просто случайная картинка
        elif query_text == 'mem':
            is_meme = True
        elif query_text == 'phrase':
            is_phrase = True
            text_to_add = get_random_phrase()
        elif query_text == 'words':
            is_words = True
            text_to_add = get_random_russian_words(3)
        
        # Проверяем на text команду
        elif query_text.startswith('text'):
            text_match = re.search(r'text\s+"([^"]+)"', query_text, re.IGNORECASE)
            if text_match:
                text_to_add = text_match.group(1)
                remaining = re.sub(r'text\s+"[^"]+"', '', query_text, flags=re.IGNORECASE).strip()
                
                # Проверяем на коллаж
                if remaining and remaining.split()[0].isdigit():
                    parts = remaining.split()
                    collage_count = int(parts[0])
                    if collage_count < 2:
                        collage_count = 2
                    elif collage_count > 10:
                        collage_count = 10
                    search_query = ' '.join(parts[1:]) if len(parts) > 1 else None
                else:
                    search_query = remaining if remaining else None
                
                print(f"📝 Text команда: '{text_to_add}', коллаж: {collage_count}, поиск: {search_query}")
        
        # Проверяем на коллаж с категорией
        elif parts and parts[0].isdigit():
            collage_count = int(parts[0])
            if collage_count < 2:
                collage_count = 2
            elif collage_count > 10:
                collage_count = 10
            
            if len(parts) > 1:
                if parts[1] in PHRASES:
                    category = parts[1]
                    text_to_add = get_random_phrase(category)
                    search_query = ' '.join(parts[2:]) if len(parts) > 2 else None
                else:
                    search_query = ' '.join(parts[1:])
            
            print(f"🎨 Коллаж: {collage_count}, категория: {category}, поиск: {search_query}")
        
        # Проверяем на категорию
        elif parts and parts[0] in PHRASES:
            category = parts[0]
            text_to_add = get_random_phrase(category)
            search_query = ' '.join(parts[1:]) if len(parts) > 1 else None
            print(f"🎭 Категория: {category}, текст: {text_to_add}, поиск: {search_query}")
        
        # Если ничего не подошло - обычный поиск
        elif query_text:
            search_query = query_text
            print(f"🔍 Поиск: {search_query}")
        
        # Получаем картинку(и)
        if collage_count:
            # Коллаж
            image_urls = []
            for i in range(collage_count):
                img_url, _ = get_random_image(search_query, meme_mode=is_meme)
                if img_url:
                    image_urls.append(img_url)
                time.sleep(0.1)
            
            if len(image_urls) >= 2:
                if text_to_add:
                    collage_full, collage_thumb = create_collage_with_text(image_urls, len(image_urls), text_to_add)
                else:
                    collage_full, collage_thumb = create_collage(image_urls, len(image_urls))
                
                if collage_full and collage_thumb:
                    image_id = generate_unique_id("collage")
                    thumb_id = f"thumb_{image_id}"
                    
                    temp_images[image_id] = (collage_full.getvalue(), time.time())
                    temp_images[thumb_id] = (collage_thumb.getvalue(), time.time())
                    
                    hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "tgbotrandompic.onrender.com")
                    collage_url = f"https://{hostname}/image/{image_id}"
                    thumb_url = f"https://{hostname}/image/{thumb_id}"
                    
                    title = f"🎨 {text_to_add[:30]}" if text_to_add else f"🎨 Коллаж {collage_count}"
                    
                    result = telebot.types.InlineQueryResultPhoto(
                        id=image_id,
                        photo_url=collage_url,
                        thumbnail_url=thumb_url,
                        title=title,
                        description=text_to_add if text_to_add else f"{search_query or 'Случайные'}"
                    )
                    results.append(result)
        else:
            # Одиночная картинка
            image_url, thumb_url = get_random_image(search_query, meme_mode=is_meme)
            
            if image_url:
                if text_to_add or is_phrase or is_words:
                    if not text_to_add:
                        if is_phrase:
                            text_to_add = get_random_phrase()
                        elif is_words:
                            text_to_add = get_random_russian_words(3)
                    
                    img_full, img_thumb = add_text_to_image(image_url, text_to_add)
                    if img_full and img_thumb:
                        image_id = generate_unique_id("text")
                        thumb_id = f"thumb_{image_id}"
                        
                        temp_images[image_id] = (img_full.getvalue(), time.time())
                        temp_images[thumb_id] = (img_thumb.getvalue(), time.time())
                        
                        hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "tgbotrandompic.onrender.com")
                        img_url = f"https://{hostname}/image/{image_id}"
                        thumb_url = f"https://{hostname}/image/{thumb_id}"
                        
                        title = "📝 Фраза" if is_phrase else "🎲 Слова" if is_words else f"📝 {text_to_add[:30]}"
                        
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
                    title = "😂 Мем" if is_meme else f"📸 {search_query}" if search_query else "🖼️ Случайная"
                    
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
        import traceback
        print(traceback.format_exc())

    try:
        if results:
            bot.answer_inline_query(inline_query.id, results, cache_time=0, is_personal=True)
            print(f"✅ Отправлено {len(results)} результатов")
        else:
            # Если нет результатов, показываем меню
            btn1 = InlineQueryResultArticle(
                id="btn_random",
                title="🖼️ Случайная картинка",
                description="Просто случайная картинка",
                input_message_content=InputTextMessageContent("."),
                reply_markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("🖼️ Случайная", switch_inline_query_current_chat="random")
                )
            )
            bot.answer_inline_query(inline_query.id, [btn1], cache_time=0, is_personal=True)
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