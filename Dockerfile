FROM python:3.12-alpine AS builder

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --no-compile -r requirements.txt


FROM python:3.12-alpine

ENV PYTHONDONTWRITEBYTECODE=1

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/ /usr/local/bin/

WORKDIR /app
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY config.yaml ./

RUN addgroup -S appuser && adduser -S -H -G appuser appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data

VOLUME ["/data"]
WORKDIR /app/backend
USER appuser

ENV MQTT_BROKER="" \
    MQTT_PORT="1883" \
    MQTT_USER="" \
    DOMAIN="localhost" \
    PORT="8000" \
    SCHEME="http" \
    DATABASE_URL="sqlite+aiosqlite:////data/weather.db"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
