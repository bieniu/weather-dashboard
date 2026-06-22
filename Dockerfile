FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY config.yaml ./config.yaml

RUN addgroup --system appuser && adduser --system --no-create-home --ingroup appuser appuser

WORKDIR /app/backend

VOLUME ["/data"]

RUN chown -R appuser:appuser /app

USER appuser

ENV MQTT_BROKER=""
ENV MQTT_PORT="1883"
ENV MQTT_USER=""
# MQTT_PASSWORD must be provided at runtime (via -e / env_file) - not set here to avoid baking secrets into the image
ENV DOMAIN="localhost"
ENV PORT="8000"
ENV SCHEME="http"
ENV DATABASE_URL="sqlite+aiosqlite:////data/weather.db"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
