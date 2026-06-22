FROM ghcr.io/astral-sh/uv:python3.14-alpine AS builder

WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --no-dev --frozen --no-install-project
COPY backend/ ./backend/
RUN uv sync --no-dev --frozen


FROM python:3.14-alpine

ENV PYTHONDONTWRITEBYTECODE=1

COPY --from=builder /app/.venv /app/.venv

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

ENV PATH="/app/.venv/bin:$PATH" \
    MQTT_BROKER="" \
    MQTT_PORT="1883" \
    MQTT_USER="" \
    DOMAIN="localhost" \
    PORT="8000" \
    SCHEME="http" \
    DATABASE_URL="sqlite+aiosqlite:////data/weather.db"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
