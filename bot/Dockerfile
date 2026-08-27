FROM python:3.11-slim

WORKDIR /app

# Бот переиспользует пакет tem (crud + очередь), поэтому контекст сборки -
# корень репозитория, как у ml_worker.
COPY bot/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/src /app/src
COPY bot/main.py /app/main.py

ENV PYTHONPATH=/app/src

CMD ["python", "main.py"]
