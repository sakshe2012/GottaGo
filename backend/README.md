# GottaGo FastAPI Backend

The official Python backend for **GottaGo**, a smart public washroom discovery, live occupancy monitoring, and AI rush prediction platform.

---

## 1. Overview & Technology Stack

- **Framework**: FastAPI (Python 3.10+)
- **Database**: SQLite (SQLAlchemy ORM with Alembic schema management)
- **Validation**: Pydantic v2
- **Machine Learning**: Scikit-learn Random Forest Classifier (`rush_model.pkl`, Joblib)
- **Geospatial Computation**: Haversine distance and spatial bounding-box indexing (`geo.py`)
- **Server**: Uvicorn ASGI Server

---

## 2. Environment Configuration & Setup

### A. Create Virtual Environment
From the `backend` directory:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### B. Install Dependencies
```bash
pip install -r requirements.txt
```

### C. Safe Environment Configuration
Copy the template configuration file:
```bash
cp .env.example .env
```

Configure your local `.env` file using placeholders:
```ini
HOST=0.0.0.0
PORT=8000
DATABASE_URL=sqlite:///./gottago.db
ENVIRONMENT=development
# Device Authentication Secret (Required for telemetry & GPS registration)
LEGACY_DEVICE_TOKEN=YOUR_SECRET_DEVICE_TOKEN
```

> [!SECURITY]
> **Secret Protection**: Never commit `.env` or hardcode tokens into version control. The backend strictly requires `LEGACY_DEVICE_TOKEN` to be set in the environment. If it is omitted or blank, all device-facing endpoints fail closed with `503 Service Unavailable`.

---

## 3. Database Architecture & Seeding

The backend stores persistent telemetry and facility data in SQLite (`backend/gottago.db`).

- **Automatic Schema Initialization**: When FastAPI starts, `init_db()` in `database.py` creates all necessary tables (`washrooms`, `devices`, `sensor_records`, `cleanliness_ratings`, `maintenance_logs`, `users`).
- **Default Seed Data**: If the database is newly initialized, `init_db()` automatically provisions:
  - **Primary Washroom (`id=1`)**: Default facility for single-stall legacy telemetry.
  - **Primary ESP32 Device (`id=1`)**: Default legacy hardware mapped to Washroom #1.
- **Isolated Test Database**: Automated tests execute against a temporary `test_gottago.db` file, which is created and deleted automatically during test runs without touching production records.

---

## 4. Hardware Device Authentication & Security

Telemetry ingestion and hardware registration require authentication via the `X-Device-Token` HTTP header:

1. **Fail-Closed Verification**: The shared function `verify_device_token(x_device_token)` runs as the first statement in protected endpoints:
   - If `LEGACY_DEVICE_TOKEN` is missing or empty on the server: Returns `HTTP 503 Service Unavailable` (`"Device authentication is not configured on the server."`).
   - If `X-Device-Token` is missing from the client request or does not match: Returns `HTTP 401 Unauthorized` (`"Invalid or missing X-Device-Token header."`).
2. **Constant-Time Comparison**: Token validation uses `hmac.compare_digest` to prevent timing side-channel attacks.
3. **Multi-Washroom Isolation**: Legacy hardware is bound strictly to Washroom #1. Any attempt to submit telemetry targeting `washroom_id != 1` is rejected with `HTTP 403 Forbidden`.

---

## 5. Machine Learning Rush Prediction Model

The backend incorporates an offline-trained **Random Forest Classifier** (`rush_model.pkl`) to predict real-time rush levels:

### Authoritative 9-Feature Schema
Features are extracted dynamically from database telemetry using `extract_features_from_db()` in `features.py`:

| # | Feature Name | Description | Value Range |
|:---:|:---|:---|:---:|
| 1 | `day_of_week` | Day index (Monday=0 ... Sunday=6) | `0` – `6` |
| 2 | `is_weekend` | Weekend binary flag | `0` or `1` |
| 3 | `hour` | Current hour of the day | `0` – `23` |
| 4 | `capacity` | Total facility stall capacity | `1` – `50` |
| 5 | `current_occupancy` | Most recent people count | `0` – `capacity` |
| 6 | `occupancy_percent` | Capacity utilization percentage | `0.0` – `100.0%` |
| 7 | `entries_5min` | Cumulative entry counts over past 5 minutes | `0+` |
| 8 | `exits_5min` | Cumulative exit counts over past 5 minutes | `0+` |
| 9 | `net_flow_5min` | Net crowd movement (`entries_5min - exits_5min`) | Integer |

### Predictions & Freshness Protection
- **Target Classes**: `LOW`, `MEDIUM`, `HIGH`
- **Output**: Predicted class label, calibrated probability breakdown across all three classes, and feature snapshot.
- **Data Freshness Guard**: Telemetry older than `MAX_STALE_SECONDS` (default: 300s / 5 minutes) triggers `prediction_status: "UNAVAILABLE"` unless explicitly bypassed via `allow_stale=true`.

---

## 6. API Reference

| Method | Endpoint | Authentication | Description |
|:---:|:---|:---:|:---|
| `GET` | `/health` | None (Public) | System health check and server timestamp |
| `POST` | `/api/sensor-data` | `X-Device-Token` | Ingest sensor telemetry and update occupancy |
| `POST` | `/api/devices/location` | `X-Device-Token` | Register immutable GPS coordinates for hardware |
| `GET` | `/api/status` | None (Public) | Current washroom occupancy status and ESP32 heartbeat |
| `GET` | `/api/history` | None (Public) | Historical sensor records for a washroom |
| `GET` | `/api/prediction` | None (Public) | Real-time AI rush prediction using Random Forest |
| `GET` | `/api/washrooms/nearby` | None (Public) | Spatial discovery & ranking of nearby washrooms |
| `GET` | `/api/washrooms/{washroom_id}` | None (Public) | Full washroom details, amenities, and live status |

---

### A. Health Check
`GET /health`

**Response (`200 OK`)**:
```json
{
  "status": "healthy",
  "backend": "GottaGo Backend",
  "timestamp": "2026-11-10T12:00:00.000000Z"
}
```

---

### B. Ingest Sensor Data (Authenticated)
`POST /api/sensor-data`

**Headers**:
```http
X-Device-Token: YOUR_DEVICE_TOKEN
Content-Type: application/json
```

**Request Body (Vacant Example)**:
```json
{
  "ir1_state": 0,
  "ir2_state": 0,
  "pir_state": 0,
  "people_count": 0,
  "occupancy_status": "VACANT"
}
```

**Request Body (Occupied Example)**:
```json
{
  "ir1_state": 1,
  "ir2_state": 0,
  "pir_state": 1,
  "people_count": 1,
  "occupancy_status": "OCCUPIED"
}
```

**Response (`201 Created`)**:
```json
{
  "message": "Sensor data recorded successfully",
  "record_id": 1659,
  "data": {
    "id": 1659,
    "washroom_id": 1,
    "device_id": 1,
    "ir1_state": 0,
    "ir2_state": 0,
    "pir_state": 0,
    "people_count": 0,
    "occupancy_status": "VACANT",
    "timestamp": "2026-11-10T12:01:00.000000Z"
  }
}
```

**Error Responses**:
- `401 Unauthorized`: Missing or invalid `X-Device-Token`.
- `403 Forbidden`: Request attempted to target `washroom_id != 1`.
- `422 Unprocessable Entity`: Validation failure (e.g. `people_count: 0` with `occupancy_status: "OCCUPIED"`).
- `503 Service Unavailable`: Server `LEGACY_DEVICE_TOKEN` unconfigured or no active legacy device found.

---

### C. Register Device Geographical Location (Authenticated)
`POST /api/devices/location`

**Headers**:
```http
X-Device-Token: YOUR_DEVICE_TOKEN
Content-Type: application/json
```

**Request Body**:
```json
{
  "latitude": 18.5204,
  "longitude": 73.8567,
  "altitude_m": 560.0,
  "hdop": 1.2,
  "satellites": 8
}
```

> **Validation Constraints**:
> `latitude` must be between -90.0 and 90.0; `longitude` between -180.0 and 180.0; `hdop` must be $\le 3.5$; `satellites` must be $\ge 4$. Null Island coordinates `(0.0, 0.0)` are rejected with `422 Unprocessable Entity`.

**Response (`200 OK` - Initial Registration)**:
```json
{
  "device_id": 1,
  "device_uid": "ESP32-PRIMARY-DEVICE",
  "washroom_id": 1,
  "washroom_name": "Primary Washroom",
  "latitude": 18.5204,
  "longitude": 73.8567,
  "coordinates_updated": true,
  "status": "REGISTERED",
  "timestamp": "2026-11-10T12:02:00.000000Z"
}
```

**Response (`200 OK` - Subsequent Call / Immutable Lock)**:
```json
{
  "device_id": 1,
  "device_uid": "ESP32-PRIMARY-DEVICE",
  "washroom_id": 1,
  "washroom_name": "Primary Washroom",
  "latitude": 18.5204,
  "longitude": 73.8567,
  "coordinates_updated": false,
  "status": "ALREADY_REGISTERED",
  "timestamp": "2026-11-10T12:05:00.000000Z"
}
```

**Error Responses**:
- `401 Unauthorized`: Missing or invalid `X-Device-Token`.
- `409 Conflict`: Washroom coordinates are in an inconsistent database state (one populated, one NULL) or device is unassigned.
- `422 Unprocessable Entity`: HDOP $> 3.5$, satellites $< 4$, or Null Island coordinates.

---

### D. Current Status
`GET /api/status?washroom_id=1`

**Query Parameters**:
- `washroom_id` (optional, integer, default: `1`)

**Response (`200 OK`)**:
```json
{
  "washroom_id": 1,
  "washroom_name": "Primary Washroom",
  "occupancy_status": "VACANT",
  "people_count": 0,
  "esp32_connected": true,
  "last_updated": "2026-11-10T12:01:00.000000Z"
}
```

---

### E. AI Rush Prediction
`GET /api/prediction?washroom_id=1&allow_stale=false`

**Query Parameters**:
- `washroom_id` (optional, integer, default: `1`)
- `allow_stale` (optional, boolean, default: `false`)

**Response (`200 OK` - Success)**:
```json
{
  "washroom_id": 1,
  "washroom_name": "Primary Washroom",
  "predicted_rush": "LOW",
  "predicted_rush_level": "LOW",
  "prediction_status": "SUCCESS",
  "prediction_timestamp": "2026-11-10T12:02:30.000000Z",
  "current_occupancy": 0,
  "occupancy_percent": 0.0,
  "capacity": 5,
  "probabilities": {
    "LOW": 0.85,
    "MEDIUM": 0.12,
    "HIGH": 0.03
  },
  "features_used": {
    "day_of_week": 1,
    "is_weekend": 0,
    "hour": 12,
    "capacity": 5,
    "current_occupancy": 0,
    "occupancy_percent": 0.0,
    "entries_5min": 0,
    "exits_5min": 0,
    "net_flow_5min": 0
  },
  "model_status": "LOADED",
  "note": null
}
```

---

### F. Telemetry History
`GET /api/history?washroom_id=1&limit=5&offset=0`

**Query Parameters**:
- `washroom_id` (optional, integer, default: `1`)
- `limit` (optional, integer, default: `50`, min: `1`, max: `500`)
- `offset` (optional, integer, default: `0`)

**Response (`200 OK`)**:
```json
{
  "washroom_id": 1,
  "total": 1658,
  "count": 1,
  "records": [
    {
      "id": 1658,
      "washroom_id": 1,
      "device_id": 1,
      "ir1_state": 0,
      "ir2_state": 0,
      "pir_state": 0,
      "people_count": 0,
      "occupancy_status": "VACANT",
      "timestamp": "2026-11-10T12:00:00.000000Z"
    }
  ]
}
```

---

### G. Discover Nearby Washrooms
`GET /api/washrooms/nearby?latitude=18.5204&longitude=73.8567&radius_km=5.0&limit=10`

**Query Parameters**:
- `latitude` (required, float, `-90.0` to `90.0`)
- `longitude` (required, float, `-180.0` to `180.0`)
- `radius_km` (optional, float, default: `5.0`, min: `0.1`, max: `50.0`)
- `gender` (optional, string: `"MALE"`, `"FEMALE"`, `"UNISEX"`)
- `accessibility_required` (optional, boolean, default: `false`)
- `limit` (optional, integer, default: `10`, min: `1`, max: `50`)

**Response (`200 OK`)**:
```json
{
  "user_location": {
    "latitude": 18.5204,
    "longitude": 73.8567
  },
  "search_radius_km": 5.0,
  "total_found": 1,
  "washrooms": [
    {
      "washroom_id": 1,
      "slug": "primary-washroom",
      "name": "Primary Washroom",
      "building": "Main Facility",
      "floor": "1",
      "room_number": "101",
      "latitude": 18.5204,
      "longitude": 73.8567,
      "distance_km": 0.05,
      "gender_type": "UNISEX",
      "is_accessible": true,
      "capacity": 5,
      "has_hardware": true,
      "is_active": true,
      "occupancy_status": "VACANT",
      "people_count": 0,
      "esp32_connected": true,
      "last_updated": "2026-11-10T12:01:00.000000Z",
      "predicted_rush": "LOW",
      "predicted_rush_level": "LOW",
      "prediction_status": "SUCCESS",
      "rush_probabilities": {
        "LOW": 0.85,
        "MEDIUM": 0.12,
        "HIGH": 0.03
      },
      "cleanliness": {
        "rating": 4.5,
        "review_count": 12,
        "status_label": "Clean"
      },
      "recommendation_score": 92.4,
      "recommendation_rank": 1
    }
  ]
}
```

---

### H. Get Washroom Details
`GET /api/washrooms/{washroom_id}?user_lat=18.5204&user_lng=73.8567`

**Path Parameters**:
- `washroom_id` (required, integer)

**Query Parameters**:
- `user_lat` (optional, float)
- `user_lng` (optional, float)

**Response (`200 OK`)**:
```json
{
  "washroom_id": 1,
  "slug": "primary-washroom",
  "name": "Primary Washroom",
  "building": "Main Facility",
  "floor": "1",
  "room_number": "101",
  "latitude": 18.5204,
  "longitude": 73.8567,
  "distance_km": 0.05,
  "gender_type": "UNISEX",
  "is_accessible": true,
  "capacity": 5,
  "operating_status": "OPEN",
  "operating_hours": "06:00 - 22:00",
  "amenities": "{\"soap\": true, \"paper_towels\": true, \"mirror\": true}",
  "has_hardware": true,
  "is_active": true,
  "occupancy_status": "VACANT",
  "people_count": 0,
  "esp32_connected": true,
  "last_updated": "2026-11-10T12:01:00.000000Z",
  "predicted_rush": "LOW",
  "predicted_rush_level": "LOW",
  "prediction_status": "SUCCESS",
  "rush_probabilities": {
    "LOW": 0.85,
    "MEDIUM": 0.12,
    "HIGH": 0.03
  },
  "cleanliness": {
    "rating": 4.5,
    "review_count": 12,
    "status_label": "Clean"
  }
}
```

---

## 7. Interactive Documentation (Swagger & ReDoc)

When the server is running locally, access the interactive API explorers:

- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 8. Starting & Stopping the Server

### Starting the Server
```bash
# Using uvicorn CLI
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Or running the entrypoint directly
python main.py
```

> **Android Emulator Access**:
> The Android emulator connects to the host machine's backend at:
> `http://10.0.2.2:8000`

### Stopping the Server
Press `Ctrl + C` in the terminal session running Uvicorn.

---

## 9. Automated Testing

Execute the backend test suite using the project's virtual environment:

```bash
python test_backend.py
```

### Coverage Overview (45 Automated Tests)
- **Tests 1–4**: Model service initialization, 9-feature specification validation, and calibrated inference.
- **Tests 5–7**: SQLite database initialization, foreign key validation, and schema constraints.
- **Tests 8–12**: Telemetry persistence, occupancy calculations, live status, and history pagination.
- **Tests 13–14**: Live ML rush inference and peak rush level transitions.
- **Tests 15–18**: Multi-washroom telemetry scoping and cross-facility isolation.
- **Tests 19–24**: Feature extraction logic, stale telemetry handling, and rolling flow calculations.
- **Tests 25–35**: Spatial discovery bounding box queries, Haversine distance, and recommendation ranking.
- **Tests 36–43**: NEO-6M GPS location registration, Null Island rejection, and immutable coordinate lock.
- **Tests 44–45**: `X-Device-Token` authentication security, missing/invalid header rejection, and server-side fail-closed behavior (`503 Service Unavailable`).
