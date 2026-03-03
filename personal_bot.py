import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from flask import Flask, request
from dotenv import load_dotenv
import time
import threading
import sys
import traceback
from io import BytesIO

# Импортируем общую логику
from shared_logic import *

load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
PORT = int(os.getenv('PORT', 8080))

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не задан в переменных окружения")

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
app = Flask(__name__)

# Хранилище временных файлов
temp_files = {}

def generate_unique_id():
    return f"personal_{int(time.time() * 1000)}_{random.randint(10000, 99999)}"

def cleanup_temp_files():
    while True:
        time.sleep(600)
        now = time.time()
        to_delete = [k for k, (_, ts) in temp_files.items() if now - ts > 900]
        for k in to_delete:
            del temp_files[k]
        if to_delete:
            print(f"🧹 Очищено {len(to_delete)} временных файлов")

threading.Thread(target=cleanup_temp_files, daemon=True).start()

def create_main_keyboard():
    """Создает основную клавиатуру с командами"""
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    # Основные команды
    btn1 = KeyboardButton("🖼️ Случайное фото")
    btn2 = KeyboardButton("🎭 Случайный мем")
    btn3 = KeyboardButton("🎬 Случайная GIF")
    btn4 = KeyboardButton("🎲 Эмодзи дня")
    btn5 = KeyboardButton("📝 Текст на фото")
    btn6 = KeyboardButton("📖 Помощь")
    
    markup.add(btn1, btn2, btn3, btn4, btn5, btn6)
    return markup

def create_text_keyboard():
    """Создает клавиатуру для выбора типа текста"""
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    btn1 = KeyboardButton("✏️ Свой текст")
    btn2 = KeyboardButton("🎲 Случайная фраза")
    btn3 = KeyboardButton("🎭 Категория papich")
    btn4 = KeyboardButton("🎭 Категория tehnik")
    btn5 = KeyboardButton("◀️ Назад")
    
    markup.add(btn1, btn2, btn3, btn4, btn5)
    return markup

def send_photo_with_text(chat_id, text, photo_type='photo', query=None, count=1):
    """Отправляет фото/мем/GIF с текстом"""
    try:
        if photo_type == 'gif':
            urls = []
            for _ in range(count):
                url = get_random_gif(query)
                if url and url not in urls:
                    urls.append(url)
            
            for i, url in enumerate(urls):
                if text:
                    full = add_text_to_gif(url, text)
                else:
                    r = requests.get(url, timeout=10)
                    full = BytesIO(r.content)
                
                if full:
                    file_id = generate_unique_id()
                    temp_files[file_id] = (full.getvalue(), time.time())
                    bot.send_document(chat_id, ('animation.gif', full), caption=f"GIF {i+1}" if count > 1 else None)
        
        elif photo_type == 'meme':
            urls = []
            for _ in range(count):
                url, _ = get_random_meme(query)
                if url and url not in urls:
                    urls.append(url)
            
            for i, url in enumerate(urls):
                if text:
                    full = add_text_to_image(url, text)
                else:
                    r = requests.get(url, timeout=10)
                    full = BytesIO(r.content)
                
                if full:
                    bot.send_photo(chat_id, full, caption=f"Мем {i+1}" if count > 1 else None)
        
        else:  # обычное фото
            urls = []
            for _ in range(count):
                url, _ = get_random_image(query)
                if url and url not in urls:
                    urls.append(url)
            
            for i, url in enumerate(urls):
                if text:
                    full = add_text_to_image(url, text)
                else:
                    r = requests.get(url, timeout=10)
                    full = BytesIO(r.content)
                
                if full:
                    bot.send_photo(chat_id, full, caption=f"Фото {i+1}" if count > 1 else None)
                    
    except Exception as e:
        bot.send_message(chat_id, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """Обработка команд start и help"""
    help_text = (
        '🎨 Привет! Я бот для случайных картинок.\n\n'
        '📸 Доступные команды:\n'
        '• /start, /help - это сообщение\n'
        '• /photo - случайное фото\n'
        '• /meme - случайный мем\n'
        '• /gif - случайная GIF\n'
        '• /emoji - эмодзи дня\n'
        '• /text - фото с текстом\n'
        '• /randtext - фото со случайной фразой\n\n'
        '🎭 Категории фраз:\n'
        '• /papich - фраза из категории papich\n'
        '• /tehnik - фраза из категории tehnik\n\n'
        '🎲 Также можно указать количество:\n'
        '• /photo 3 - 3 случайных фото\n'
        '• /meme 2 - 2 мема\n\n'
        '📝 Текст в кавычках:\n'
        '• /text "привет" - фото с текстом\n'
        '• /text "привет" кот 2 - 2 фото котов с текстом'
    )
    
    bot.reply_to(message, help_text, reply_markup=create_main_keyboard())

@bot.message_handler(func=lambda message: message.text == "🖼️ Случайное фото")
def handle_random_photo_button(message):
    bot.send_message(message.chat.id, "🔍 Ищу случайное фото...")
    send_photo_with_text(message.chat.id, None, 'photo')

@bot.message_handler(func=lambda message: message.text == "🎭 Случайный мем")
def handle_random_meme_button(message):
    bot.send_message(message.chat.id, "🔍 Ищу случайный мем...")
    send_photo_with_text(message.chat.id, None, 'meme')

@bot.message_handler(func=lambda message: message.text == "🎬 Случайная GIF")
def handle_random_gif_button(message):
    if not GIPHY_API_KEY:
        bot.send_message(message.chat.id, "❌ GIF временно недоступны")
        return
    bot.send_message(message.chat.id, "🔍 Ищу случайную GIF...")
    send_photo_with_text(message.chat.id, None, 'gif')

@bot.message_handler(func=lambda message: message.text == "🎲 Эмодзи дня")
def handle_emoji_button(message):
    emoji = get_user_emoji(message.from_user.id)
    phrase = random.choice(EMOJI_PHRASES).format(emoji=emoji)
    bot.send_message(message.chat.id, phrase)

@bot.message_handler(func=lambda message: message.text == "📝 Текст на фото")
def handle_text_button(message):
    markup = create_text_keyboard()
    bot.send_message(message.chat.id, "Выберите тип текста:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "📖 Помощь")
def handle_help_button(message):
    send_welcome(message)

@bot.message_handler(func=lambda message: message.text == "✏️ Свой текст")
def handle_custom_text(message):
    msg = bot.send_message(message.chat.id, "Введите текст в кавычках, например:\n\"Привет мир\"\n\nМожно добавить тему и количество:\n\"Привет\" кот 3")
    bot.register_next_step_handler(msg, process_custom_text)

def process_custom_text(message):
    try:
        text = message.text.strip()
        parts = text.lower().split()
        count = 1
        query = None
        
        # Проверяем наличие числа в конце
        if parts and parts[-1].isdigit():
            count = min(int(parts[-1]), 5)
            text_without_count = ' '.join(parts[:-1])
        else:
            text_without_count = text
        
        # Ищем текст в кавычках
        text_match = re.search(r'"([^"]+)"', text_without_count)
        if not text_match:
            bot.send_message(message.chat.id, "❌ Нужно использовать кавычки! Пример: \"Привет\"")
            return
        
        text_to_add = text_match.group(1)
        remaining = re.sub(r'"[^"]+"', '', text_without_count).strip()
        if remaining:
            query = remaining
        
        bot.send_message(message.chat.id, f"🖼️ Генерирую {count} фото с текстом...")
        send_photo_with_text(message.chat.id, text_to_add, 'photo', query, count)
        
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")

@bot.message_handler(func=lambda message: message.text == "🎲 Случайная фраза")
def handle_randtext_button(message):
    bot.send_message(message.chat.id, "🔍 Генерирую случайную фразу...")
    phrase = get_russian_phrase()
    
    msg = bot.send_message(message.chat.id, f"Фраза: {phrase}\n\nСколько фото сделать? (1-5)")
    bot.register_next_step_handler(msg, lambda m: process_randtext_count(m, phrase))

def process_randtext_count(message, phrase):
    try:
        count = 1
        if message.text.isdigit():
            count = min(int(message.text), 5)
        bot.send_message(message.chat.id, f"🖼️ Генерирую {count} фото с фразой...")
        send_photo_with_text(message.chat.id, phrase, 'photo', None, count)
    except:
        bot.send_message(message.chat.id, "❌ Ошибка")

@bot.message_handler(func=lambda message: message.text in ["🎭 Категория papich", "🎭 Категория tehnik"])
def handle_category_button(message):
    category = message.text.split()[2]  # papich или tehnik
    phrase = get_random_phrase(category)
    
    msg = bot.send_message(message.chat.id, f"Фраза: {phrase}\n\nСколько фото сделать? (1-5)")
    bot.register_next_step_handler(msg, lambda m: process_category_count(m, phrase))

def process_category_count(message, phrase):
    try:
        count = 1
        if message.text.isdigit():
            count = min(int(message.text), 5)
        bot.send_message(message.chat.id, f"🖼️ Генерирую {count} фото...")
        send_photo_with_text(message.chat.id, phrase, 'photo', None, count)
    except:
        bot.send_message(message.chat.id, "❌ Ошибка")

@bot.message_handler(func=lambda message: message.text == "◀️ Назад")
def handle_back_button(message):
    bot.send_message(message.chat.id, "Главное меню:", reply_markup=create_main_keyboard())

@bot.message_handler(commands=['photo', 'meme', 'gif', 'emoji', 'text', 'randtext', 'papich', 'tehnik'])
def handle_commands(message):
    """Обработка команд с аргументами"""
    try:
        parts = message.text.split()
        command = parts[0][1:]  # убираем /
        
        # Парсим количество
        count = 1
        args_start = 1
        
        if len(parts) > 1 and parts[1].isdigit():
            count = min(int(parts[1]), 5)
            args_start = 2
        
        # Определяем тип контента
        if command in ['photo', 'meme', 'gif']:
            query = ' '.join(parts[args_start:]) if len(parts) > args_start else None
            bot.send_message(message.chat.id, f"🔍 Ищу...")
            send_photo_with_text(message.chat.id, None, command, query, count)
        
        elif command == 'emoji':
            emoji = get_user_emoji(message.from_user.id)
            phrase = random.choice(EMOJI_PHRASES).format(emoji=emoji)
            bot.send_message(message.chat.id, phrase)
        
        elif command == 'text':
            # Ищем текст в кавычках
            text_match = re.search(r'"([^"]+)"', message.text)
            if text_match:
                text_to_add = text_match.group(1)
                remaining = re.sub(r'"[^"]+"', '', message.text).strip()
                # Убираем команду и число из оставшегося
                remaining_parts = remaining.split()
                if remaining_parts and remaining_parts[0] == '/text':
                    remaining_parts = remaining_parts[1:]
                if remaining_parts and remaining_parts[0].isdigit():
                    remaining_parts = remaining_parts[1:]
                query = ' '.join(remaining_parts) if remaining_parts else None
                
                bot.send_message(message.chat.id, f"🖼️ Генерирую фото с текстом...")
                send_photo_with_text(message.chat.id, text_to_add, 'photo', query, count)
            else:
                bot.send_message(message.chat.id, "❌ Используйте кавычки: /text \"Привет\"")
        
        elif command == 'randtext':
            phrase = get_russian_phrase()
            query = ' '.join(parts[args_start:]) if len(parts) > args_start else None
            bot.send_message(message.chat.id, f"🖼️ Генерирую фото с фразой...")
            send_photo_with_text(message.chat.id, phrase, 'photo', query, count)
        
        elif command in ['papich', 'tehnik']:
            phrase = get_random_phrase(command)
            query = ' '.join(parts[args_start:]) if len(parts) > args_start else None
            bot.send_message(message.chat.id, f"🖼️ Генерирую фото с фразой...")
            send_photo_with_text(message.chat.id, phrase, 'photo', query, count)
            
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")

@app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        try:
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return 'OK', 200
        except Exception as e:
            print(f"Ошибка: {e}")
            return 'Error', 500
    abort(403)

@app.route('/')
def index():
    return 'Personal bot is running!', 200

@app.route('/health')
def health():
    return 'OK', 200

def setup_webhook():
    hostname = os.getenv("RAILWAY_PUBLIC_DOMAIN")
    if not hostname:
        print("Локальный режим")
        return
    
    webhook_path = f"/{TELEGRAM_TOKEN}"
    webhook_url = f"https://{hostname}{webhook_path}"
    
    try:
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url=webhook_url)
        print(f"Webhook установлен: {webhook_url}")
    except Exception as e:
        print(f"Ошибка webhook: {e}")

if __name__ == '__main__':
    print("🚀 Запуск personal бота...")
    setup_webhook()
    app.run(host='0.0.0.0', port=PORT, debug=False)
else:
    setup_webhook()