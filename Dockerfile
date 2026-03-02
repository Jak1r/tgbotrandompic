FROM python:3.11-slim

# Устанавливаем необходимые пакеты
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    cabextract \
    xfonts-utils \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /app/fonts

# Устанавливаем Microsoft Core Fonts через cabextract
RUN wget -O /tmp/impact.exe "https://downloads.sourceforge.net/project/corefonts/the%20fonts/final/impact32.exe" \
    && cabextract -L -d /app/fonts /tmp/impact.exe \
    && rm /tmp/impact.exe \
    && ls -la /app/fonts/  # для отладки

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]