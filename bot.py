import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
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
import sys
import traceback

print("=== START bot.py ===")
print(f"Python version: {sys.version}")
print(f"Working directory: {os.getcwd()}")

# ───────────────────────────────────────────────
# Переменные окружения
# ───────────────────────────────────────────────

load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
UNSPLASH_ACCESS_KEY = os.getenv('UNSPLASH_ACCESS_KEY')
PEXELS_API_KEY = os.getenv('PEXELS_API_KEY')
PIXABAY_API_KEY = os.getenv('PIXABAY_API_KEY')

PORT = int(os.getenv('PORT', 8080))  # Railway использует 8080

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не задан в переменных окружения")

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

# ───────────────────────────────────────────────
# Фразы из JSON
# ───────────────────────────────────────────────

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
            "papich": ["Хорош, хорош!", "Это база!", "Красавчик!", "Топчик!", "Вайб", "Хайпово", "Пальчик вверх", "Лучше всех!", "Огонь!", "Зашло!"],
            "tehnik": ["Техника - молодёжь!", "Батя", "Здарова, пацаны!", "Погнали!", "Заряжай!", "Кто не курит и не пьёт - тот здоровеньким помрёт", "Эх, техника!", "Молодёжка", "Будь здоров!"],
            "stethem": ["Где деньги, Лиза?", "Ты кто по жизни?", "Заберите у него тапки", "Слабоумие и отвага", "Ты не пройдешь", "Где паспорт?", "Ты меня уважаешь?", "Аниме - говно"],
            "mat": ["#@!$%", "***", "#$%@", "!@#$%^&", "***!!!", "@#$%", "!@#$"],
            "random": ["Удача", "Красота", "Счастье", "Любовь", "Дружба", "Мечта", "Успех", "Победа", "Радость", "Вдохновение", "Свобода", "Гармония", "Мудрость", "Сила", "Доброта"]
        }
        with open('phrases.json', 'w', encoding='utf-8') as f:
            json.dump(default_phrases, f, ensure_ascii=False, indent=2)
        return default_phrases
    except Exception as e:
        print(f"❌ Ошибка загрузки phrases.json: {e}")
        return {}

PHRASES = load_phrases()

# Список тем для случайного выбора
RANDOM_QUERIES = [
    'nature', 'city', 'abstract', 'people', 'animals', 'food',
    'travel', 'space', 'art', 'technology', 'mountain', 'ocean',
    'forest', 'sunset', 'flowers', 'architecture', 'beach', 'winter'
]

# ───────────────────────────────────────────────
# Русские слова
# ───────────────────────────────────────────────

words_cache = []

def fetch_russian_words():
    global words_cache
    
    if words_cache:
        return words_cache
    
    try:
        print("🌐 Загружаем русские слова из интернета...")
        
        sources = [
            "https://raw.githubusercontent.com/danakt/russian-words/master/russian.txt",
            "https://raw.githubusercontent.com/Koziev/ruwordnet/master/data/words.txt"
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
                    all_words.extend(russian_words)
                    print(f"✅ Загружено {len(russian_words)} слов из {source}")
            except Exception as e:
                print(f"⚠️ Ошибка загрузки из {source}: {e}")
        
        if all_words:
            words_cache = list(set(all_words))
            print(f"✅ Всего загружено {len(words_cache)} русских слов")
            return words_cache
        else:
            words_cache = [
                'мир', 'дом', 'лес', 'река', 'гора', 'море', 'солнце', 'небо', 'трава', 'цветок',
                'кот', 'собака', 'птица', 'рыба', 'дерево', 'ветер', 'дождь', 'снег', 'огонь', 'вода',
                'книга', 'стол', 'стул', 'окно', 'дверь', 'комната', 'город', 'улица', 'дорога', 'машина',
                'человек', 'друг', 'семья', 'мама', 'папа', 'брат', 'сестра', 'ребенок', 'имя', 'слово',
                'время', 'день', 'ночь', 'утро', 'вечер', 'год', 'месяц', 'неделя', 'час', 'минута'
            ]
            return words_cache
            
    except Exception as e:
        print(f"❌ Ошибка загрузки слов: {e}")
        return ['случайные', 'русские', 'слова']

fetch_russian_words()

# ───────────────────────────────────────────────
# Инициализация
# ───────────────────────────────────────────────

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
app = Flask(__name__)

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

def get_random_russian_words(count=3):
    global words_cache
    if not words_cache:
        words_cache = fetch_russian_words()
    
    if words_cache and len(words_cache) >= count:
        selected = random.sample(words_cache, count)
        return ' '.join(selected)
    return "случайные слова"

def cleanup_temp_images():
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
            print(f"🧹 Очищено {len(to_delete)} старых картинок из памяти")

cleanup_thread = threading.Thread(target=cleanup_temp_images, daemon=True)
cleanup_thread.start()

def setup_webhook():
    hostname = os.getenv("RAILWAY_PUBLIC_DOMAIN")
    if not hostname:
        print("RAILWAY_PUBLIC_DOMAIN не найден → локальный режим?")
        return

    webhook_path = f"/{TELEGRAM_TOKEN}"
    webhook_url = f"https://{hostname}{webhook_path}"
    
    try:
        current_webhook = bot.get_webhook_info()
        if current_webhook.url != webhook_url:
            bot.remove_webhook()
            time.sleep(1)
            success = bot.set_webhook(url=webhook_url)
            print(f"✅ Webhook {'установлен' if success else 'НЕ УСТАНОВЛЕН'}: {webhook_url}")
        else:
            print(f"✅ Webhook уже установлен правильно: {webhook_url}")
    except Exception as e:
        print(f"❌ Ошибка при установке webhook: {e}")
        traceback.print_exc()

# ───────────────────────────────────────────────
# Функции получения изображений
# ───────────────────────────────────────────────

def get_unsplash_image(query):
    url = f'https://api.unsplash.com/photos/random?query={query}&client_id={UNSPLASH_ACCESS_KEY}'
    
    try:
        response = requests.get(url, timeout=10)
        
        if response.status_code == 429:
            print(f"⚠️ Unsplash rate limit достигнут")
            return None, None, True
        
        response.raise_for_status()
        data = response.json()
        
        urls = data.get('urls', {})
        image_url = urls.get('regular')
        thumb_url = urls.get('thumb')
        
        print(f"✅ Unsplash: получена картинка")
        return image_url, thumb_url, False
        
    except Exception as e:
        print(f"❌ Ошибка Unsplash: {e}")
        return None, None, False

def get_pexels_image(query):
    url = f'https://api.pexels.com/v1/search?query={query}&per_page=1&page={random.randint(1, 100)}'
    
    headers = {'Authorization': PEXELS_API_KEY}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 429:
            print(f"⚠️ Pexels rate limit достигнут")
            return None, None, True
        
        response.raise_for_status()
        data = response.json()
        
        if data.get('photos') and len(data['photos']) > 0:
            photo = data['photos'][0]
            image_url = photo['src']['large']
            thumb_url = photo['src']['small']
            
            print(f"✅ Pexels: получена картинка")
            return image_url, thumb_url, False
        else:
            print(f"⚠️ Pexels: нет результатов для '{query}'")
            return None, None, False
            
    except Exception as e:
        print(f"❌ Ошибка Pexels: {e}")
        return None, None, False

def get_pixabay_image(query):
    url = f'https://pixabay.com/api/?key={PIXABAY_API_KEY}&q={query}&image_type=photo&per_page=3&page={random.randint(1, 50)}'
    
    try:
        response = requests.get(url, timeout=10)
        
        if response.status_code == 429:
            print(f"⚠️ Pixabay rate limit достигнут")
            return None, None, True
        
        response.raise_for_status()
        data = response.json()
        
        if data.get('hits') and len(data['hits']) > 0:
            photo = random.choice(data['hits'])
            image_url = photo['largeImageURL']
            thumb_url = photo['previewURL']
            
            print(f"✅ Pixabay: получена картинка")
            return image_url, thumb_url, False
        else:
            print(f"⚠️ Pixabay: нет результатов для '{query}'")
            return None, None, False
            
    except Exception as e:
        print(f"❌ Ошибка Pixabay: {e}")
        return None, None, False

def get_random_image(custom_query=None):
    global current_api_index
    
    query = custom_query or random.choice(RANDOM_QUERIES)
    
    for attempt in range(len(available_apis)):
        api_name = available_apis[current_api_index]
        
        print(f"🔄 Попытка #{attempt + 1}: используем {api_name.upper()}")
        
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
            print(f"⚠️ {api_name.upper()} rate limit, переключаемся")
            current_api_index = (current_api_index + 1) % len(available_apis)
            continue
        
        current_api_index = (current_api_index + 1) % len(available_apis)
    
    print(f"❌ Все API не вернули результат для '{query}'")
    return None, None

# ───────────────────────────────────────────────
# Коллаж
# ───────────────────────────────────────────────

def create_collage(image_urls, count):
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
        collage.save(full_output, format='JPEG', quality=85, optimize=True)
        full_output.seek(0)
        
        thumb_output = BytesIO()
        thumb.save(thumb_output, format='JPEG', quality=70, optimize=True)
        thumb_output.seek(0)
        
        print(f"✅ Коллаж создан ({collage_width}x{collage_height})")
        return full_output, thumb_output
        
    except Exception as e:
        print(f"❌ Ошибка коллажа: {e}")
        traceback.print_exc()
        return None, None

# ───────────────────────────────────────────────
# Текст на картинке
# ───────────────────────────────────────────────

def add_text_to_image(image_url, text):
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
        ]
        
        for font_path in font_paths:
            try:
                font = ImageFont.truetype(font_path, font_size)
                print(f"✅ Шрифт: {font_path}")
                break
            except:
                continue
        
        if font is None:
            print("⚠️ Шрифт не найден → дефолтный")
            font = ImageFont.load_default()
        
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
        
        y_offset = img.height - 60
        
        for line in reversed(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            x = (img.width - text_width) // 2
            y = y_offset - text_height
            
            outline_range = 3
            for adj_x in range(-outline_range, outline_range + 1):
                for adj_y in range(-outline_range, outline_range + 1):
                    draw.text((x + adj_x, y + adj_y), line, font=font, fill='black')
            
            draw.text((x, y), line, font=font, fill='white')
            y_offset = y - 10
        
        thumb = img.copy()
        thumb.thumbnail((200, 200), Image.Resampling.LANCZOS)
        
        full_output = BytesIO()
        img.save(full_output, format='JPEG', quality=90, optimize=True)
        full_output.seek(0)
        
        thumb_output = BytesIO()
        thumb.save(thumb_output, format='JPEG', quality=70, optimize=True)
        thumb_output.seek(0)
        
        print("✅ Текст добавлен")
        return full_output, thumb_output
        
    except Exception as e:
        print(f"❌ Ошибка текста: {e}")
        traceback.print_exc()
        return None, None

# ───────────────────────────────────────────────
# Коллаж + текст
# ───────────────────────────────────────────────

def create_collage_with_text(image_urls, count, text):
    try:
        print(f"🎨 Коллаж с текстом: '{text}' ({count} шт)")
        
        images = []
        for url in image_urls[:count]:
            try:
                r = requests.get(url, timeout=10)
                img = Image.open(BytesIO(r.content))
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                images.append(img)
            except Exception as e:
                print(f"Ошибка загрузки: {e}")
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
        
        draw = ImageDraw.Draw(collage)
        
        font_size = int(collage.height * 0.1)
        font = None
        
        font_paths = ['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf']
        
        for path in font_paths:
            try:
                font = ImageFont.truetype(path, font_size)
                break
            except:
                pass
        
        if font is None:
            font = ImageFont.load_default()
        
        max_width = collage.width - 80
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
        
        total_text_height = 0
        line_heights = []
        
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            lh = bbox[3] - bbox[1]
            line_heights.append(lh)
            total_text_height += lh + 10
        
        y_offset = collage.height - total_text_height - 40
        
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            tw = bbox[2] - bbox[0]
            x = (collage.width - tw) // 2
            y = y_offset
            
            outline_range = max(3, font_size // 20)
            for dx in range(-outline_range, outline_range + 1):
                for dy in range(-outline_range, outline_range + 1):
                    draw.text((x + dx, y + dy), line, font=font, fill='black')
            
            draw.text((x, y), line, font=font, fill='white')
            
            y_offset += line_heights[i] + 10
        
        thumb = collage.copy()
        thumb.thumbnail((200, 200), Image.Resampling.LANCZOS)
        
        full = BytesIO()
        collage.save(full, format='JPEG', quality=85, optimize=True)
        full.seek(0)
        
        thumb_io = BytesIO()
        thumb.save(thumb_io, format='JPEG', quality=70, optimize=True)
        thumb_io.seek(0)
        
        print("Коллаж + текст готов")
        return full, thumb_io
        
    except Exception as e:
        print(f"Ошибка коллажа+текста: {e}")
        traceback.print_exc()
        return None, None

# ───────────────────────────────────────────────
# Хендлеры
# ───────────────────────────────────────────────

@bot.message_handler(commands=['start', 'help'])
def start_command(message):
    available_commands = list(PHRASES.keys())
    commands_text = '\n'.join([f'• `@randompikcha2_bot {cmd}` — фраза из "{cmd}"' for cmd in available_commands])
    
    help_text = (
        '🎨 Привет! Я бот для картинок.\n\n'
        '📸 Режимы:\n'
        '• Просто имя бота — случайная картинка\n'
        '• `@randompikcha2_bot cats` — коты\n\n'
        '🎨 Коллажи:\n'
        '• `@randompikcha2_bot 5` — 5 картинок\n'
        '• `@randompikcha2_bot 5 cats` — 5 котов\n'
        '• `@randompikcha2_bot 5 papich cats` — 5 котов + фраза papich\n\n'
        '📝 Текст:\n'
        '• `@randompikcha2_bot text "Привет"` — текст на картинке\n'
        '• `@randompikcha2_bot 5 text "Привет" cats` — коллаж + текст\n\n'
        '🎭 Фразы:\n'
        f'{commands_text}\n\n'
        '🎲 Слова:\n'
        '• `@randompikcha2_bot randtext` — слова на картинке\n'
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

    query_text = inline_query.query.strip()
    results = []

    try:
        collage_count = None
        text_to_add = None
        search_query = None
        is_randtext = False
        randtext_count = 3
        phrase_category = None
        
        parts = query_text.split()
        
        if parts and parts[0] == 'randtext':
            is_randtext = True
            if len(parts) > 1 and parts[1].isdigit():
                randtext_count = min(int(parts[1]), 10)
                search_query = ' '.join(parts[2:]) if len(parts) > 2 else None
            else:
                search_query = ' '.join(parts[1:])
        
        elif parts and parts[0] == 'text':
            text_match = re.search(r'text\s+"([^"]+)"', query_text, re.IGNORECASE)
            if text_match:
                text_to_add = text_match.group(1)
                remaining = re.sub(r'text\s+"[^"]+"', '', query_text, flags=re.IGNORECASE).strip()
                remaining_parts = remaining.split()
                
                if remaining_parts and remaining_parts[0].isdigit():
                    collage_count = int(remaining_parts[0])
                    collage_count = max(2, min(10, collage_count))
                    search_query = ' '.join(remaining_parts[1:])
                else:
                    search_query = remaining if remaining else None
        
        elif parts and parts[0].isdigit():
            collage_count = int(parts[0])
            collage_count = max(2, min(10, collage_count))
            
            if len(parts) > 1:
                if parts[1] in PHRASES:
                    phrase_category = parts[1]
                    text_to_add = get_random_phrase(phrase_category)
                    search_query = ' '.join(parts[2:])
                else:
                    search_query = ' '.join(parts[1:])
        
        elif parts and parts[0] in PHRASES:
            phrase_category = parts[0]
            text_to_add = get_random_phrase(phrase_category)
            search_query = ' '.join(parts[1:])
        
        elif query_text:
            search_query = query_text
        
        # РЕЖИМЫ
        
        if is_randtext:
            text_to_add = get_random_russian_words(randtext_count)
            image_url, _ = get_random_image(search_query)
            
            if image_url:
                text_full, text_thumb = add_text_to_image(image_url, text_to_add)
                
                if text_full and text_thumb:
                    image_id = generate_unique_id("randtext")
                    thumb_id = f"thumb_{image_id}"
                    
                    temp_images[image_id] = (text_full.getvalue(), time.time())
                    temp_images[thumb_id] = (text_thumb.getvalue(), time.time())
                    
                    hostname = os.getenv("RAILWAY_PUBLIC_DOMAIN", "localhost")
                    text_image_url = f"https://{hostname}/image/{image_id}"
                    thumb_text_url = f"https://{hostname}/image/{thumb_id}"
                    
                    result = telebot.types.InlineQueryResultPhoto(
                        id=image_id,
                        photo_url=text_image_url,
                        thumbnail_url=thumb_text_url,
                        title=f"🎲 Слова ({randtext_count})",
                        description=text_to_add
                    )
                    results.append(result)
        
        elif collage_count and text_to_add:
            image_urls = []
            for _ in range(collage_count):
                url, _ = get_random_image(search_query)
                if url:
                    image_urls.append(url)
                time.sleep(0.1)
            
            if len(image_urls) >= 2:
                full, thumb = create_collage_with_text(image_urls, len(image_urls), text_to_add)
                
                if full and thumb:
                    image_id = generate_unique_id("collage_text")
                    thumb_id = f"thumb_{image_id}"
                    
                    temp_images[image_id] = (full.getvalue(), time.time())
                    temp_images[thumb_id] = (thumb.getvalue(), time.time())
                    
                    hostname = os.getenv("RAILWAY_PUBLIC_DOMAIN", "localhost")
                    url = f"https://{hostname}/image/{image_id}"
                    thumb_url = f"https://{hostname}/image/{thumb_id}"
                    
                    title = f"Коллаж {phrase_category}" if phrase_category else f"Коллаж: {text_to_add[:30]}..."
                    
                    result = telebot.types.InlineQueryResultPhoto(
                        id=image_id,
                        photo_url=url,
                        thumbnail_url=thumb_url,
                        title=title,
                        description=f"{text_to_add} | {search_query or 'случайно'}"
                    )
                    results.append(result)
        
        elif collage_count:
            image_urls = []
            for _ in range(collage_count):
                url, _ = get_random_image(search_query)
                if url:
                    image_urls.append(url)
                time.sleep(0.1)
            
            if len(image_urls) >= 2:
                full, thumb = create_collage(image_urls, len(image_urls))
                
                if full and thumb:
                    image_id = generate_unique_id("collage")
                    thumb_id = f"thumb_{image_id}"
                    
                    temp_images[image_id] = (full.getvalue(), time.time())
                    temp_images[thumb_id] = (thumb.getvalue(), time.time())
                    
                    hostname = os.getenv("RAILWAY_PUBLIC_DOMAIN", "localhost")
                    url = f"https://{hostname}/image/{image_id}"
                    thumb_url = f"https://{hostname}/image/{thumb_id}"
                    
                    result = telebot.types.InlineQueryResultPhoto(
                        id=image_id,
                        photo_url=url,
                        thumbnail_url=thumb_url,
                        title=f"Коллаж {len(image_urls)} шт",
                        description=search_query or "случайные"
                    )
                    results.append(result)
        
        elif text_to_add:
            image_url, _ = get_random_image(search_query)
            
            if image_url:
                full, thumb = add_text_to_image(image_url, text_to_add)
                
                if full and thumb:
                    image_id = generate_unique_id("text")
                    thumb_id = f"thumb_{image_id}"
                    
                    temp_images[image_id] = (full.getvalue(), time.time())
                    temp_images[thumb_id] = (thumb.getvalue(), time.time())
                    
                    hostname = os.getenv("RAILWAY_PUBLIC_DOMAIN", "localhost")
                    url = f"https://{hostname}/image/{image_id}"
                    thumb_url = f"https://{hostname}/image/{thumb_id}"
                    
                    title = text_to_add[:30] + "..." if len(text_to_add) > 30 else text_to_add
                    
                    result = telebot.types.InlineQueryResultPhoto(
                        id=image_id,
                        photo_url=url,
                        thumbnail_url=thumb_url,
                        title=title,
                        description=text_to_add
                    )
                    results.append(result)
        
        elif search_query:
            image_url, thumb_url = get_random_image(search_query)
            
            if image_url and thumb_url:
                result_id = generate_unique_id("img")
                
                result = telebot.types.InlineQueryResultPhoto(
                    id=result_id,
                    photo_url=image_url,
                    thumbnail_url=thumb_url,
                    photo_width=1080,
                    photo_height=720,
                    title=f"📸 {search_query}",
                    description="Нажми отправить"
                )
                results.append(result)
        
        else:
            image_url, thumb_url = get_random_image()
            
            if image_url and thumb_url:
                result_id = generate_unique_id("img")
                
                result = telebot.types.InlineQueryResultPhoto(
                    id=result_id,
                    photo_url=image_url,
                    thumbnail_url=thumb_url,
                    photo_width=1080,
                    photo_height=720,
                    title="📸 Случайная",
                    description="Нажми"
                )
                results.append(result)
        
    except Exception as e:
        print(f"Inline ошибка: {e}")
        traceback.print_exc()
    
    try:
        if results:
            bot.answer_inline_query(inline_query.id, results, cache_time=0, is_personal=True)
            print(f"✅ Отправлено {len(results)} результатов")
        else:
            bot.answer_inline_query(inline_query.id, [], cache_time=0)
            print("⚠️ Нет результатов")
    except Exception as e:
        print(f"Ошибка ответа inline: {e}")
        traceback.print_exc()

# ───────────────────────────────────────────────
# Flask роуты
# ───────────────────────────────────────────────

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
        f'Слов: {len(words_cache)}<br>'
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
            return response
        
        return send_file(
            BytesIO(image_data),
            mimetype='image/jpeg',
            as_attachment=False,
            download_name=f'{image_id}.jpg'
        )
    else:
        print(f"Изображение {image_id} не найдено")
        abort(404)

# ───────────────────────────────────────────────
# Запуск
# ───────────────────────────────────────────────

if __name__ == '__main__':
    setup_webhook()
    app.run(host='0.0.0.0', port=PORT, debug=False)
else:
    setup_webhook()