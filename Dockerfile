FROM ghcr.io/astral-sh/uv:python3.14-alpine AS builder

WORKDIR /app
COPY pyproject.toml uv.lock ./
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
    && apk add --no-cache curl \
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
    PORT="8332" \
    SCHEME="http" \
    DATABASE_URL="sqlite+aiosqlite:////data/weather.db"

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD curl --fail http://localhost:8332/health || exit 1

EXPOSE 8332
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8332", "--proxy-headers", "--forwarded-allow-ips=127.0.0.1,::1"]
