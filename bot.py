import os
import telebot
import random
import requests
from flask import Flask, request, abort, send_file
from dotenv import load_dotenv
import time
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import threading
import uuid
import sys
import traceback
import json

print("=== START bot.py ===")
print(f"Python: {sys.version}")

try:
    load_dotenv()
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
    UNSPLASH_ACCESS_KEY = os.getenv('UNSPLASH_ACCESS_KEY')
    PEXELS_API_KEY = os.getenv('PEXELS_API_KEY')
    PIXABAY_API_KEY = os.getenv('PIXABAY_API_KEY')
    PORT = int(os.getenv('PORT', 10000))

    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_TOKEN не задан")

    available_apis = []
    if UNSPLASH_ACCESS_KEY: available_apis.append('unsplash')
    if PEXELS_API_KEY: available_apis.append('pexels')
    if PIXABAY_API_KEY: available_apis.append('pixabay')
    if not available_apis:
        raise ValueError("Нет API ключей для изображений")

    print(f"Доступные API: {', '.join(available_apis)}")

    # Фразы (оставляем, но упрощаем загрузку)
    def load_phrases():
        try:
            with open('phrases.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"phrases.json ошибка: {e}, создаём дефолт")
            default = {
                "papich": ["Хорош, хорош!", "Это база!", "Красавчик!", "Топчик!"],
                "tehnik": ["Техника - молодёжь!", "Погнали!", "Здарова, пацаны!"],
                "stethem": ["Где деньги, Лиза?", "Ты кто по жизни?"],
                "mat": ["#@!$%", "***!!!"],
                "random": ["Удача", "Красота", "Счастье", "Сила"]
            }
            with open('phrases.json', 'w', encoding='utf-8') as f:
                json.dump(default, f, ensure_ascii=False)
            return default

    PHRASES = load_phrases()

    bot = telebot.TeleBot(TELEGRAM_TOKEN)
    app = Flask(__name__)

    current_api_index = 0
    RANDOM_QUERIES = ['nature', 'city', 'abstract', 'animals', 'space', 'sunset', 'cat', 'dog']

    # Временное хранилище изображений (критично для inline)
    temp_images = {}  # id: (bytes_data, timestamp)
    MAX_TEMP_IMAGES = 40  # лимит, чтобы не сожрать всю память

    def cleanup_temp_images():
        while True:
            time.sleep(600)  # каждые 10 мин
            now = time.time()
            to_delete = []
            for img_id, (data, ts) in temp_images.items():
                if now - ts > 1800:  # 30 мин
                    to_delete.append(img_id)
            for img_id in to_delete:
                del temp_images[img_id]
            print(f"Очищено {len(to_delete)} старых изображений")

            # Жёсткий лимит
            if len(temp_images) > MAX_TEMP_IMAGES:
                sorted_ids = sorted(temp_images, key=lambda k: temp_images[k][1])
                excess = len(temp_images) - MAX_TEMP_IMAGES
                for i in range(excess):
                    del temp_images[sorted_ids[i]]
                print(f"Принудительная очистка: удалено {excess} по лимиту")

    threading.Thread(target=cleanup_temp_images, daemon=True).start()

    def generate_unique_id(prefix="img"):
        return f"{prefix}_{uuid.uuid4().hex[:10]}"

    def get_random_image(query=None):
        global current_api_index
        q = query or random.choice(RANDOM_QUERIES)
        for _ in range(len(available_apis) + 1):
            api = available_apis[current_api_index]
            try:
                if api == 'unsplash':
                    url = f"https://api.unsplash.com/photos/random?query={q}&client_id={UNSPLASH_ACCESS_KEY}"
                    r = requests.get(url, timeout=12)
                    if r.ok:
                        data = r.json()
                        return data['urls']['regular']
                elif api == 'pexels':
                    headers = {'Authorization': PEXELS_API_KEY}
                    url = f"https://api.pexels.com/v1/search?query={q}&per_page=1"
                    r = requests.get(url, headers=headers, timeout=12)
                    if r.ok:
                        photos = r.json()['photos']
                        if photos:
                            return photos[0]['src']['large']
                elif api == 'pixabay':
                    url = f"https://pixabay.com/api/?key={PIXABAY_API_KEY}&q={q}&image_type=photo&per_page=3"
                    r = requests.get(url, timeout=12)
                    if r.ok:
                        hits = r.json()['hits']
                        if hits:
                            return random.choice(hits)['largeImageURL']
            except Exception as e:
                print(f"API {api} ошибка: {e}")
            current_api_index = (current_api_index + 1) % len(available_apis)
        return None

    def add_text_to_image(image_url, text):
        try:
            r = requests.get(image_url, timeout=15)
            r.raise_for_status()
            img = Image.open(BytesIO(r.content)).convert('RGB')

            draw = ImageDraw.Draw(img)
            font_size = max(30, int(img.height * 0.06))
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
            except:
                font = ImageFont.load_default()
                font_size = 40  # fallback

            max_width = img.width - 60
            lines = []
            current_line = []
            for word in text.split():
                test_line = ' '.join(current_line + [word])
                bbox = draw.textbbox((0, 0), test_line, font=font)
                if bbox[2] - bbox[0] <= max_width:
                    current_line.append(word)
                else:
                    lines.append(' '.join(current_line))
                    current_line = [word]
            if current_line:
                lines.append(' '.join(current_line))

            line_height = font_size + 10
            text_height = len(lines) * line_height
            y = img.height - text_height - 30

            for line in lines:
                bbox = draw.textbbox((0, 0), line, font=font)
                text_width = bbox[2] - bbox[0]
                x = (img.width - text_width) // 2

                # Обводка чёрная
                for dx in [-3, -2, -1, 0, 1, 2, 3]:
                    for dy in [-3, -2, -1, 0, 1, 2, 3]:
                        if dx != 0 or dy != 0:
                            draw.text((x + dx, y + dy), line, font=font, fill='black')

                draw.text((x, y), line, font=font, fill='white')
                y += line_height

            output = BytesIO()
            img.save(output, format='JPEG', quality=88, optimize=True)
            output.seek(0)
            return output
        except Exception as e:
            print(f"add_text ошибка: {e}")
            return None

    @bot.inline_handler(lambda query: True)
    def inline_handler(inline_query):
        q = inline_query.query.strip().lower()
        results = []

        text_to_add = None
        search_q = q

        # Парсим "text \"текст\" [тема]"
        if q.startswith('text '):
            try:
                start = q.find('"')
                end = q.rfind('"')
                if start > -1 and end > start:
                    text_to_add = q[start+1:end].strip()
                    search_q = q[end+1:].strip() if end+1 < len(q) else None
            except:
                pass

        # Категория фразы → берём случайную фразу как текст
        elif q in PHRASES:
            text_to_add = random.choice(PHRASES[q])
            search_q = None  # или оставь q как тему поиска

        image_url = get_random_image(search_q)
        if not image_url:
            bot.answer_inline_query(inline_query.id, [])
            return

        result_id = generate_unique_id("img")
        title = search_q or "Случайная картинка"
        description = "Без текста"
        photo_url = image_url
        thumb_url = image_url  # можно улучшить, но пока так

        if text_to_add:
            processed = add_text_to_image(image_url, text_to_add)
            if processed:
                temp_images[result_id] = (processed.getvalue(), time.time())
                photo_url = f"https://randompikchabot.bothost.ru/image/{result_id}"
                thumb_url = photo_url  # или генерировать thumb отдельно
                title = text_to_add[:30] + "..." if len(text_to_add) > 30 else text_to_add
                description = f"С текстом: {text_to_add}"

        result = telebot.types.InlineQueryResultPhoto(
            id=result_id,
            photo_url=photo_url,
            thumbnail_url=thumb_url,
            title=title,
            description=description
        )
        results.append(result)

        try:
            bot.answer_inline_query(inline_query.id, results, cache_time=0, is_personal=True)
        except Exception as e:
            print(f"answer_inline ошибка: {e}")

    # Роут для отдачи изображений
    @app.route('/image/<image_id>')
    def serve_image(image_id):
        if image_id in temp_images:
            data, _ = temp_images[image_id]
            return send_file(BytesIO(data), mimetype='image/jpeg')
        abort(404)

    # Webhook
    @app.route('/webhook', methods=['POST'])
    def webhook():
        if request.headers.get('content-type') == 'application/json':
            json_string = request.get_data().decode('utf-8')
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return 'OK', 200
        abort(403)

    @app.route('/')
    def index():
        return f'🤖 Bot running | APIs: {", ".join(available_apis)} | Temp images: {len(temp_images)} | Phrases: {sum(len(v) for v in PHRASES.values())}'

    def setup_webhook():
        hostname = 'randompikchabot.bothost.ru'  # или os.getenv если нужно
        url = f'https://{hostname}/webhook'
        try:
            bot.remove_webhook()
            time.sleep(1)
            bot.set_webhook(url=url)
            print(f"Webhook установлен: {url}")
        except Exception as e:
            print(f"Webhook ошибка: {e}")

except Exception as e:
    print("!!! CRASH НА СТАРТЕ !!!")
    traceback.print_exc(file=sys.stdout)
    sys.exit(1)

if __name__ == '__main__':
    setup_webhook()
    app.run(host='0.0.0.0', port=PORT, debug=False)
else:
    setup_webhook()