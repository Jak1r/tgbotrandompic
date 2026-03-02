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
import string
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

# Кэш для русских слов
words_cache = []

def fetch_russian_words():
    """Загружает русские слова из интернета"""
    global words_cache
    
    if words_cache:
        return words_cache
    
    try:
        print("🌐 Загружаем русские слова из интернета...")
        
        # Используем GitHub с русскими словами
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
            # Запасной список
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

# Инициализируем слова при запуске
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
    unique_str = str(uuid.uuid4()).replace('-', '')[:8]
    return f"{prefix}_{timestamp}_{random_part}_{unique_str}"

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
            print(f"🧹 Очищено {len(to_delete)} старых картинок из памяти")

# Запускаем очистку в фоне
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
                print(f"✅ Webhook успешно установлен на: {webhook_url}")
            else:
                print("❌ Не удалось установить webhook")
        else:
            print(f"✅ Webhook уже установлен правильно: {webhook_url}")
    except Exception as e:
        print(f"❌ Ошибка при установке webhook: {e}")

# Функции для работы с API
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
    
    headers = {
        'Authorization': PEXELS_API_KEY
    }
    
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
            print(f"⚠️ {api_name.upper()} rate limit, переключаемся на следующий API")
            current_api_index = (current_api_index + 1) % len(available_apis)
            continue
        
        current_api_index = (current_api_index + 1) % len(available_apis)
    
    print(f"❌ Все API не вернули результат для '{query}'")
    return None, None

# ФУНКЦИЯ: Создание коллажа
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
        collage.save(full_output, format='JPEG', quality=85, optimize=True)
        full_output.seek(0)
        
        thumb_output = BytesIO()
        thumb.save(thumb_output, format='JPEG', quality=70, optimize=True)
        thumb_output.seek(0)
        
        print(f"✅ Коллаж создан успешно ({collage_width}x{collage_height})")
        return full_output, thumb_output
        
    except Exception as e:
        print(f"❌ Ошибка создания коллажа: {e}")
        import traceback
        print(traceback.format_exc())
        return None, None

# ФУНКЦИЯ: Добавление текста на картинку
def add_text_to_image(image_url, text):
    """Добавляет текст внизу картинки как в мемах"""
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
            print(f"⚠️ Используем дефолтный шрифт")
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
        
        print(f"✅ Текст добавлен успешно")
        return full_output, thumb_output
        
    except Exception as e:
        print(f"❌ Ошибка добавления текста: {e}")
        import traceback
        print(traceback.format_exc())
        return None, None

# ФУНКЦИЯ: Создание коллажа с текстом (ОДИН ТЕКСТ НА ВЕСЬ КОЛЛАЖ)
def create_collage_with_text(image_urls, count, text):
    """Создает коллаж из картинок и добавляет текст сверху"""
    try:
        print(f"🎨 Создаем коллаж из {count} картинок с текстом: '{text}'")
        
        # Сначала создаем обычный коллаж
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
        
        # Определяем размеры коллажа
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
        
        # Размещаем картинки
        for idx, img in enumerate(images):
            img.thumbnail((cell_width, cell_height), Image.Resampling.LANCZOS)
            
            col = idx % cols
            row = idx // cols
            
            x = col * cell_width + (cell_width - img.width) // 2
            y = row * cell_height + (cell_height - img.height) // 2
            
            collage.paste(img, (x, y))
        
        # ТЕПЕРЬ ДОБАВЛЯЕМ ТЕКСТ НА КОЛЛАЖ
        draw = ImageDraw.Draw(collage)
        
        # Размер шрифта (относительно размера коллажа)
        font_size = int(collage.height * 0.1)  # 10% от высоты коллажа
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
            print(f"⚠️ Используем дефолтный шрифт")
            font = ImageFont.load_default()
        
        # Разбиваем текст на строки, чтобы поместился на коллаже
        max_width = collage.width - 80  # Отступы по краям
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
        
        # Рисуем текст в НИЖНЕЙ части коллажа
        total_text_height = 0
        line_heights = []
        
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_height = bbox[3] - bbox[1]
            line_heights.append(line_height)
            total_text_height += line_height + 10  # + отступ между строками
        
        # Позиция для текста (снизу, с отступом)
        y_offset = collage.height - total_text_height - 40
        
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            
            x = (collage.width - text_width) // 2
            y = y_offset
            
            # Рисуем обводку (черную)
            outline_range = max(3, font_size // 20)
            for adj_x in range(-outline_range, outline_range + 1):
                for adj_y in range(-outline_range, outline_range + 1):
                    draw.text((x + adj_x, y + adj_y), line, font=font, fill='black')
            
            # Рисуем основной текст (белый)
            draw.text((x, y), line, font=font, fill='white')
            
            y_offset += line_heights[i] + 10
        
        # Создаем превью
        thumb = collage.copy()
        thumb.thumbnail((200, 200), Image.Resampling.LANCZOS)
        
        # Сохраняем
        full_output = BytesIO()
        collage.save(full_output, format='JPEG', quality=85, optimize=True)
        full_output.seek(0)
        
        thumb_output = BytesIO()
        thumb.save(thumb_output, format='JPEG', quality=70, optimize=True)
        thumb_output.seek(0)
        
        print(f"✅ Коллаж с текстом создан успешно ({collage_width}x{collage_height})")
        return full_output, thumb_output
        
    except Exception as e:
        print(f"❌ Ошибка создания коллажа с текстом: {e}")
        import traceback
        print(traceback.format_exc())
        return None, None

@bot.message_handler(commands=['start', 'help'])
def start_command(message):
    available_commands = list(PHRASES.keys())
    commands_text = '\n'.join([f'• `@randompikcha2_bot  {cmd}` — случайная фраза из "{cmd}"' for cmd in available_commands])
    
    help_text = (
        '🎨 *Привет! Я бот для работы с картинками.*\n\n'
        '📸 *Основные режимы:*\n'
        '• Просто введи мое имя — одна случайная картинка\n'
        '• `@randompikcha2_bot  cats` — картинка с котами\n\n'
        '🎨 *Коллажи:*\n'
        '• `@randompikcha2_bot  5` — коллаж из 5 случайных картинок\n'
        '• `@randompikcha2_bot  5 cats` — коллаж из 5 картинок с котами\n'
        '• `@randompikcha2_bot  5 papich cats` — коллаж из 5 котов с фразой из "papich" сверху\n\n'
        '📝 *Текст на картинках:*\n'
        '• `@randompikcha2_bot  text "Hello"` — картинка с текстом "Hello"\n'
        '• `@randompikcha2_bot  text "Привет" cats` — картинка с котами и текстом\n'
        '• `@randompikcha2_bot  5 text "Привет" cats` — коллаж из 5 котов с текстом "Привет" сверху\n\n'
        '🎭 *Фразы по категориям:*\n'
        f'{commands_text}\n\n'
        '🎲 *Случайные слова:*\n'
        '• `@randompikcha2_bot  randtext` — картинка со случайным русским словом\n'
        '• `@randompikcha2_bot  randtext 3` — картинка с 3 случайными словами\n'
        '• `@randompikcha2_bot  randtext 5 cats` — 5 случайных слов на фоне котов\n\n'
        f'🔑 API: {", ".join(available_apis)}\n'
        f'💾 Фраз в базе: {sum(len(v) for v in PHRASES.values())}\n'
        f'📚 Русских слов: {len(words_cache)}'
    )
    bot.reply_to(message, help_text, parse_mode='Markdown')

@bot.message_handler(func=lambda message: True)
def handle_mention(message):
    bot_username = bot.get_me().username
    if f'@{bot_username}' in message.text:
        markup = InlineKeyboardMarkup()
        button = InlineKeyboardButton('📸 Отправить случайную картинку', callback_data='send_random_img')
        markup.add(button)
        bot.reply_to(message, 'Что хочешь сделать?', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data == 'send_random_img':
        bot.answer_callback_query(call.id, "Загружаю картинку...")
        image_url, _ = get_random_image()
        if image_url:
            try:
                bot.send_photo(call.message.chat.id, image_url)
            except Exception as e:
                bot.send_message(call.message.chat.id, '❌ Не удалось отправить изображение')
                print(f"❌ Ошибка отправки фото: {e}")
        else:
            bot.send_message(call.message.chat.id, '❌ Не удалось найти картинку. Попробуй позже!')

@bot.inline_handler(lambda query: True)
def inline_handler(inline_query):
    print(f"📥 Получен inline-запрос: '{inline_query.query}' от пользователя {inline_query.from_user.id}")
    print(f"📊 Картинок в памяти: {len(temp_images)}")

    query_text = inline_query.query.strip()
    results = []

    try:
        # Парсим запрос
        collage_count = None
        text_to_add = None
        search_query = None
        is_randtext = False
        randtext_count = 3
        phrase_category = None
        
        # Разбиваем запрос на части
        parts = query_text.split()
        
        # Проверяем на команду "randtext"
        if parts and parts[0] == 'randtext':
            is_randtext = True
            if len(parts) > 1 and parts[1].isdigit():
                randtext_count = min(int(parts[1]), 10)
                # Остаток после цифры - поисковый запрос
                if len(parts) > 2:
                    search_query = ' '.join(parts[2:])
            elif len(parts) > 1:
                # Если второй элемент не цифра, это поисковый запрос
                search_query = ' '.join(parts[1:])
            print(f"🎲 Randtext: {randtext_count} слов, поиск: {search_query}")
        
        # Проверяем на команду "text"
        elif parts and parts[0] == 'text':
            text_match = re.search(r'text\s+"([^"]+)"', query_text, re.IGNORECASE)
            if text_match:
                text_to_add = text_match.group(1)
                # Убираем часть с текстом из запроса
                remaining = re.sub(r'text\s+"[^"]+"', '', query_text, flags=re.IGNORECASE).strip()
                remaining_parts = remaining.split()
                
                # Проверяем, есть ли цифра в начале (для коллажа)
                if remaining_parts and remaining_parts[0].isdigit():
                    collage_count = int(remaining_parts[0])
                    if collage_count < 2:
                        collage_count = 2
                    elif collage_count > 10:
                        collage_count = 10
                    
                    # Остаток после цифры - поисковый запрос
                    if len(remaining_parts) > 1:
                        search_query = ' '.join(remaining_parts[1:])
                else:
                    # Обычный текст без коллажа
                    search_query = remaining if remaining else None
                
                print(f"📝 Текст: '{text_to_add}', коллаж: {collage_count}, поиск: {search_query}")
        
        # Проверяем на цифру в начале (коллаж)
        elif parts and parts[0].isdigit():
            collage_count = int(parts[0])
            if collage_count < 2:
                collage_count = 2
            elif collage_count > 10:
                collage_count = 10
            
            # Проверяем остаток запроса
            if len(parts) > 1:
                # Может быть категория фраз или поисковый запрос
                if parts[1] in PHRASES:
                    phrase_category = parts[1]
                    text_to_add = get_random_phrase(phrase_category)
                    # Остаток после категории - поисковый запрос
                    if len(parts) > 2:
                        search_query = ' '.join(parts[2:])
                    print(f"🎨 Коллаж {collage_count} с фразой из '{phrase_category}': '{text_to_add}', поиск: {search_query}")
                else:
                    # Обычный поиск
                    search_query = ' '.join(parts[1:])
                    print(f"🎨 Коллаж {collage_count}, поиск: {search_query}")
            else:
                print(f"🎨 Коллаж {collage_count} без поиска")
        
        # Проверяем на команды из JSON
        elif parts and parts[0] in PHRASES:
            phrase_category = parts[0]
            text_to_add = get_random_phrase(phrase_category)
            if len(parts) > 1:
                search_query = ' '.join(parts[1:])
            print(f"🎭 Категория '{phrase_category}': '{text_to_add}', поиск: {search_query}")
        
        # Если ничего не подошло - обычный поиск
        elif query_text:
            search_query = query_text
            print(f"🔍 Поиск: '{search_query}'")
        
        # РЕЖИМ 0: Случайный текст (randtext)
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
                    
                    hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "tgbotrandompic.onrender.com")
                    text_image_url = f"https://{hostname}/image/{image_id}"
                    thumb_text_url = f"https://{hostname}/image/{thumb_id}"
                    
                    result = telebot.types.InlineQueryResultPhoto(
                        id=image_id,
                        photo_url=text_image_url,
                        thumbnail_url=thumb_text_url,
                        title=f"🎲 Случайные слова ({randtext_count})",
                        description=f"{text_to_add}"
                    )
                    results.append(result)
        
        # РЕЖИМ 1: Коллаж с текстом (ОДИН ТЕКСТ НА ВЕСЬ КОЛЛАЖ)
        elif collage_count and text_to_add:
            # Собираем картинки
            image_urls = []
            for i in range(collage_count):
                img_url, _ = get_random_image(search_query)
                if img_url:
                    image_urls.append(img_url)
                time.sleep(0.1)
            
            if len(image_urls) >= 2:
                # Создаем коллаж и добавляем текст сверху
                collage_full, collage_thumb = create_collage_with_text(image_urls, len(image_urls), text_to_add)
                
                if collage_full and collage_thumb:
                    image_id = generate_unique_id("collage_text")
                    thumb_id = f"thumb_{image_id}"
                    
                    temp_images[image_id] = (collage_full.getvalue(), time.time())
                    temp_images[thumb_id] = (collage_thumb.getvalue(), time.time())
                    
                    hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "tgbotrandompic.onrender.com")
                    collage_url = f"https://{hostname}/image/{image_id}"
                    thumb_collage_url = f"https://{hostname}/image/{thumb_id}"
                    
                    # Определяем заголовок
                    if phrase_category:
                        title = f"🎨 Коллаж {phrase_category}"
                    else:
                        short_text = text_to_add[:30] + ('...' if len(text_to_add) > 30 else '')
                        title = f"🎨 Коллаж: {short_text}"
                    
                    result = telebot.types.InlineQueryResultPhoto(
                        id=image_id,
                        photo_url=collage_url,
                        thumbnail_url=thumb_collage_url,
                        title=title,
                        description=f"{text_to_add} | {search_query if search_query else 'Случайные картинки'}"
                    )
                    results.append(result)
        
        # РЕЖИМ 2: Обычный коллаж (без текста)
        elif collage_count:
            image_urls = []
            for i in range(collage_count):
                img_url, _ = get_random_image(search_query)
                if img_url:
                    image_urls.append(img_url)
                time.sleep(0.1)
            
            if len(image_urls) >= 2:
                collage_full, collage_thumb = create_collage(image_urls, len(image_urls))
                
                if collage_full and collage_thumb:
                    image_id = generate_unique_id("collage")
                    thumb_id = f"thumb_{image_id}"
                    
                    temp_images[image_id] = (collage_full.getvalue(), time.time())
                    temp_images[thumb_id] = (collage_thumb.getvalue(), time.time())
                    
                    hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "tgbotrandompic.onrender.com")
                    collage_url = f"https://{hostname}/image/{image_id}"
                    thumb_collage_url = f"https://{hostname}/image/{thumb_id}"
                    
                    result = telebot.types.InlineQueryResultPhoto(
                        id=image_id,
                        photo_url=collage_url,
                        thumbnail_url=thumb_collage_url,
                        title=f"🎨 Коллаж из {len(image_urls)} картинок",
                        description=f"{'Тема: ' + search_query if search_query else 'Случайные картинки'}"
                    )
                    results.append(result)
        
        # РЕЖИМ 3: Одиночная картинка с текстом
        elif text_to_add:
            image_url, _ = get_random_image(search_query)
            
            if image_url:
                text_full, text_thumb = add_text_to_image(image_url, text_to_add)
                
                if text_full and text_thumb:
                    image_id = generate_unique_id("text")
                    thumb_id = f"thumb_{image_id}"
                    
                    temp_images[image_id] = (text_full.getvalue(), time.time())
                    temp_images[thumb_id] = (text_thumb.getvalue(), time.time())
                    
                    hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "tgbotrandompic.onrender.com")
                    text_image_url = f"https://{hostname}/image/{image_id}"
                    thumb_text_url = f"https://{hostname}/image/{thumb_id}"
                    
                    # Определяем заголовок
                    if phrase_category:
                        emoji = "👑" if phrase_category == 'papich' else "🔧" if phrase_category == 'tehnik' else "💪" if phrase_category == 'stethem' else "🤬" if phrase_category == 'mat' else "🎲" if phrase_category == 'random' else "📝"
                        title = f"{emoji} {phrase_category.capitalize()}"
                    else:
                        short_text = text_to_add[:30] + ('...' if len(text_to_add) > 30 else '')
                        title = f"📝 {short_text}"
                    
                    result = telebot.types.InlineQueryResultPhoto(
                        id=image_id,
                        photo_url=text_image_url,
                        thumbnail_url=thumb_text_url,
                        title=title,
                        description=text_to_add
                    )
                    results.append(result)
        
        # РЕЖИМ 4: Обычная картинка (поиск)
        elif search_query:
            image_url, thumb_url = get_random_image(search_query)
            
            if image_url and thumb_url:
                result_id = generate_unique_id("img")
                title = f"📸 {search_query}"
                
                result = telebot.types.InlineQueryResultPhoto(
                    id=result_id,
                    photo_url=image_url,
                    thumbnail_url=thumb_url,
                    photo_width=1080,
                    photo_height=720,
                    title=title,
                    description="Нажми, чтобы отправить"
                )
                results.append(result)
        
        # РЕЖИМ 5: Пустой запрос - случайная картинка
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
                    title="📸 Случайная картинка",
                    description="Нажми, чтобы отправить"
                )
                results.append(result)
        
    except Exception as e:
        print(f"❌ Ошибка при создании результата: {e}")
        import traceback
        print(traceback.format_exc())

    try:
        if results:
            bot.answer_inline_query(inline_query.id, results, cache_time=0, is_personal=True)
            print(f"✅ Отправлено {len(results)} результатов в Telegram")
        else:
            print(f"⚠️ Нет результатов")
            bot.answer_inline_query(inline_query.id, [], cache_time=0)
    except Exception as e:
        print(f"❌ Ошибка при ответе Telegram: {e}")
        import traceback
        print(traceback.format_exc())

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
    return f'🤖 Bot is running! APIs: {", ".join(available_apis)} | Images in memory: {len(temp_images)} | Phrases: {sum(len(v) for v in PHRASES.values())} | Russian words: {len(words_cache)}', 200

@app.route('/health')
def health():
    return 'OK', 200

@app.route('/image/<image_id>', methods=['GET', 'HEAD'])
def serve_image(image_id):
    """Отдает сгенерированную картинку по ID"""
    print(f"🔍 {request.method} запрос картинки: {image_id}")
    
    if image_id in temp_images:
        image_data, timestamp = temp_images[image_id]
        
        if request.method == 'HEAD':
            response = app.make_response('')
            response.headers['Content-Type'] = 'image/jpeg'
            response.headers['Content-Length'] = str(len(image_data))
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Cache-Control'] = 'public, max-age=3600'
            return response
        
        response = send_file(
            BytesIO(image_data),
            mimetype='image/jpeg',
            as_attachment=False,
            download_name=f'{image_id}.jpg'
        )
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Cache-Control'] = 'public, max-age=3600'
        return response
    else:
        print(f"❌ Картинка {image_id} НЕ найдена в памяти")
        abort(404)

if __name__ == '__main__':
    # Для локального запуска
    app.run(host='0.0.0.0', port=PORT, debug=False)
else:
    # При импорте (на продакшене) устанавливаем вебхук
    setup_webhook()