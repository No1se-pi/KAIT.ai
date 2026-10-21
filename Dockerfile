FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --default-timeout=120 --retries=10 -r requirements.txt

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
       
COPY app ./app
COPY data ./data

RUN mkdir -p /app/logs/telegram_sessions /app/logs/web_sessions

CMD ["python", "-m", "app.bootstrap"]


