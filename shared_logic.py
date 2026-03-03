import os
import random
import requests
import json
import time
from PIL import Image, ImageDraw, ImageFont, ImageSequence
from io import BytesIO
import re
import hashlib
from datetime import datetime, timedelta
import pytz

# ========== ЗАГРУЗКА ЭМОДЗИ ==========
def load_emojis():
    try:
        if os.path.exists('emojis.json'):
            with open('emojis.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
            all_emojis = []
            for category, emojis in data.items():
                all_emojis.extend(emojis)
            print(f"✅ Загружено {len(all_emojis)} эмодзи из emojis.json")  # 👈 Добавить эту строку
            return all_emojis
    except Exception as e:
        print(f"❌ Ошибка загрузки emojis.json: {e}")  # 👈 Добавить эту строку
        pass
    print("⚠️ Используются запасные эмодзи (10 шт)")  # 👈 Добавить эту строку
    return ["😀", "😂", "😎", "😍", "🥳", "🔥", "✨", "⭐", "🌈", "🍕"]

ALL_EMOJIS = load_emojis()
print(f"📊 Всего эмодзи доступно: {len(ALL_EMOJIS)}")  # 👈 Эта строка уже есть

# ========== ФРАЗЫ ==========
def load_phrases():
    try:
        with open('phrases.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

PHRASES = load_phrases()

# ========== API КЛЮЧИ ==========
UNSPLASH_ACCESS_KEY = os.getenv('UNSPLASH_ACCESS_KEY')
PEXELS_API_KEY = os.getenv('PEXELS_API_KEY')
PIXABAY_API_KEY = os.getenv('PIXABAY_API_KEY')
GIPHY_API_KEY = os.getenv('GIPHY_API_KEY')

available_apis = []
if UNSPLASH_ACCESS_KEY: available_apis.append('unsplash')
if PEXELS_API_KEY: available_apis.append('pexels')
if PIXABAY_API_KEY: available_apis.append('pixabay')

# ========== RANDOM QUERIES ==========
RANDOM_QUERIES = [
    'nature', 'city', 'abstract', 'people', 'animals', 'food',
    'travel', 'space', 'art', 'technology', 'mountain', 'ocean',
    'forest', 'sunset', 'flowers', 'architecture', 'beach', 'winter'
]

MEME_QUERIES = [
    'meme', 'memes', 'funny', 'dankmemes', 'memesdaily',
    'programmingmemes', 'wholesomememes', 'meirl', '2meirl4meirl'
]

# ========== ИСТОЧНИКИ МЕМОВ ==========
MEME_SOURCES = [
    {
        'name': 'reddit',
        'url': 'https://meme-api.com/gimme',
        'parser': lambda data: (data.get('url'), data.get('preview', [data.get('url')])[-1] if data.get('preview') else data.get('url'))
    },
    {
        'name': 'imgflip',
        'url': 'https://api.imgflip.com/get_memes',
        'parser': lambda data: (random.choice(data['data']['memes'])['url'], None) if data.get('data') and data['data'].get('memes') else (None, None)
    }
]

# ========== ЭМОДЗИ ДНЯ ==========
EMOJI_PHRASES = [
    "Твоё эмодзи дня - {emoji}",
    "Случайное эмодзи дня - {emoji}",
    "Сегодня тебе выпало: {emoji}",
    "Твоё эмодзи дня - {emoji}, жесть ты лох!",
    "Красавчик, твоё эмодзи дня - {emoji}",
    "Барабанная дробь... Твоё эмодзи дня - {emoji}!",
    "Вселенная выбрала для тебя: {emoji}",
    "Джекпот! Твоё эмодзи дня - {emoji}",
    "Хмм, думаю тебе подойдёт... {emoji}",
    "Сегодня ты в образе эмодзи {emoji}",
    "Тебе сегодня везёт! Твоё эмодзи - {emoji}",
    "Звезды говорят, твоё эмодзи дня - {emoji}",
    "Крутится барабан... И твоё эмодзи дня - {emoji}!",
    "Оба-на, сегодня ты - {emoji}!",
    "Хот-хот, твоё эмодзи дня - {emoji}!",
    "С таким эмодзи ты горы свернёшь: {emoji}",
    "Радужного тебе настроения! Твой эмодзи - {emoji}",
    "Тра-ля-ля, твоё эмодзи сегодня - {emoji}",
    "Ой, смотри какое эмодзи выпало: {emoji}",
    "Вкусняшка дня - эмодзи {emoji}",
    "Сегодня ты будешь как {emoji} - стильно и модно!",
    "Эмодзи дня: {emoji} (спорный выбор, но ок)",
    "Держи своё эмодзи: {emoji}, не потеряй!",
    "Твоя суперсила сегодня - {emoji}",
    "Эмодзи-то какое: {emoji}! Завидуют все!",
    "Сегодня ты - {emoji}, гордись!",
    "Эмодзи дня определяет твоё настроение: {emoji}",
    "Вжух! И твоё эмодзи дня - {emoji}",
    "Ты думал будет другое? А вот нет! {emoji}",
    "Эмодзи-гороскоп говорит: {emoji}",
    "Твой тотем на сегодня - {emoji}",
    "Эмодзи-оракул изрёк: {emoji}",
    "Итак, сегодня ты - {emoji}. Смирись.",
    "Поздравляю! Твоё эмодзи дня - {emoji}",
    "Эмодзи-лотерея: выигрыш - {emoji}!",
    "Твой персональный эмодзи-стикер: {emoji}",
    "Эмодзи-шаман сказал: {emoji} будет твоим",
    "Сюрприз! Твоё эмодзи дня - {emoji}",
    "Эмодзи-карма принесла тебе {emoji}",
    "Твой эмодзи-тотем на сегодня: {emoji}",
    "Эмодзи-пророк вещает: {emoji}",
    "Магия эмодзи превращает тебя в {emoji}",
    "Эмодзи-гороскоп на сегодня: {emoji} - твой знак",
    "Твоя эмодзи-аура сегодня: {emoji}",
    "Эмодзи-вибрации дня: {emoji}",
    "Космос посылает тебе эмодзи {emoji}",
    "Твой эмодзи-дух-хранитель: {emoji}",
    "Эмодзи-фарт на сегодня: {emoji}",
    "День пройдёт под знаком эмодзи {emoji}",
    "Эмодзи-предсказание: сегодня ты - {emoji}",
    "Волшебный экран показал: {emoji}",
    "Твой эмодзи-покровитель на сегодня: {emoji}",
    "Эмодзи-энергия дня: {emoji}",
    "Сегодня твой день - день эмодзи {emoji}!",
    "Эмодзи-фортуна улыбнулась тебе: {emoji}",
    "Твоя эмодзи-судьба: {emoji}",
    "Эмодзи-вселенная выбрала: {emoji}",
    "Сегодня ты будешь излучать эмодзи {emoji}",
    "Эмодзи-настроение дня: {emoji}",
    "Твой эмодзи-символ сегодня: {emoji}",
    "Эмодзи-тотемное животное: {emoji}",
    "Магический шар показывает: {emoji}",
    "Эмодзи-поток принёс тебе {emoji}",
    "Твой эмодзи-аватар на сегодня: {emoji}"
]

user_emojis = {}

def get_moscow_midnight_timestamp():
    tz = pytz.timezone('Europe/Moscow')
    now = datetime.now(tz)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.timestamp()

def get_user_emoji(user_id):
    current_time = time.time()
    today_midnight = get_moscow_midnight_timestamp()
    
    if user_id in user_emojis:
        emoji, expiry = user_emojis[user_id]
        if expiry >= today_midnight:
            return emoji
    
    new_emoji = random.choice(ALL_EMOJIS)
    next_midnight = today_midnight + 86400
    user_emojis[user_id] = (new_emoji, next_midnight)
    return new_emoji

# ========== API ФУНКЦИИ ==========
def get_unsplash_image(query):
    url = f'https://api.unsplash.com/photos/random?query={query}&client_id={UNSPLASH_ACCESS_KEY}'
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            urls = data.get('urls', {})
            return urls.get('regular'), urls.get('thumb')
        return None, None
    except:
        return None, None

def get_pexels_image(query):
    url = f'https://api.pexels.com/v1/search?query={query}&per_page=1&page={random.randint(1, 100)}'
    headers = {'Authorization': PEXELS_API_KEY}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            photos = data.get('photos', [])
            if photos:
                photo = photos[0]
                return photo['src']['large'], photo['src']['small']
        return None, None
    except:
        return None, None

def get_pixabay_image(query):
    url = f'https://pixabay.com/api/?key={PIXABAY_API_KEY}&q={query}&image_type=photo&per_page=3&page={random.randint(1, 50)}'
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            hits = data.get('hits', [])
            if hits:
                photo = random.choice(hits)
                return photo['largeImageURL'], photo['previewURL']
        return None, None
    except:
        return None, None

def get_random_image(custom_query=None):
    query = custom_query or random.choice(RANDOM_QUERIES)
    for api in available_apis:
        if api == 'unsplash':
            image_url, thumb_url = get_unsplash_image(query)
        elif api == 'pexels':
            image_url, thumb_url = get_pexels_image(query)
        elif api == 'pixabay':
            image_url, thumb_url = get_pixabay_image(query)
        if image_url and thumb_url:
            return image_url, thumb_url
    return None, None

def get_random_meme(query=None):
    sources = MEME_SOURCES.copy()
    random.shuffle(sources)
    
    for source in sources:
        try:
            if source['name'] == 'reddit' and query:
                url = f"https://meme-api.com/gimme/{query}"
            else:
                url = source['url']
            
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                meme_url, thumb_url = source['parser'](data)
                if meme_url:
                    if not thumb_url:
                        thumb_url = meme_url
                    return meme_url, thumb_url
        except:
            continue
    
    tag = query or random.choice(MEME_QUERIES)
    return get_random_image(tag)

def get_random_gif(query=None):
    """Получает случайную GIF-ку из GIPHY API с диагностикой"""
    if not GIPHY_API_KEY:
        print("❌ GIPHY API ключ не настроен")
        return None
    
    try:
        tag = query or random.choice(RANDOM_QUERIES)
        
        url = "https://api.giphy.com/v1/gifs/random"
        params = {
            'api_key': GIPHY_API_KEY,
            'tag': tag,
            'rating': 'pg-13',
            'fmt': 'json'
        }
        
        print(f"🔄 GIPHY: запрос с тегом '{tag}'")
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('meta') and data['meta'].get('status') == 200:
                if data.get('data') and data['data'].get('images'):
                    gif_url = data['data']['images']['original']['url']
                    print(f"✅ GIPHY: GIF получена")
                    return gif_url
            else:
                print(f"⚠️ GIPHY meta error: {data.get('meta')}")
        
        elif response.status_code == 429:
            print("❌ GIPHY: Лимит запросов исчерпан (429)")
        elif response.status_code == 403:
            print("❌ GIPHY: Ошибка авторизации (403)")
        else:
            print(f"⚠️ GIPHY: статус {response.status_code}")
        
        return None
        
    except requests.exceptions.Timeout:
        print("❌ GIPHY: Таймаут")
        return None
    except requests.exceptions.ConnectionError:
        print("❌ GIPHY: Ошибка соединения")
        return None
    except Exception as e:
        print(f"❌ GIPHY ошибка: {e}")
        return None

def get_russian_phrase():
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
    except:
        pass
    
    backup = [
        "Всё будет хорошо!", "Жизнь прекрасна!", "Улыбнись новому дню!",
        "Верь в лучшее!", "Ты справишься!", "Никогда не сдавайся!"
    ]
    return random.choice(backup)

def get_random_phrase(category="random"):
    if category in PHRASES and PHRASES[category]:
        return random.choice(PHRASES[category])
    return "Случайная фраза"

# ========== ФУНКЦИИ ДОБАВЛЕНИЯ ТЕКСТА ==========
def add_text_to_image(image_url, text):
    try:
        r = requests.get(image_url, timeout=10)
        img = Image.open(BytesIO(r.content)).convert('RGB')
        
        max_size = 1200
        if img.width > max_size or img.height > max_size:
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
        draw = ImageDraw.Draw(img)
        
        font_paths = [
            '/app/fonts/Impact.ttf',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        ]
        
        base_font = None
        for font_path in font_paths:
            try:
                base_font = ImageFont.truetype(font_path, 100)
                break
            except:
                pass
        
        if base_font is None:
            base_font = ImageFont.load_default()
        
        side_margin = min(max(int(img.width * 0.05), 20), 60)
        target_width = img.width - (side_margin * 2)
        safety_margin = 0.93
        
        unique_chars = ''.join(set(text.replace(' ', ''))) or "А"
        char_width_target = (target_width / len(text)) * safety_margin
        
        test_sizes = [200, 180, 160, 140, 120, 110, 100, 95, 90, 85, 80, 75, 70, 68, 66, 64, 62, 60, 58, 56, 54, 52, 50, 48, 46, 44, 42, 40, 38, 36, 34, 32, 30, 28, 26, 24, 22, 20]
        
        optimal_font_size = 20
        for size in test_sizes:
            font = base_font.font_variant(size=size)
            total_width = 0
            for char in unique_chars[:5]:
                bbox = draw.textbbox((0, 0), char, font=font)
                total_width += bbox[2] - bbox[0]
            avg_char_width = total_width / min(len(unique_chars), 5)
            if avg_char_width <= char_width_target:
                optimal_font_size = size
                break
        
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
        
        return full_output
    except:
        return None

def add_text_to_gif(gif_url, text):
    try:
        r = requests.get(gif_url, timeout=10)
        gif = Image.open(BytesIO(r.content))
        
        first_frame = gif.convert('RGB')
        frame_width, frame_height = first_frame.size
        
        font_paths = [
            '/app/fonts/Impact.ttf',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        ]
        
        base_font = None
        for font_path in font_paths:
            try:
                base_font = ImageFont.truetype(font_path, 100)
                break
            except:
                pass
        
        if base_font is None:
            base_font = ImageFont.load_default()
        
        side_margin = min(max(int(frame_width * 0.05), 20), 60)
        target_width = frame_width - (side_margin * 2)
        safety_margin = 0.93
        
        unique_chars = ''.join(set(text.replace(' ', ''))) or "А"
        char_width_target = (target_width / len(text)) * safety_margin
        
        test_sizes = [200, 180, 160, 140, 120, 110, 100, 95, 90, 85, 80, 75, 70, 68, 66, 64, 62, 60, 58, 56, 54, 52, 50, 48, 46, 44, 42, 40, 38, 36, 34, 32, 30, 28, 26, 24, 22, 20]
        
        optimal_font_size = 20
        temp_draw = ImageDraw.Draw(first_frame)
        
        for size in test_sizes:
            font = base_font.font_variant(size=size)
            total_width = 0
            for char in unique_chars[:5]:
                bbox = temp_draw.textbbox((0, 0), char, font=font)
                total_width += bbox[2] - bbox[0]
            avg_char_width = total_width / min(len(unique_chars), 5)
            if avg_char_width <= char_width_target:
                optimal_font_size = size
                break
        
        font = base_font.font_variant(size=optimal_font_size)
        
        words = text.split()
        lines = []
        current_line = []
        
        for word in words:
            test_line = ' '.join(current_line + [word])
            bbox = temp_draw.textbbox((0, 0), test_line, font=font)
            if bbox[2] - bbox[0] <= target_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
        
        if current_line:
            lines.append(' '.join(current_line))
        
        durations = []
        frames = []
        
        for frame in ImageSequence.Iterator(gif):
            try:
                durations.append(frame.info.get('duration', 50))
            except:
                durations.append(50)
            
            frame_rgb = frame.convert('RGB')
            frame_copy = frame_rgb.copy()
            draw = ImageDraw.Draw(frame_copy)
            
            y_offset = frame_copy.height - 60
            outline_range = max(2, int(optimal_font_size * 0.03))
            
            for line in reversed(lines):
                bbox = draw.textbbox((0, 0), line, font=font)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
                x = (frame_copy.width - tw) // 2
                y = y_offset - th
                
                for dx in range(-outline_range, outline_range + 1):
                    for dy in range(-outline_range, outline_range + 1):
                        if dx != 0 or dy != 0:
                            draw.text((x + dx, y + dy), line, font=font, fill='black')
                
                draw.text((x, y), line, font=font, fill='white')
                y_offset = y - int(optimal_font_size * 0.2)
            
            frames.append(frame_copy)
        
        output = BytesIO()
        frames[0].save(
            output,
            format='GIF',
            save_all=True,
            append_images=frames[1:],
            loop=0,
            duration=durations,
            optimize=False
        )
        output.seek(0)
        return output
    except:
        return None