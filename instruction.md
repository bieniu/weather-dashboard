# Instrukcja implementacji — Weather Dashboard (MQTT + FastAPI + Material Design)

Instrukcja dla agenta AI do implementacji aplikacji webowej wyświetlającej dane pogodowe pobierane z brokera MQTT. Backend w Pythonie (FastAPI), frontend w Material Design z wykresami zmian z ostatnich 12 godzin.

---

## Wymagania środowiskowe

### Zależności Python

```
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
aiomqtt>=2.0.0
sqlalchemy>=2.0.0
aiosqlite>=0.20.0
pydantic-settings>=2.2.0
python-dotenv>=1.0.0
```

Zapisz jako `backend/requirements.txt`.

### Plik `.env`

```env
MQTT_BROKER
MQTT_PORT
MQTT_USER
MQTT_PASSWORD
```

Plik jest już w katalogu `backend/`.

---

## Struktura projektu

```
weather-dashboard/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── mqtt_client.py
│   │   └── routers/
│   │       ├── __init__.py
│   │       └── weather.py
│   ├── requirements.txt
│   └── .env
└── frontend/
    ├── index.html
    ├── style.css
    └── app.js
```

---

## Implementacja backendu

### 1. Konfiguracja (`app/config.py`)

Wczytuje zmienne ze środowiska / pliku `.env`.

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    mqtt_broker: str
    mqtt_port: int = 1883
    mqtt_user: str
    mqtt_password: str

settings = Settings()
```

---

### 2. Baza danych (`app/database.py`)

SQLite z asynchronicznym SQLAlchemy. Plik bazy danych tworzony automatycznie.

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = "sqlite+aiosqlite:///./weather.db"

engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

class Base(DeclarativeBase):
    pass

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with SessionLocal() as session:
        yield session
```

---

### 3. Model ORM (`app/models.py`)

Jeden rekord = jeden odczyt z jednego topiku. Indeks na `(parameter, timestamp)` przyspiesza zapytania historyczne.

```python
from sqlalchemy import Column, Integer, Float, String, DateTime, Index
from datetime import datetime, timezone
from .database import Base

class WeatherReading(Base):
    __tablename__ = "weather_readings"

    id        = Column(Integer, primary_key=True, autoincrement=True)
    parameter = Column(String(50), nullable=False)   # "temperature" | "humidity"
    value     = Column(Float, nullable=False)
    unit      = Column(String(10), nullable=False)   # "°C" | "%"
    timestamp = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    __table_args__ = (
        Index("ix_weather_parameter_timestamp", "parameter", "timestamp"),
    )
```

---

### 4. Schematy Pydantic (`app/schemas.py`)

```python
from pydantic import BaseModel
from datetime import datetime

class MqttPayload(BaseModel):
    value: float
    unit: str

class WeatherReadingOut(BaseModel):
    id: int
    parameter: str
    value: float
    unit: str
    timestamp: datetime

    model_config = {"from_attributes": True}

class CurrentReadings(BaseModel):
    temperature: WeatherReadingOut | None
    humidity: WeatherReadingOut | None
```

---

### 5. Klient MQTT (`app/mqtt_client.py`)

Subskrybuje obydwa topiki, parsuje JSON payload, zapisuje do bazy danych i rozsyła aktualizację przez WebSocket do wszystkich podłączonych klientów frontendu.

#### Mapowanie topików

| Topik MQTT | Parametr w DB |
|---|---|
| `weather-dashboard/temperature` | `temperature` |
| `weather-dashboard/humidity` | `humidity` |

```python
import asyncio
import json
import aiomqtt
from datetime import datetime, timezone
from .config import settings
from .database import SessionLocal
from .models import WeatherReading

TOPIC_PARAMETER_MAP = {
    "weather-dashboard/temperature": "temperature",
    "weather-dashboard/humidity":    "humidity",
}

class WebSocketManager:
    """Przechowuje aktywne połączenia WebSocket i rozsyła wiadomości."""

    def __init__(self):
        self.active_connections: list = []

    async def connect(self, websocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, data: dict):
        import json
        message = json.dumps(data)
        for connection in self.active_connections.copy():
            try:
                await connection.send_text(message)
            except Exception:
                self.active_connections.remove(connection)

manager = WebSocketManager()


async def mqtt_listener():
    """
    Główna pętla klienta MQTT.
    Uruchamiana jako zadanie asyncio w lifespan FastAPI.
    Przy zerwaniu połączenia ponawia próbę co 5 sekund.
    """
    while True:
        try:
            async with aiomqtt.Client(
                hostname=settings.mqtt_broker,
                port=settings.mqtt_port,
                username=settings.mqtt_user,
                password=settings.mqtt_password,
            ) as client:
                await client.subscribe("weather-dashboard/#")
                print(f"[MQTT] Połączono z {settings.mqtt_broker}:{settings.mqtt_port}")

                async for message in client.messages:
                    topic = str(message.topic)
                    parameter = TOPIC_PARAMETER_MAP.get(topic)
                    if parameter is None:
                        continue  # nieznany topik — ignoruj

                    try:
                        payload = json.loads(message.payload)
                        value = float(payload["value"])
                        unit  = str(payload["unit"])
                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        print(f"[MQTT] Błąd parsowania payloadu na topiku {topic}: {e}")
                        continue

                    # Zapis do bazy danych
                    async with SessionLocal() as db:
                        reading = WeatherReading(
                            parameter=parameter,
                            value=value,
                            unit=unit,
                            timestamp=datetime.now(timezone.utc),
                        )
                        db.add(reading)
                        await db.commit()
                        await db.refresh(reading)

                    # Broadcast do frontendu przez WebSocket
                    await manager.broadcast({
                        "parameter": parameter,
                        "value": value,
                        "unit": unit,
                        "timestamp": reading.timestamp.isoformat(),
                    })

        except aiomqtt.MqttError as e:
            print(f"[MQTT] Błąd połączenia: {e}. Ponawianie za 5s...")
            await asyncio.sleep(5)
```

---

### 6. Router REST + WebSocket (`app/routers/weather.py`)

```python
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from datetime import datetime, timezone, timedelta
from ..database import get_db
from ..models import WeatherReading
from ..schemas import WeatherReadingOut, CurrentReadings
from ..mqtt_client import manager

router = APIRouter(prefix="/api/weather", tags=["weather"])


@router.get("/current", response_model=CurrentReadings)
async def get_current(db: AsyncSession = Depends(get_db)):
    """Zwraca ostatni odczyt temperatury i wilgotności."""
    result = {}
    for param in ("temperature", "humidity"):
        stmt = (
            select(WeatherReading)
            .where(WeatherReading.parameter == param)
            .order_by(desc(WeatherReading.timestamp))
            .limit(1)
        )
        row = (await db.execute(stmt)).scalar_one_or_none()
        result[param] = row
    return result


@router.get("/history/{parameter}", response_model=list[WeatherReadingOut])
async def get_history(
    parameter: str,
    hours: int = 12,
    db: AsyncSession = Depends(get_db),
):
    """
    Zwraca historię odczytów z ostatnich `hours` godzin (domyślnie 12).
    Parametr: 'temperature' lub 'humidity'.
    """
    if parameter not in ("temperature", "humidity"):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Nieprawidłowy parametr")

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = (
        select(WeatherReading)
        .where(
            WeatherReading.parameter == parameter,
            WeatherReading.timestamp >= since,
        )
        .order_by(WeatherReading.timestamp)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return rows


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket — push nowych odczytów do klientów frontendu."""
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep-alive ping
    except WebSocketDisconnect:
        manager.disconnect(websocket)
```

---

### 7. Główna aplikacja (`app/main.py`)

```python
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .database import init_db
from .mqtt_client import mqtt_listener
from .routers.weather import router as weather_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    mqtt_task = asyncio.create_task(mqtt_listener())
    yield
    # Shutdown
    mqtt_task.cancel()
    try:
        await mqtt_task
    except asyncio.CancelledError:
        pass

app = FastAPI(title="Weather Dashboard", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(weather_router)

# Serwuj frontend ze statycznych plików
app.mount("/", StaticFiles(directory="../frontend", html=True), name="frontend")
```

---

### Uruchomienie backendu

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Dokumentacja API dostępna automatycznie pod: `http://localhost:8000/docs`

---

## Implementacja frontendu

### 8. `frontend/index.html`

Używa Material Web Components (MWC) via ESM CDN oraz Chart.js dla wykresów.

```html
<!DOCTYPE html>
<html lang="pl" data-theme="light">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Weather Dashboard</title>

  <!-- Material Symbols + Roboto -->
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&family=Roboto+Mono:wght@400;500&display=swap" rel="stylesheet" />
  <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,1,0" rel="stylesheet" />

  <!-- Chart.js -->
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
  <!-- date-fns adapter dla osi czasu Chart.js -->
  <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>

  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <!-- Top App Bar -->
  <header class="top-app-bar">
    <div class="top-app-bar__content">
      <span class="top-app-bar__title">
        <span class="material-symbols-rounded">partly_cloudy_day</span>
        Weather Station
      </span>
      <div class="top-app-bar__actions">
        <span id="connection-status" class="status-chip status-chip--disconnected">
          <span class="material-symbols-rounded">wifi_off</span>
          Rozłączono
        </span>
        <button class="icon-btn" id="theme-toggle" aria-label="Przełącz motyw" data-theme-toggle>
          <span class="material-symbols-rounded">dark_mode</span>
        </button>
      </div>
    </div>
  </header>

  <main class="main-content">
    <!-- Siatka kart pogodowych -->
    <div class="weather-grid">

      <!-- Karta: Temperatura -->
      <article class="weather-card" id="card-temperature">
        <div class="weather-card__header">
          <span class="material-symbols-rounded weather-card__icon weather-card__icon--temp">thermometer</span>
          <span class="weather-card__label">Temperatura</span>
        </div>
        <div class="weather-card__current">
          <span class="weather-card__value" id="temp-value">--</span>
          <span class="weather-card__unit">°C</span>
        </div>
        <p class="weather-card__updated" id="temp-updated">Oczekiwanie na dane...</p>
        <div class="weather-card__chart-wrapper">
          <canvas id="chart-temperature" aria-label="Wykres temperatury z ostatnich 12 godzin" role="img"></canvas>
        </div>
      </article>

      <!-- Karta: Wilgotność -->
      <article class="weather-card" id="card-humidity">
        <div class="weather-card__header">
          <span class="material-symbols-rounded weather-card__icon weather-card__icon--humidity">humidity_percentage</span>
          <span class="weather-card__label">Wilgotność</span>
        </div>
        <div class="weather-card__current">
          <span class="weather-card__value" id="humidity-value">--</span>
          <span class="weather-card__unit">%</span>
        </div>
        <p class="weather-card__updated" id="humidity-updated">Oczekiwanie na dane...</p>
        <div class="weather-card__chart-wrapper">
          <canvas id="chart-humidity" aria-label="Wykres wilgotności z ostatnich 12 godzin" role="img"></canvas>
        </div>
      </article>

    </div>
  </main>

  <script src="app.js" type="module"></script>
</body>
</html>
```

---

### 9. `frontend/style.css`

Material Design 3 — własna implementacja z tokenami kolorów MD3 (Dynamic Color Teal).

```css
/* ========== TOKENY MATERIAL DESIGN 3 ========== */
:root, [data-theme="light"] {
  --md-sys-color-primary:           #006874;
  --md-sys-color-on-primary:        #ffffff;
  --md-sys-color-primary-container: #97f0ff;
  --md-sys-color-surface:           #f5fafb;
  --md-sys-color-surface-variant:   #dbe4e6;
  --md-sys-color-on-surface:        #171d1e;
  --md-sys-color-on-surface-variant:#3f4849;
  --md-sys-color-outline:           #6f797a;
  --md-sys-color-outline-variant:   #bfc8ca;
  --md-sys-color-background:        #f5fafb;
  --md-sys-color-error:             #ba1a1a;

  --md-sys-color-temp-accent:       #c62828;
  --md-sys-color-humidity-accent:   #1565c0;

  --md-elevation-1: 0 1px 2px rgba(0,0,0,.06), 0 2px 6px rgba(0,0,0,.08);
  --md-elevation-2: 0 2px 4px rgba(0,0,0,.08), 0 4px 12px rgba(0,0,0,.10);
  --md-elevation-3: 0 4px 8px rgba(0,0,0,.10), 0 8px 24px rgba(0,0,0,.12);

  --transition: 200ms cubic-bezier(0.2, 0, 0, 1);
}

[data-theme="dark"] {
  --md-sys-color-primary:           #4fd8eb;
  --md-sys-color-on-primary:        #00363d;
  --md-sys-color-primary-container: #004f58;
  --md-sys-color-surface:           #0e1415;
  --md-sys-color-surface-variant:   #3f4849;
  --md-sys-color-on-surface:        #e6f2f3;
  --md-sys-color-on-surface-variant:#bfc8ca;
  --md-sys-color-outline:           #899395;
  --md-sys-color-outline-variant:   #3f4849;
  --md-sys-color-background:        #0e1415;
  --md-sys-color-error:             #ffb4ab;

  --md-sys-color-temp-accent:       #ef9a9a;
  --md-sys-color-humidity-accent:   #90caf9;

  --md-elevation-1: 0 1px 2px rgba(0,0,0,.3), 0 2px 6px rgba(0,0,0,.25);
  --md-elevation-2: 0 2px 4px rgba(0,0,0,.35), 0 4px 12px rgba(0,0,0,.30);
  --md-elevation-3: 0 4px 8px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.35);
}

/* ========== RESET ========== */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html {
  -webkit-text-size-adjust: none;
  text-size-adjust: none;
  -webkit-font-smoothing: antialiased;
  scroll-behavior: smooth;
}
body {
  font-family: 'Roboto', sans-serif;
  font-size: 1rem;
  line-height: 1.5;
  background: var(--md-sys-color-background);
  color: var(--md-sys-color-on-surface);
  min-height: 100dvh;
  transition: background var(--transition), color var(--transition);
}

/* ========== TOP APP BAR ========== */
.top-app-bar {
  position: sticky;
  top: 0;
  z-index: 100;
  background: var(--md-sys-color-surface);
  border-bottom: 1px solid var(--md-sys-color-outline-variant);
  box-shadow: var(--md-elevation-1);
}
.top-app-bar__content {
  max-width: 1200px;
  margin-inline: auto;
  padding: 0.75rem 1rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}
.top-app-bar__title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 1.25rem;
  font-weight: 500;
  color: var(--md-sys-color-on-surface);
}
.top-app-bar__actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

/* ========== WSKAŹNIK POŁĄCZENIA ========== */
.status-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.75rem;
  border-radius: 9999px;
  font-size: 0.8125rem;
  font-weight: 500;
  transition: background var(--transition), color var(--transition);
}
.status-chip .material-symbols-rounded { font-size: 1rem; }
.status-chip--connected    { background: #e8f5e9; color: #1b5e20; }
.status-chip--disconnected { background: #fce4ec; color: #b71c1c; }
[data-theme="dark"] .status-chip--connected    { background: #1b5e20; color: #a5d6a7; }
[data-theme="dark"] .status-chip--disconnected { background: #4a0000; color: #ef9a9a; }

/* ========== PRZYCISK IKONY ========== */
.icon-btn {
  cursor: pointer;
  background: none;
  border: none;
  width: 2.75rem;
  height: 2.75rem;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--md-sys-color-on-surface-variant);
  transition: background var(--transition), color var(--transition);
}
.icon-btn:hover  { background: color-mix(in srgb, var(--md-sys-color-on-surface) 8%, transparent); }
.icon-btn:active { background: color-mix(in srgb, var(--md-sys-color-on-surface) 12%, transparent); }

/* ========== GŁÓWNA TREŚĆ ========== */
.main-content {
  max-width: 1200px;
  margin-inline: auto;
  padding: 1.5rem 1rem;
}

/* ========== SIATKA KART ========== */
.weather-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(400px, 100%), 1fr));
  gap: 1rem;
}

/* ========== KARTA POGODOWA ========== */
.weather-card {
  background: var(--md-sys-color-surface);
  border-radius: 1rem;
  padding: 1.25rem;
  box-shadow: var(--md-elevation-1);
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  transition: box-shadow var(--transition), background var(--transition);
}
.weather-card:hover { box-shadow: var(--md-elevation-2); }

.weather-card__header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.weather-card__icon {
  font-size: 1.5rem;
}
.weather-card__icon--temp     { color: var(--md-sys-color-temp-accent); }
.weather-card__icon--humidity { color: var(--md-sys-color-humidity-accent); }

.weather-card__label {
  font-size: 0.875rem;
  font-weight: 500;
  letter-spacing: 0.01em;
  color: var(--md-sys-color-on-surface-variant);
  text-transform: uppercase;
}

.weather-card__current {
  display: flex;
  align-items: baseline;
  gap: 0.25rem;
}
.weather-card__value {
  font-size: clamp(2.5rem, 6vw, 3.5rem);
  font-weight: 300;
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums lining-nums;
  line-height: 1;
  transition: color 300ms ease;
}
.weather-card__unit {
  font-size: 1.25rem;
  font-weight: 400;
  color: var(--md-sys-color-on-surface-variant);
}

.weather-card__updated {
  font-size: 0.75rem;
  color: var(--md-sys-color-on-surface-variant);
  min-height: 1.2em;
}

.weather-card__chart-wrapper {
  position: relative;
  height: 160px;
  margin-top: 0.5rem;
}

/* ========== RESPONSYWNOŚĆ ========== */
@media (max-width: 480px) {
  .top-app-bar__title { font-size: 1.1rem; }
  .status-chip span:last-child { display: none; } /* Tylko ikona na małych ekranach */
  .weather-card { padding: 1rem; }
  .weather-card__chart-wrapper { height: 130px; }
}
```

---

### 10. `frontend/app.js`

Inicjalizuje wykresy, pobiera dane historyczne z REST API, podłącza WebSocket do live updates i obsługuje przełącznik motywu.

```javascript
// ===== KONFIGURACJA =====
const API_BASE = "http://localhost:8000/api/weather";
const WS_URL   = "ws://localhost:8000/api/weather/ws";
const HISTORY_HOURS = 12;
const MAX_CHART_POINTS = 144; // co 5 minut przez 12h = 144 pkt

// ===== STAN WYKRESÓW =====
const charts = {};

// ===== HELPERS =====
function formatTimestamp(isoString) {
  const d = new Date(isoString);
  return d.toLocaleTimeString("pl-PL", { hour: "2-digit", minute: "2-digit" });
}

function formatUpdated(isoString) {
  const d = new Date(isoString);
  return `Zaktualizowano: ${d.toLocaleTimeString("pl-PL")}`;
}

// ===== INICJALIZACJA WYKRESÓW =====
function createChart(canvasId, parameter, color) {
  const ctx = document.getElementById(canvasId).getContext("2d");

  return new Chart(ctx, {
    type: "line",
    data: {
      datasets: [{
        data: [],
        borderColor: color,
        backgroundColor: color + "22",
        borderWidth: 2,
        pointRadius: 0,
        pointHoverRadius: 4,
        tension: 0.3,
        fill: true,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 400 },
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => ` ${ctx.parsed.y} ${parameter === "temperature" ? "°C" : "%"}`,
            title: (items) => formatTimestamp(items[0].raw.x),
          }
        }
      },
      scales: {
        x: {
          type: "time",
          time: { unit: "hour", tooltipFormat: "HH:mm" },
          grid: { color: getComputedStyle(document.documentElement)
                           .getPropertyValue("--md-sys-color-outline-variant").trim() },
          ticks: {
            font: { family: "Roboto", size: 11 },
            color: getComputedStyle(document.documentElement)
                     .getPropertyValue("--md-sys-color-on-surface-variant").trim(),
            maxTicksLimit: 6,
          }
        },
        y: {
          grid: { color: getComputedStyle(document.documentElement)
                           .getPropertyValue("--md-sys-color-outline-variant").trim() },
          ticks: {
            font: { family: "Roboto Mono", size: 11 },
            color: getComputedStyle(document.documentElement)
                     .getPropertyValue("--md-sys-color-on-surface-variant").trim(),
          }
        }
      }
    }
  });
}

// ===== AKTUALIZACJA KARTY =====
function updateCard(parameter, value, unit, timestamp) {
  const valueEl   = document.getElementById(`${parameter === "temperature" ? "temp" : "humidity"}-value`);
  const updatedEl = document.getElementById(`${parameter === "temperature" ? "temp" : "humidity"}-updated`);

  if (valueEl)   valueEl.textContent   = value;
  if (updatedEl) updatedEl.textContent = formatUpdated(timestamp);
}

// ===== DODANIE PUNKTU DO WYKRESU =====
function appendChartPoint(parameter, value, timestamp) {
  const chart = charts[parameter];
  if (!chart) return;

  chart.data.datasets[0].data.push({ x: new Date(timestamp), y: value });

  // Ogranicz liczbę punktów
  if (chart.data.datasets[0].data.length > MAX_CHART_POINTS) {
    chart.data.datasets[0].data.shift();
  }

  chart.update("none"); // aktualizacja bez animacji dla live data
}

// ===== POBIERANIE HISTORII (REST) =====
async function loadHistory(parameter) {
  try {
    const res = await fetch(`${API_BASE}/history/${parameter}?hours=${HISTORY_HOURS}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const history = await res.json();

    const chart = charts[parameter];
    if (!chart) return;

    chart.data.datasets[0].data = history.map(r => ({
      x: new Date(r.timestamp),
      y: r.value,
    }));
    chart.update();

    // Ustaw aktualną wartość z ostatniego rekordu
    if (history.length > 0) {
      const last = history[history.length - 1];
      updateCard(parameter, last.value, last.unit, last.timestamp);
    }
  } catch (err) {
    console.error(`[History] Błąd pobierania ${parameter}:`, err);
  }
}

// ===== WEBSOCKET — LIVE UPDATES =====
function connectWebSocket() {
  const statusEl = document.getElementById("connection-status");
  const ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    console.log("[WS] Połączono");
    statusEl.className = "status-chip status-chip--connected";
    statusEl.innerHTML = `<span class="material-symbols-rounded">wifi</span><span>Połączono</span>`;
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      updateCard(data.parameter, data.value, data.unit, data.timestamp);
      appendChartPoint(data.parameter, data.value, data.timestamp);
    } catch (e) {
      console.warn("[WS] Błąd parsowania wiadomości:", e);
    }
  };

  ws.onclose = () => {
    console.warn("[WS] Rozłączono. Ponawianie za 5s...");
    statusEl.className = "status-chip status-chip--disconnected";
    statusEl.innerHTML = `<span class="material-symbols-rounded">wifi_off</span><span>Rozłączono</span>`;
    setTimeout(connectWebSocket, 5000);
  };

  ws.onerror = (err) => {
    console.error("[WS] Błąd:", err);
    ws.close();
  };
}

// ===== PRZEŁĄCZNIK MOTYWU =====
function initThemeToggle() {
  const btn = document.querySelector("[data-theme-toggle]");
  const html = document.documentElement;
  let theme = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  html.setAttribute("data-theme", theme);

  const updateIcon = () => {
    btn.querySelector(".material-symbols-rounded").textContent =
      theme === "dark" ? "light_mode" : "dark_mode";
    btn.setAttribute("aria-label",
      theme === "dark" ? "Przełącz na jasny motyw" : "Przełącz na ciemny motyw");
  };
  updateIcon();

  btn.addEventListener("click", () => {
    theme = theme === "dark" ? "light" : "dark";
    html.setAttribute("data-theme", theme);
    updateIcon();
    // Odśwież kolory osi wykresów po zmianie motywu
    Object.values(charts).forEach(c => c.update());
  });
}

// ===== INICJALIZACJA APLIKACJI =====
async function init() {
  initThemeToggle();

  // Utwórz wykresy
  charts["temperature"] = createChart(
    "chart-temperature",
    "temperature",
    getComputedStyle(document.documentElement)
      .getPropertyValue("--md-sys-color-temp-accent").trim()
  );
  charts["humidity"] = createChart(
    "chart-humidity",
    "humidity",
    getComputedStyle(document.documentElement)
      .getPropertyValue("--md-sys-color-humidity-accent").trim()
  );

  // Pobierz dane historyczne
  await Promise.all([
    loadHistory("temperature"),
    loadHistory("humidity"),
  ]);

  // Podłącz WebSocket
  connectWebSocket();
}

document.addEventListener("DOMContentLoaded", init);
```

---

## Czyszczenie starych danych

Aby baza danych nie rosła w nieskończoność, dodaj zaplanowane zadanie w `app/main.py`.

### Dodaj do `lifespan` w `main.py`

```python
import asyncio
from sqlalchemy import delete, text

async def cleanup_old_readings():
    """Usuwa odczyty starsze niż 30 dni — uruchamiane co godzinę."""
    while True:
        await asyncio.sleep(3600)
        async with SessionLocal() as db:
            cutoff = datetime.now(timezone.utc) - timedelta(days=30)
            await db.execute(
                delete(WeatherReading).where(WeatherReading.timestamp < cutoff)
            )
            await db.commit()
            print("[Cleanup] Usunięto stare rekordy")

# W lifespan, obok mqtt_task:
cleanup_task = asyncio.create_task(cleanup_old_readings())
```

---

## Opcjonalne: Docker Compose

```yaml
# docker-compose.yml (w katalogu głównym projektu)
services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    env_file:
      - ./backend/.env
    volumes:
      - ./backend:/app
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000

  # Tylko jeśli masz własny broker Mosquitto
  # mosquitto:
  #   image: eclipse-mosquitto:2
  #   ports: ["1883:1883"]
  #   volumes: ["./mosquitto.conf:/mosquitto/config/mosquitto.conf"]
```

```dockerfile
# backend/Dockerfile
FROM python:3.14-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## Kolejność implementacji dla agenta

1. Utwórz strukturę katalogów i pliki `__init__.py`
2. Zapisz `requirements.txt` i zainstaluj zależności
3. Zaimplementuj w kolejności: `config.py` → `database.py` → `models.py` → `schemas.py`
4. Zaimplementuj `mqtt_client.py` — przetestuj połączenie z brokerem (`mosquitto_sub` lub `MQTT Explorer`)
5. Zaimplementuj `routers/weather.py` i `main.py`
6. Uruchom backend: `uvicorn app.main:app --reload`
7. Sprawdź `http://localhost:8000/docs` — przetestuj endpointy `/current` i `/history/temperature`
8. Utwórz pliki frontendu: `index.html`, `style.css`, `app.js`
9.  Otwórz `index.html` w przeglądarce — sprawdź wykresy i live updates
10. Zweryfikuj responsywność w DevTools na 375px i 768px
11. Zaimplementuj unit testy dla backendu
12. Zaimplementuj unit testy dla frontendu

---

## Uwagi dla agenta
- Kod Pythona z docstringami i annotacja typów
- Plik `.env` **nigdy nie jest commitowany** — dodaj `backend/.env` do `.gitignore`
- stwórz venv dla pythona 3.14
- `aiosqlite` jest wymagane jako sterownik dla `sqlite+aiosqlite://` w SQLAlchemy
- CORS jest ustawiony na `allow_origins=["*"]` — w produkcji ogranicz do konkretnej domeny
- Wykresy Chart.js używają `chartjs-adapter-date-fns` — **oba skrypty muszą być załadowane** (Chart.js przed adapterem)
- Jeśli frontend i backend są na różnych portach w produkcji, zmień `API_BASE` i `WS_URL` w `app.js`
