FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV SYNC_INTERVAL_MINUTES=30

CMD ["python", "-u", "scheduler.py"]