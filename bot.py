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
import hashlib

# ========== ЛОГИРОВАНИЕ ==========
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
    force=True
)

print(f"Python version: {sys.version}")
print(f"Working directory: {os.getcwd()}")
# ========== КОНЕЦ ЛОГИРОВАНИЯ ==========

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
        response = requests.get(
            'https://fucking-great-advice.ru/api/random',
            timeout=5,
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        
        if response.status_code == 200:
            data = response.json()
            phrase = data.get('text', '').strip()
            
            if phrase and len(phrase) > 5:
                return phrase
            
    except Exception as e:
        print(f"⚠️ Ошибка получения фразы из API: {e}")
    
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
        time.sleep(600)
        now = time.time()
        to_delete = [k for k, (_, ts) in temp_images.items() if now - ts > 900]
        for k in to_delete:
            del temp_images[k]
        if to_delete:
            print(f"🧹 Очищено {len(to_delete)} старых изображений")

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

# ========== ФУНКЦИЯ ДОБАВЛЕНИЯ ТЕКСТА ==========
def add_text_to_image(image_url, text):
    try:
        print(f"📝 Добавляем текст: '{text[:30]}...'")
        
        r = requests.get(image_url, timeout=10)
        img = Image.open(BytesIO(r.content)).convert('RGB')
        
        max_size = 1200
        if img.width > max_size or img.height > max_size:
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
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
                print(f"✅ Шрифт: {font_path}")
                break
            except:
                pass
        
        if base_font is None:
            base_font = ImageFont.load_default()
            print("⚠️ Дефолтный шрифт")
        
        # ===== ПРОПОРЦИОНАЛЬНЫЕ ОТСТУПЫ =====
        side_margin = min(max(int(img.width * 0.05), 20), 60)
        target_width = img.width - (side_margin * 2)
        safety_margin = 0.93
        
        # Получаем уникальные символы из текста
        unique_chars = ''.join(set(text.replace(' ', ''))) or "А"
        
        # Рассчитываем целевую ширину символа
        char_width_target = (target_width / len(text)) * safety_margin
        
        # Тестируем размеры шрифта
        test_sizes = [200, 180, 160, 140, 120, 110, 100, 95, 90, 85, 80, 75, 70, 68, 66, 64, 62, 60, 58, 56, 54, 52, 50, 48, 46, 44, 42, 40, 38, 36, 34, 32, 30, 28, 26, 24, 22, 20]
        
        optimal_font_size = 20
        
        for size in test_sizes:
            font = base_font.font_variant(size=size)
            
            # Измеряем среднюю ширину уникальных символов
            total_width = 0
            for char in unique_chars[:5]:
                bbox = draw.textbbox((0, 0), char, font=font)
                total_width += bbox[2] - bbox[0]
            
            avg_char_width = total_width / min(len(unique_chars), 5)
            
            if avg_char_width <= char_width_target:
                optimal_font_size = size
                break
        
        # Финальный шрифт и разбиение на строки
        font = base_font.font_variant(size=optimal_font_size)
        
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
        
        # Рисуем текст
        y_offset = img.height - 60
        outline_range = max(2, int(optimal_font_size * 0.03))
        
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
        
        print(f"✅ Готово! Шрифт: {optimal_font_size}px")
        return full_output
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return None
# ========== КОНЕЦ ФУНКЦИИ ==========

@bot.message_handler(commands=['start', 'help'])
def start_command(message):
    available_commands = list(PHRASES.keys())
    commands_text = '\n'.join([f'• `@randompikcha2_bot {cmd}` — фраза из "{cmd}"' for cmd in available_commands])
    
    help_text = (
        '🎨 Привет! Я бот для случайных картинок.\n\n'
        '📸 Как пользоваться:\n'
        '• Просто имя бота — случайная картинка\n'
        '• `@randompikcha2_bot cats` — картинка по теме\n\n'
        '📝 Текст на картинке:\n'
        '• `@randompikcha2_bot "Привет мир"` — картинка с текстом\n'
        '• `@randompikcha2_bot "Привет" cats` — текст + тема\n\n'
        '🎭 Фразы:\n'
        f'{commands_text}\n\n'
        '🎲 Случайные фразы:\n'
        '• `@randompikcha2_bot randtext` — картинка + осмысленная фраза\n'
        '• `@randompikcha2_bot randtext 3` — 3 фразы на одной картинке\n'
        '• `@randompikcha2_bot randtext природа` — фраза + картинка по теме\n'
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
    query_text = inline_query.query.strip()
    user_id = inline_query.from_user.id
    
    print(f"📨 Запрос: '{query_text}' от {user_id}")
    
    # ===== УМНАЯ ЗАДЕРЖКА =====
    if not query_text:
        pass  # без задержки
    elif len(query_text) < 3:
        time.sleep(0.2)
    else:
        hash_input = f"{user_id}_{query_text}".encode()
        hash_value = int(hashlib.md5(hash_input).hexdigest(), 16)
        delay = 0.3 + (hash_value % 5) / 10  # 0.3-0.8 сек
        time.sleep(delay)
    
    results = []

    try:
        text_to_add = None
        search_query = None
        is_randtext = False
        images_count = 1  # по умолчанию 1 картинка
        
        # Парсим запрос
        original_text = query_text
        parts = query_text.lower().split()
        
        # Ищем число в конце (количество картинок)
        if parts and parts[-1].isdigit():
            images_count = min(int(parts[-1]), 5)  # максимум 5 картинок
            # Убираем число из запроса для дальнейшей обработки
            query_text = ' '.join(parts[:-1])
            parts = query_text.lower().split()
            print(f"  → запрошено {images_count} картинок")
        
        # Если после удаления числа запрос стал пустым
        if not query_text:
            # Просто случайные картинки
            search_query = None
            print(f"  → {images_count} случайных картинок")
        else:
            # Проверяем на randtext
            if parts and parts[0] == 'randtext':
                is_randtext = True
                print(f"  → режим randtext")
                
                # Получаем поисковый запрос (все что после randtext, кроме числа)
                if len(parts) > 1:
                    # Проверяем, является ли следующий элемент числом (для обратной совместимости)
                    if parts[1].isdigit():
                        # Старый формат randtext 3 - игнорируем число, берем одну фразу
                        search_query = ' '.join(parts[2:]) if len(parts) > 2 else None
                    else:
                        search_query = ' '.join(parts[1:])
                else:
                    search_query = None
                
                # ВСЕГДА берем только ОДНУ фразу
                text_to_add = get_russian_phrase()
                print(f"  → фраза: {text_to_add[:30]}...")
            
            # Проверяем на категории фраз
            elif parts and parts[0] in PHRASES:
                phrase_category = parts[0]
                text_to_add = get_random_phrase(phrase_category)
                search_query = ' '.join(parts[1:]) if len(parts) > 1 else None
                print(f"  → категория: {phrase_category}")
            
            # Проверяем на текст в кавычках
            elif re.match(r'^".+"', query_text) or (parts and parts[0].startswith('"')):
                text_match = re.search(r'"([^"]+)"', original_text)
                if text_match:
                    text_to_add = text_match.group(1)
                    # Убираем кавычки из запроса для поиска
                    remaining = re.sub(r'"[^"]+"', '', original_text).strip()
                    # Убираем число, если оно есть
                    if remaining and remaining.split() and remaining.split()[-1].isdigit():
                        remaining = ' '.join(remaining.split()[:-1])
                    search_query = remaining if remaining else None
                    print(f"  → текст: {text_to_add[:30]}...")
            
            # Обычный поиск
            elif query_text:
                print(f"  → поиск: {query_text}")
                search_query = query_text

        # ===== ГЕНЕРАЦИЯ КАРТИНОК =====
        if text_to_add or is_randtext:
            print(f"🖼️ Генерируем {images_count} картинок с текстом: '{text_to_add[:30]}...'")
            
            # Быстро собираем URL
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
            
            # Генерируем картинки
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
            # Обычные картинки без текста
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

# Эндпоинт для получения изображений
@app.route('/image/<image_id>', methods=['GET', 'HEAD'])
def serve_image(image_id):
    if image_id in temp_images:
        image_data, _ = temp_images[image_id]
        
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
        f'Домен: https://{hostname}'
    ), 200

@app.route('/health')
def health():
    return 'OK', 200

if __name__ == '__main__':
    print("🚀 Запуск бота...")
    setup_webhook()
    app.run(host='0.0.0.0', port=PORT, debug=False)
else:
    setup_webhook()