FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY config.yaml ./config.yaml

WORKDIR /app/backend

VOLUME ["/data"]

ENV MQTT_BROKER=""
ENV MQTT_PORT="1883"
ENV MQTT_USER=""
ENV MQTT_PASSWORD=""
ENV DATABASE_URL="sqlite+aiosqlite:////data/weather.db"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
