FROM python:3.11-slim

# Устанавливаем wget и скачиваем Impact.ttf (классика мемов)
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /app/fonts \
    && wget -O /app/fonts/Impact.ttf \
    https://github.com/sophilabs/macgifer/raw/master/static/font/impact.ttf

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]