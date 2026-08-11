FROM python:3.11-slim

WORKDIR /app

# Воркер переиспользует пакет tem (домен + БД), поэтому контекст сборки -
# корень репозитория, а не папка ml_worker.
COPY ml_worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/src /app/src
COPY ml_worker/main.py /app/main.py

ENV PYTHONPATH=/app/src

CMD ["python", "main.py"]