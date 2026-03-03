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
import hashlib  # для генерации стабильного хеша

# ========== ДИАГНОСТИКА ==========
import logging

# Настраиваем логирование
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
    force=True
)

# Принудительный flush для print
# print = lambda *args, **kwargs: __builtins__.print(*args, **kwargs, flush=True)

# print("🔥🔥🔥 БОТ ЗАПУСКАЕТСЯ С ДИАГНОСТИКОЙ 🔥🔥🔥")
print(f"Python version: {sys.version}")
print(f"Working directory: {os.getcwd()}")
# ========== КОНЕЦ ДИАГНОСТИКИ ==========

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

# Функция для получения фраз из Fucking Great Advice
def get_russian_phrase():
    """Получает случайную русскую фразу из Fucking Great Advice API"""
    try:
        print("🔥 Запрашиваем фразу из Fucking Great Advice...")
        
        response = requests.get(
            'https://fucking-great-advice.ru/api/random',
            timeout=5,
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        
        if response.status_code == 200:
            data = response.json()
            phrase = data.get('text', '').strip()
            
            if phrase and len(phrase) > 5:
                print(f"✅ Получена фраза: {phrase[:50]}...")
                return phrase
            
    except Exception as e:
        print(f"⚠️ Ошибка получения фразы из API: {e}")
    
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
        "Мечты сбываются!"
    ]
    return random.choice(backup_phrases)

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
app = Flask(__name__)

current_api_index = 0
temp_images = {}  # Хранилище для временных изображений

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
    """Очистка старых изображений"""
    while True:
        time.sleep(600)  # Каждые 10 минут
        now = time.time()
        to_delete = [k for k, (_, ts) in temp_images.items() if now - ts > 900]  # 15 минут
        for k in to_delete:
            del temp_images[k]
        if to_delete:
            print(f"🧹 Очищено {len(to_delete)} старых изображений")

# Запускаем поток очистки
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

# ========== ИСПРАВЛЕННАЯ ВЕРСИЯ (РЕАЛЬНЫЕ СИМВОЛЫ) ==========
def add_text_to_image(image_url, text):
    try:
        print(f"🔥 add_text_to_image ВЫЗВАНА с текстом: '{text}'")
        
        # Скачиваем изображение
        r = requests.get(image_url, timeout=10)
        img = Image.open(BytesIO(r.content)).convert('RGB')
        print(f"📐 Исходный размер: {img.width} x {img.height}")
        
        # Уменьшаем если слишком большое
        max_size = 1200
        if img.width > max_size or img.height > max_size:
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            print(f"📐 После ресайза: {img.width} x {img.height}")
        
        draw = ImageDraw.Draw(img)
        
        # Загружаем шрифт
        font_paths = [
            '/app/fonts/Impact.ttf',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        ]
        
        base_font = None
        for font_path in font_paths:
            try:
                base_font = ImageFont.truetype(font_path, 100)
                print(f"✅ Шрифт загружен: {font_path}")
                break
            except Exception as e:
                print(f"⚠️ Шрифт {font_path} не загружен: {e}")
        
        if base_font is None:
            base_font = ImageFont.load_default()
            print("⚠️ Используем дефолтный шрифт")
        
        # ===== ПРОПОРЦИОНАЛЬНЫЕ ОТСТУПЫ =====
        side_margin = min(max(int(img.width * 0.05), 20), 60)
        target_width = img.width - (side_margin * 2)
        
        # ЗАПАС 7% (0.93)
        safety_margin = 0.93
        
        # Получаем уникальные символы из текста для измерения
        unique_chars = ''.join(set(text.replace(' ', '')))
        if not unique_chars:
            unique_chars = "А"
        
        print(f"📊 Параметры расчета:")
        print(f"  - Ширина картинки: {img.width}px")
        print(f"  - Отступы по бокам: {side_margin}px (5% от ширины)")
        print(f"  - Доступная ширина: {target_width}px")
        print(f"  - Запас: {int((1-safety_margin)*100)}%")
        print(f"  - Длина текста: {len(text)} символов")
        print(f"  - Уникальных символов для измерения: {len(unique_chars)}")
        
        # Рассчитываем целевую ширину символа
        char_width_target = (target_width / len(text)) * safety_margin
        print(f"  - Целевая ширина символа: {char_width_target:.1f}px")
        
        # Тестируем разные размеры шрифта
        test_sizes = [200, 180, 160, 140, 120, 110, 100, 95, 90, 85, 80, 75, 70, 68, 66, 64, 62, 60, 58, 56, 54, 52, 50, 48, 46, 44, 42, 40, 38, 36, 34, 32, 30, 28, 26, 24, 22, 20]
        
        optimal_font_size = 20
        
        print(f"🔍 Подбор размера шрифта (по уникальным символам '{unique_chars[:10]}...'):")
        for size in test_sizes:
            font = base_font.font_variant(size=size)
            
            # Измеряем среднюю ширину уникальных символов из текста
            total_width = 0
            for char in unique_chars[:5]:  # берем первые 5 уникальных символов для скорости
                bbox = draw.textbbox((0, 0), char, font=font)
                total_width += bbox[2] - bbox[0]
            
            avg_char_width = total_width / min(len(unique_chars), 5)
            
            print(f"  Размер {size:3d}px → ср. ширина символа: {avg_char_width:5.1f}px", end='')
            
            if avg_char_width <= char_width_target:
                print(f" ✅ ПОДХОДИТ")
                optimal_font_size = size
                break
            else:
                print(f" ❌")
        
        # Финальный шрифт
        font = base_font.font_variant(size=optimal_font_size)
        
        # Разбиваем на строки
        words = text.split()
        lines = []
        current_line = []
        
        for word in words:
            test_line = ' '.join(current_line + [word])
            bbox = draw.textbbox((0, 0), test_line, font=font)
            if bbox[2] - bbox[0] <= target_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
        
        if current_line:
            lines.append(' '.join(current_line))
        
        # Если слишком много строк, уменьшаем шрифт
        if len(lines) > 3:
            print(f"⚠️ {len(lines)} строк, ищем меньший размер...")
            current_index = test_sizes.index(optimal_font_size) if optimal_font_size in test_sizes else -1
            
            for next_index in range(current_index + 1, len(test_sizes)):
                next_size = test_sizes[next_index]
                test_font = base_font.font_variant(size=next_size)
                
                test_lines = []
                test_current = []
                
                for word in words:
                    test_line = ' '.join(test_current + [word])
                    bbox = draw.textbbox((0, 0), test_line, font=test_font)
                    if bbox[2] - bbox[0] <= target_width:
                        test_current.append(word)
                    else:
                        if test_current:
                            test_lines.append(' '.join(test_current))
                        test_current = [word]
                
                if test_current:
                    test_lines.append(' '.join(test_current))
                
                if len(test_lines) <= 3:
                    optimal_font_size = next_size
                    font = test_font
                    lines = test_lines
                    print(f"✅ Выбран размер {next_size}px ({len(lines)} строк)")
                    break
        
        print(f"📝 Финальное разбиение: {len(lines)} строк")
        for i, line in enumerate(lines, 1):
            print(f"  Строка {i}: '{line}'")
        
        # Рассчитываем реальное заполнение ширины
        if lines:
            bbox = draw.textbbox((0, 0), lines[0], font=font)
            actual_width = bbox[2] - bbox[0]
            fill_percentage = (actual_width / target_width) * 100
            print(f"📊 Заполнение ширины: {fill_percentage:.1f}%")
        
        # Рисуем текст
        y_offset = img.height - 60
        outline_range = max(2, int(optimal_font_size * 0.03))
        print(f"✏️ Толщина обводки: {outline_range}px")
        
        for line in reversed(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            x = (img.width - tw) // 2
            y = y_offset - th
            
            for dx in range(-outline_range, outline_range + 1):
                for dy in range(-outline_range, outline_range + 1):
                    if dx != 0 or dy != 0:
                        draw.text((x + dx, y + dy), line, font=font, fill='black')
            
            draw.text((x, y), line, font=font, fill='white')
            y_offset = y - int(optimal_font_size * 0.2)
        
        full_output = BytesIO()
        img.save(full_output, format='JPEG', quality=90, optimize=True)
        full_output.seek(0)
        
        print(f"✅ Готово! Размер шрифта: {optimal_font_size}px")
        print(f"  - Цель по ширине: {char_width_target:.1f}px на символ")
        return full_output
        
    except Exception as e:
        print(f"❌ ОШИБКА: {e}")
        traceback.print_exc()
        return None
# ========== КОНЕЦ ИСПРАВЛЕННОЙ ВЕРСИИ ==========

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
        '• `@твойбот randtext` — картинка + осмысленная фраза\n'
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
    query_text = inline_query.query.strip().lower()
    user_id = inline_query.from_user.id
    
    print(f"📨 Запрос: '{query_text}' от {user_id}")
    
    # ===== УМНАЯ ЗАДЕРЖКА =====
    # Если запрос пустой или очень короткий - минимальная задержка
    if len(query_text) < 2:
        time.sleep(0.3)
    else:
        # Генерируем "стабильную" задержку на основе текста и user_id
        # Чтобы один и тот же запрос от одного пользователя имел одинаковую задержку
        hash_input = f"{user_id}_{query_text}".encode()
        hash_value = int(hashlib.md5(hash_input).hexdigest(), 16)
        
        # Задержка от 0.5 до 1.2 секунд в зависимости от хеша
        delay = 0.5 + (hash_value % 7) / 10  # 0.5 + 0.0-0.7 = 0.5-1.2 сек
        time.sleep(delay)
    
    # Остальной код функции...
    results = []

    try:
        text_to_add = None
        search_query = query_text
        is_randtext = False
        phrase_count = 1

        parts = query_text.split()

        # Обработка randtext
        if parts and parts[0] == 'randtext':
            print(f"🔥 Обработка randtext")
            is_randtext = True
            
            if len(parts) > 1:
                if parts[1].isdigit():
                    phrase_count = min(int(parts[1]), 3)
                    search_query = ' '.join(parts[2:]) if len(parts) > 2 else None
                    print(f"🔥 Количество фраз: {phrase_count}")
                else:
                    search_query = ' '.join(parts[1:])
                    print(f"🔥 Поисковый запрос: {search_query}")
            
            if phrase_count > 1:
                phrases = []
                for i in range(phrase_count):
                    print(f"🔥 Получаем фразу {i+1} из {phrase_count}...")
                    phrase = get_russian_phrase()
                    phrases.append(phrase)
                    if i < phrase_count - 1:
                        time.sleep(0.5)
                text_to_add = ' | '.join(phrases)
            else:
                text_to_add = get_russian_phrase()
            
            print(f"🔥 Текст для добавления: {text_to_add[:50]}...")
        
        # Обработка text
        elif parts and parts[0] == 'text':
            print(f"🔥 Обработка text")
            text_match = re.search(r'text\s+"([^"]+)"', query_text, re.IGNORECASE)
            if text_match:
                text_to_add = text_match.group(1)
                remaining = re.sub(r'text\s+"[^"]+"', '', query_text, flags=re.IGNORECASE).strip()
                search_query = remaining if remaining else None
                print(f"🔥 Текст: {text_to_add}")
                print(f"🔥 Поиск: {search_query}")

        # Обработка категорий фраз
        elif parts and parts[0] in PHRASES:
            print(f"🔥 Обработка категории: {parts[0]}")
            phrase_category = parts[0]
            text_to_add = get_random_phrase(phrase_category)
            search_query = ' '.join(parts[1:]) if len(parts) > 1 else None
            print(f"🔥 Текст: {text_to_add}")
            print(f"🔥 Поиск: {search_query}")

        elif query_text:
            print(f"🔥 Простой поиск: {query_text}")
            search_query = query_text

        # Отправка фото с текстом через URL
        if text_to_add or is_randtext:
            print(f"🔥 Получаем случайное изображение с запросом: {search_query}")
            image_url, _ = get_random_image(search_query)
            
            if image_url:
                print(f"🔥 Изображение получено: {image_url}")
                print(f"🔥 ВЫЗЫВАЕМ add_text_to_image")
                
                full = add_text_to_image(image_url, text_to_add)
                
                print(f"🔥 РЕЗУЛЬТАТ add_text_to_image: {'успех' if full else 'НЕУДАЧА'}")
                
                if full:
                    # Сохраняем изображение во временное хранилище
                    image_id = generate_unique_id("randtext" if is_randtext else "text")
                    temp_images[image_id] = (full.getvalue(), time.time())
                    
                    # Формируем URL для доступа к изображению
                    hostname = os.getenv("RAILWAY_PUBLIC_DOMAIN", "localhost")
                    url = f"https://{hostname}/image/{image_id}"
                    
                    print(f"🔗 URL изображения: {url}")
                    print(f"📸 Всего изображений в кэше: {len(temp_images)}")
                    
                    result = telebot.types.InlineQueryResultPhoto(
                        id=image_id,
                        photo_url=url,
                        thumbnail_url=url,
                        photo_width=1080,
                        photo_height=720,
                        title=text_to_add[:30] + "..." if len(text_to_add) > 30 else text_to_add,
                        description=text_to_add
                    )
                    results.append(result)
                    print(f"🔥 Результат добавлен в список")
            else:
                print(f"🔥 Не удалось получить изображение")

        else:
            # Обычная картинка без текста
            print(f"🔥 Обычная картинка без текста")
            image_url, thumb_url = get_random_image(search_query)
            
            if image_url and thumb_url:
                result_id = generate_unique_id("img")
                
                result = telebot.types.InlineQueryResultPhoto(
                    id=result_id,
                    photo_url=image_url,
                    thumbnail_url=thumb_url,
                    photo_width=1080,
                    photo_height=720,
                    title=search_query or "Случайная картинка",
                    description="Нажми отправить"
                )
                results.append(result)
                print(f"🔥 Результат добавлен в список")

    except Exception as e:
        print(f"🔥🔥🔥 ОШИБКА В INLINE HANDLER: {e}")
        traceback.print_exc(file=sys.stdout)

    try:
        if results:
            bot.answer_inline_query(inline_query.id, results, cache_time=0, is_personal=True)
            print(f"✅ Отправлено {len(results)} результатов")
        else:
            bot.answer_inline_query(inline_query.id, [], cache_time=0)
            print("❌ Нет результатов")
    except Exception as e:
        print(f"❌ Ошибка ответа inline: {e}")
        traceback.print_exc(file=sys.stdout)

# Эндпоинт для получения изображений
@app.route('/image/<image_id>', methods=['GET', 'HEAD'])
def serve_image(image_id):
    print(f"🔍 Запрос изображения {image_id}")
    
    if image_id in temp_images:
        image_data, timestamp = temp_images[image_id]
        
        if request.method == 'HEAD':
            response = app.make_response('')
            response.headers['Content-Type'] = 'image/jpeg'
            response.headers['Content-Length'] = str(len(image_data))
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Cache-Control'] = 'public, max-age=3600'
            return response
        
        # Добавляем заголовки для правильной загрузки
        response = send_file(
            BytesIO(image_data),
            mimetype='image/jpeg',
            as_attachment=False,
            download_name=f'{image_id}.jpg'
        )
        
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Cache-Control'] = 'public, max-age=3600'
        
        print(f"✅ Изображение {image_id} отправлено, размер: {len(image_data)} байт")
        return response
        
    print(f"❌ Изображение {image_id} не найдено")
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

if __name__ == '__main__':
    print("🚀 ЗАПУСК FLASK СЕРВЕРА С ДИАГНОСТИКОЙ")
    setup_webhook()
    app.run(host='0.0.0.0', port=PORT, debug=True)
else:
    setup_webhook()
    print("🔥 Бот загружен как модуль")