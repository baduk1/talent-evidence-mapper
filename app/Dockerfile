FROM python:3.11-slim

WORKDIR /app

# Сначала зависимости - слой закэшируется и не будет пересобираться
# при каждой правке кода
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app/src
EXPOSE 8000

CMD ["uvicorn", "tem.main:app", "--host", "0.0.0.0", "--port", "8000"]