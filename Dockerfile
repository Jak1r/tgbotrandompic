FROM python:3.11-slim

# Устанавливаем wget
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /app/fonts

# Скачиваем Impact с кириллицей
RUN wget -O /app/fonts/Impact.ttf \
    "https://raw.githubusercontent.com/HuakunShen/Fonts/master/Impact.ttf"

# ИЛИ альтернативный источник:
# RUN wget -O /app/fonts/Impact.ttf \
#     "https://github.com/mat/best/raw/master/fonts/impact/impact.ttf"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]