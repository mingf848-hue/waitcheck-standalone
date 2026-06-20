FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 10000

CMD ["gunicorn", "app:app", "--workers", "1", "--threads", "8", "--timeout", "300", "--bind", "0.0.0.0:10000"]
