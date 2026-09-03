FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY client ./client

WORKDIR /app/client

EXPOSE 8080

CMD ["gunicorn", "--workers", "1", "--threads", "100", "--bind", "0.0.0.0:8080", "server:app"]