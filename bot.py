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
import uuid
import json

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
        # Создаем дефолтный JSON если файл не найден
        default_phrases = {
            "papich": ["Хорош!", "Это база!", "Красавчик!"],
            "tehnik": ["Техника - молодёжь!", "Батя!", "Здарова, пацаны!"],
            "stethem": ["Где деньги, Лиза?", "Ты кто по жизни?", "Заберите у него тапки"],
            "mat": ["#@!$%", "***", "#$%@"]
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

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
app = Flask(__name__)

# Счетчик для ротации API
current_api_index = 0

# Временное хранилище для сгенерированных картинок (с автоочисткой)
temp_images = {}

def generate_unique_id(prefix="img"):
    """Генерирует уникальный ID для inline результата"""
    unique_str = str(uuid.uuid4()).replace('-', '')[:12]
    timestamp = int(time.time() * 1000)
    return f"{prefix}_{timestamp}_{unique_str}"

def get_random_phrase(category="random"):
    """Возвращает случайную фразу из указанной категории"""
    if category in PHRASES and PHRASES[category]:
        return random.choice(PHRASES[category])
    # Если категория не найдена, берем из random или первую доступную
    if "random" in PHRASES and PHRASES["random"]:
        return random.choice(PHRASES["random"])
    # Если ничего нет, возвращаем дефолтную фразу
    return "Случайная фраза"

def generate_random_words(count=3):
    """Генерирует случайные слова (для команды randtext)"""
    words = []
    for _ in range(count):
        # Берем случайные слова из разных категорий
        category = random.choice(list(PHRASES.keys()))
        if PHRASES[category]:
            words.append(random.choice(PHRASES[category]))
    return ' '.join(words[:count])

def cleanup_temp_images():
    """Очищает старые картинки из памяти каждые 10 минут"""
    while True:
        time.sleep(600)  # 10 минут
        current_time = time.time()
        to_delete = []
        
        for image_id, (data, timestamp) in temp_images.items():
            # Удаляем картинки старше 15 минут
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
        
        # Скачиваем все картинки
        images = []
        for url in image_urls[:count]:
            try:
                response = requests.get(url, timeout=10)
                img = Image.open(BytesIO(response.content))
                # Конвертируем в RGB если нужно
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
        
        # Размер каждой ячейки
        cell_width = 400
        cell_height = 400
        
        # Создаем холст
        collage_width = cols * cell_width
        collage_height = rows * cell_height
        collage = Image.new('RGB', (collage_width, collage_height), 'white')
        
        # Размещаем картинки
        for idx, img in enumerate(images):
            # Изменяем размер с сохранением пропорций
            img.thumbnail((cell_width, cell_height), Image.Resampling.LANCZOS)
            
            # Вычисляем позицию
            col = idx % cols
            row = idx // cols
            
            # Центрируем картинку в ячейке
            x = col * cell_width + (cell_width - img.width) // 2
            y = row * cell_height + (cell_height - img.height) // 2
            
            collage.paste(img, (x, y))
        
        # Создаем превью
        thumb = collage.copy()
        thumb.thumbnail((200, 200), Image.Resampling.LANCZOS)
        
        # Сохраняем полное изображение
        full_output = BytesIO()
        collage.save(full_output, format='JPEG', quality=85, optimize=True)
        full_output.seek(0)
        
        # Сохраняем превью
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
        
        # Скачиваем картинку
        response = requests.get(image_url, timeout=10)
        img = Image.open(BytesIO(response.content))
        
        # Конвертируем в RGB если нужно
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Ограничиваем размер
        max_size = 1200
        if img.width > max_size or img.height > max_size:
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
        draw = ImageDraw.Draw(img)
        
        # Размер шрифта
        font_size = int(img.height * 0.08)
        font = None
        
        # Попытка загрузить шрифт с поддержкой кириллицы
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
        
        # Разбиваем длинный текст на строки
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
        
        # Рисуем каждую строку
        y_offset = img.height - 60
        
        for line in reversed(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            x = (img.width - text_width) // 2
            y = y_offset - text_height
            
            # Рисуем обводку
            outline_range = 3
            for adj_x in range(-outline_range, outline_range + 1):
                for adj_y in range(-outline_range, outline_range + 1):
                    draw.text((x + adj_x, y + adj_y), line, font=font, fill='black')
            
            draw.text((x, y), line, font=font, fill='white')
            y_offset = y - 10
        
        # Создаем превью
        thumb = img.copy()
        thumb.thumbnail((200, 200), Image.Resampling.LANCZOS)
        
        # Сохраняем полное изображение
        full_output = BytesIO()
        img.save(full_output, format='JPEG', quality=90, optimize=True)
        full_output.seek(0)
        
        # Сохраняем превью
        thumb_output = BytesIO()
        thumb.save(thumb_output, format='JPEG', quality=70, optimize=True)
        thumb_output.seek(0)
        
        return full_output, thumb_output
        
    except Exception as e:
        print(f"❌ Ошибка добавления текста: {e}")
        import traceback
        print(traceback.format_exc())
        return None, None

@bot.message_handler(commands=['start', 'help'])
def start_command(message):
    # Получаем список доступных команд из JSON
    available_commands = list(PHRASES.keys())
    commands_text = '\n'.join([f'• `@bot {cmd}` — случайная фраза из "{cmd}"' for cmd in available_commands[:10]])
    
    help_text = (
        '🎨 *Привет! Я бот для работы с картинками.*\n\n'
        '📸 *Основные режимы:*\n'
        '• Просто введи мое имя — одна случайная картинка\n'
        '• `@bot cats` — картинка с котами\n'
        '• `@bot 5` — коллаж из 5 картинок (2-10)\n'
        '• `@bot 7 nature` — коллаж из 7 картинок природы\n\n'
        '📝 *Текст на картинках:*\n'
        '• `@bot text "Hello"` — картинка с текстом "Hello"\n'
        '• `@bot text "Привет мир"` — поддержка русского!\n'
        '• `@bot text "Котики" cats` — картинка с котами и текстом\n\n'
        '🎭 *Случайный текст:*\n'
        '• `@bot randtext` — картинка со случайным текстом (1-3 слова)\n'
        '• `@bot randtext 5` — картинка с 5 случайными словами\n\n'
        f'📚 *Фразы по категориям:*\n{commands_text}\n\n'
        f'🔑 API: {", ".join(available_apis)}\n'
        f'💾 Фраз в базе: {sum(len(v) for v in PHRASES.values())}'
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
        # Если запрос пустой - просто случайная картинка
        if not query_text:
            print("🖼️ Пустой запрос - случайная картинка")
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
            
            bot.answer_inline_query(inline_query.id, results, cache_time=0, is_personal=True)
            return

        # Парсим запрос
        collage_count = None
        text_to_add = None
        search_query = None
        is_randtext = False
        randtext_count = 3
        phrase_category = None
        
        query_lower = query_text.lower()
        parts = query_lower.split(maxsplit=1)
        first_word = parts[0] if parts else ""
        
        # Проверяем на команду randtext
        if first_word == 'randtext':
            is_randtext = True
            if len(parts) > 1 and parts[1].isdigit():
                randtext_count = min(int(parts[1]), 10)
            print(f"🎲 Случайный текст: {randtext_count} слов")
        
        # Проверяем на команду text
        elif first_word == 'text':
            text_match = re.search(r'text\s+"([^"]+)"', query_text, re.IGNORECASE)
            if text_match:
                text_to_add = text_match.group(1)
                # Ищем остаток запроса после текста
                remaining = re.sub(r'text\s+"[^"]+"', '', query_text, flags=re.IGNORECASE).strip()
                search_query = remaining if remaining else None
                print(f"📝 Найден текст для добавления: '{text_to_add}', поиск: {search_query}")
        
        # Проверяем на цифру (коллаж)
        elif first_word.isdigit():
            collage_count = int(first_word)
            if collage_count < 2:
                collage_count = 2
            elif collage_count > 10:
                collage_count = 10
            search_query = parts[1] if len(parts) > 1 else None
            print(f"🎨 Запрошен коллаж из {collage_count} картинок")
        
        # Проверяем на команды из JSON (ВКЛЮЧАЯ random!)
        elif first_word in PHRASES:
            phrase_category = first_word
            text_to_add = get_random_phrase(phrase_category)
            search_query = parts[1] if len(parts) > 1 else None
            print(f"🎭 Категория '{phrase_category}': '{text_to_add}'")
        
        # Обычный поиск (если ничего не подошло)
        else:
            search_query = query_text
            print(f"🔍 Поиск картинок по запросу: '{search_query}'")
        
        # РЕЖИМ 0: Случайный текст (randtext)
        if is_randtext:
            text_to_add = generate_random_words(randtext_count)
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
        
        # РЕЖИМ 1: Коллаж
        elif collage_count:
            image_urls = []
            
            for i in range(collage_count):
                img_url, _ = get_random_image(search_query)
                if img_url:
                    image_urls.append(img_url)
                time.sleep(0.1)  # Небольшая задержка между запросами
            
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
        
        # РЕЖИМ 2: Текст на картинке (включая все категории из JSON)
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
                    
                    # Определяем эмодзи и заголовок в зависимости от категории
                    if phrase_category == 'papich':
                        emoji = "👑"
                    elif phrase_category == 'tehnik':
                        emoji = "🔧"
                    elif phrase_category == 'stethem':
                        emoji = "💪"
                    elif phrase_category == 'mat':
                        emoji = "🤬"
                    elif phrase_category == 'random':
                        emoji = "🎲"
                    elif phrase_category == 'inspirational':
                        emoji = "✨"
                    elif phrase_category == 'funny':
                        emoji = "😂"
                    else:
                        emoji = "📝"
                    
                    title = f"{emoji} {phrase_category.capitalize()}" if phrase_category else f"📝 {text_to_add[:30]}"
                    
                    result = telebot.types.InlineQueryResultPhoto(
                        id=image_id,
                        photo_url=text_image_url,
                        thumbnail_url=thumb_text_url,
                        title=title,
                        description=text_to_add
                    )
                    results.append(result)
                    print(f"✅ Добавлена картинка с текстом из категории '{phrase_category}': '{text_to_add}'")
        
        # РЕЖИМ 3: Обычная картинка (поиск)
        else:
            image_url, thumb_url = get_random_image(search_query)
            
            if image_url and thumb_url:
                result_id = generate_unique_id("img")
                title = f"📸 {search_query}" if search_query else "📸 Случайная картинка"
                
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
                print(f"✅ Создан результат для поиска: {search_query}")
        
    except Exception as e:
        print(f"❌ Ошибка при создании результата: {e}")
        import traceback
        print(traceback.format_exc())

    try:
        if results:
            bot.answer_inline_query(inline_query.id, results, cache_time=0, is_personal=True)
            print(f"✅ Отправлено {len(results)} результатов в Telegram")
        else:
            # Если нет результатов, отправляем случайную картинку как запасной вариант
            print(f"⚠️ Нет результатов, отправляем случайную картинку")
            image_url, thumb_url = get_random_image()
            if image_url and thumb_url:
                result_id = generate_unique_id("img_fallback")
                result = telebot.types.InlineQueryResultPhoto(
                    id=result_id,
                    photo_url=image_url,
                    thumbnail_url=thumb_url,
                    photo_width=1080,
                    photo_height=720,
                    title="📸 Случайная картинка",
                    description="Нажми, чтобы отправить"
                )
                bot.answer_inline_query(inline_query.id, [result], cache_time=0, is_personal=True)
                print(f"✅ Отправлена случайная картинка как fallback")
            else:
                bot.answer_inline_query(inline_query.id, [], cache_time=0)
                print(f"⚠️ Отправлен пустой ответ в Telegram")
    except Exception as e:
        print(f"❌ Ошибка при ответе Telegram: {e}")
        import traceback
        print(traceback.format_exc())

# Flask роуты (остаются без изменений)
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
    return f'🤖 Bot is running! APIs: {", ".join(available_apis)} | Images in memory: {len(temp_images)} | Phrases: {sum(len(v) for v in PHRASES.values())}', 200

@app.route('/health')
def health():
    return 'OK', 200

@app.route('/image/<image_id>', methods=['GET', 'HEAD', 'OPTIONS'])
def serve_image(image_id):
    """Отдает сгенерированную картинку по ID"""
    print(f"🔍 {request.method} запрос картинки: {image_id}")
    
    if request.method == 'OPTIONS':
        response = app.make_response('')
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        response.headers['Access-Control-Max-Age'] = '3600'
        return response
    
    if image_id in temp_images:
        image_data, timestamp = temp_images[image_id]
        
        if request.method == 'HEAD':
            response = app.make_response('')
            response.headers