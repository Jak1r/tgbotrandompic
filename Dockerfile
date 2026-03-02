# Базовый образ — лёгкий и быстрый
FROM python:3.11-slim

# Устанавливаем зависимости + wget для скачивания шрифта
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Создаём папку для шрифтов и скачиваем Impact.ttf (из надёжного зеркала)
RUN mkdir -p /app/fonts \
    && wget -O /app/fonts/Impact.ttf \
    https://github.com/sophilabs/macgifer/raw/master/static/font/impact.ttf

# Рабочая директория
WORKDIR /app

# Копируем и устанавливаем Python-зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код проекта
COPY . .

# Запускаем бота
CMD ["python", "bot.py"]