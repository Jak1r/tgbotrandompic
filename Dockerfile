FROM python:3.11-slim

# Устанавливаем необходимые пакеты
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    cabextract \
    xfonts-utils \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Microsoft Core Fonts через cabextract
RUN wget -O /tmp/impact.exe "https://downloads.sourceforge.net/project/corefonts/the%20fonts/final/impact32.exe" \
    && cabextract -L -d /app/fonts /tmp/impact.exe \
    && rm /tmp/impact.exe \
    && mv /app/fonts/Impact.TTF /app/fonts/Impact.ttf

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]