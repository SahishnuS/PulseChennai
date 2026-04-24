# Pulse-Chennai

A cloud-native, event-driven geospatial intelligence engine for reliable urban transit in Chennai. Detects and recovers "Ghost Buses" using multi-source data fusion: AIS-140 hardware auditing, crowdsourced passenger telemetry, and TomTom traffic flow integration.

## Architecture

```
                              ┌──────────────────┐
                              │   AIS-140 GPS    │
                              │   Simulator      │
                              └────────┬─────────┘
                                       │ POST /api/ingest
                              ┌────────▼─────────┐
                              │  Kafka Producer   │
                              │  bus-gps-pings    │
                              └────────┬─────────┘
                                       │
                    ┌──────────────────▼──────────────────┐
                    │         Kafka Consumer               │
                    │  ┌─────────────────────────────┐    │
                    │  │ Hardware Reliability Scorer  │    │
                    │  │ (Jitter + Speed + Freq + Pos)│    │
                    │  └──────────┬──────────────────┘    │
                    │             │                        │
                    │    hw_score < 0.3?                   │
                    │    ┌───────┴───────┐                 │
                    │    │ YES           │ NO              │
                    │    ▼               ▼                 │
                    │  Ghost Bus    Standard Update        │
                    │  Detection   → Redis + DB            │
                    │    │                                  │
                    │    ├─ Passenger Ping Fusion           │
                    │    ├─ TomTom Dead Reckoning          │
                    │    └─ WebSocket Publish              │
                    └─────────────────────────────────────┘
                                       │
                    ┌──────────────────▼──────────────────┐
                    │         Frontend Dashboard           │
                    │  WebSocket /ws/live                   │
                    │  TomTom Map + Glassmorphism UI        │
                    │  Ghost alerts + Traffic bars          │
                    └──────────────────────────────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI + Uvicorn (async) |
| Streaming | Apache Kafka (aiokafka) |
| Cache | Redis (redis.asyncio) |
| Database | PostgreSQL + PostGIS (asyncpg) |
| ML | PyTorch Geometric (GAT + LSTM) |
| Traffic | TomTom Traffic Flow API |
| Map | TomTom Web SDK / Leaflet (CARTO dark) |
| Frontend | Vanilla JS + CSS Glassmorphism |

## Prerequisites

- Python 3.11+
- Docker & Docker Compose (for Kafka, Redis, PostgreSQL)
- TomTom API key (free at [developer.tomtom.com](https://developer.tomtom.com))

## Quick Start

```bash
# 1. Clone & configure
git clone <repo>
cd pulse-chennai
cp .env.example .env
# Edit .env: set TOMTOM_API_KEY

# 2. Start infrastructure
docker-compose up -d

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start the server
uvicorn api.dashboard_server:app --host 0.0.0.0 --port 8001

# 5. Open dashboard
open http://localhost:8001

# 6. Run the simulator (separate terminal)
python -m simulator.demo_simulation
```

### Without Docker (Degraded Mode)

The system gracefully degrades without infrastructure:
- **No Kafka**: Messages processed directly (HTTP fallback)
- **No Redis**: In-memory state dictionary
- **No PostgreSQL**: Persistence disabled, warnings logged
- **No TomTom key**: Synthetic time-of-day traffic data

```bash
# Just run:
uvicorn api.dashboard_server:app --host 0.0.0.0 --port 8001
python -m simulator.demo_simulation
```

## API Reference

### `POST /api/ingest`
Receive a GPS ping from an AIS-140 device.
```bash
curl -X POST http://localhost:8001/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"device_id":"MTC-21G-001","lat":13.0827,"lng":80.2707,"speed":25,"route":"21G"}'
```

### `POST /api/passenger-ping`
Receive an anonymized passenger smartphone ping.
```bash
curl -X POST http://localhost:8001/api/passenger-ping \
  -H "Content-Type: application/json" \
  -d '{"lat":13.082,"lon":80.270,"accuracy_m":10,"session_token":"uuid-here"}'
```

### `GET /api/buses`
Get all active bus states from the speed layer.

### `GET /api/traffic`
Get current TomTom traffic summary for Chennai segments.

### `GET /api/metrics`
System-wide metrics: active/ghost/recovered buses, health.

### `GET /api/ghost-events`
Recent ghost bus detection events.

### `GET /health`
System health check (DB, Redis, Kafka, ML status).

### `WebSocket /ws/live`
Real-time bus updates pushed via Redis pub/sub.

## How Ghost Bus Detection Works

1. **Hardware Reliability Scoring**: Every GPS ping is scored on 4 dimensions:
   - Jitter Score (σ of consecutive positions)
   - Update Frequency (median inter-ping gap)
   - Impossible Speed (>120 km/h on Chennai roads)
   - Position Consistency (Haversine teleportation check)

2. **Weighted composite**: `score = 0.30·jitter + 0.25·freq + 0.30·speed + 0.15·position`

3. **EMA smoothing**: `rolling_score = 0.95·prev + 0.05·raw` (filters transient glitches)

4. **Threshold**: If `score < 0.3`, the bus is flagged as a **Ghost Bus**

5. **Recovery** (in priority order):
   - **Passenger Telemetry**: ≥3 anonymized smartphone pings within 200m → compute centroid → 70/30 weighted fusion
   - **TomTom Dead Reckoning**: Project forward using live traffic speed + last known heading
   - **Freeze**: Hold at last known position until signal recovers
