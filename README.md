# GottaGo — Smart Public Washroom Discovery & Availability Platform

GottaGo is a full-stack, smart public washroom discovery, live occupancy monitoring, and AI rush prediction application. The platform pairs a modern Flutter mobile client with an asynchronous FastAPI backend and ESP32 IoT sensor units to provide real-time crowd insights and facility discovery.

---

## 1. Project Overview

- **Application Name**: GottaGo
- **Application ID**: `com.gottago.app`
- **Mobile Framework**: Flutter 3.47.9 (Channel stable, Dart 3.13.7)
- **Backend Framework**: FastAPI (Python 3.14+)
- **Machine Learning**: Scikit-learn Random Forest Classifier (`rush_model.pkl`)
- **Hardware Integration**: ESP32 Microcontroller with Dual IR, PIR, and NEO-6M GPS
- **Target Platform**: Android (API 35 / Android 15) & RESTful Web APIs
- **Design System**: Material 3

---

## 2. Core Implemented Features

### 📍 GPS-Based Nearby Discovery
- **Live Device Location**: Uses smartphone GPS (`geolocator`) to locate nearby washrooms; never falls back to hardcoded coordinates.
- **Smart Recommendation Ranking**: Ranks facilities using a multi-factor score balancing walking distance (45%), live occupancy (25%), AI rush level (15%), and sensor connectivity (15%).
- **Interactive Filters**: Filter by gender accessibility (`ALL`, `UNISEX`, `MALE`, `FEMALE`), wheelchair accessibility, search radius (0.1 km to 50 km), and maximum results.
- **Resilient Fallback UI**: Displays dedicated permission request banners, location service enablement prompts, and retry actions when GPS permissions are withheld.

### 🏢 Comprehensive Washroom Details
- **Facility Metadata**: Building name, floor, room number, operating hours, fees, and accessibility accommodations.
- **Cleanliness Summary**: Community ratings, review counts, and cleanliness status badges.
- **Map Navigation**: One-click directions launching native mapping applications via geo-coordinates.

### 🟢 Real-Time Occupancy & People Counting
- **Live Occupancy Cards**: Hero indicators displaying real-time `VACANT` or `OCCUPIED` states.
- **Bidirectional People Counting**: Tracks occupant headcounts inside the facility.
- **Hardware Connectivity Monitoring**: Real-time heartbeat tracking indicating whether physical ESP32 sensors are online (within 30 seconds).

### 🤖 Machine Learning Rush Prediction
- **Trained Random Forest Classifier**: Real-time crowd level classification (`LOW`, `MEDIUM`, `HIGH`) loaded from `backend/rush_model.pkl`.
- **Authoritative 9-Feature Schema**: Evaluates temporal patterns (`day_of_week`, `is_weekend`, `hour`), facility capacity, live occupancy percentage, and 5-minute crowd flow rates (`entries_5min`, `exits_5min`, `net_flow_5min`).
- **Calibrated Probabilities**: Surfaces percentage confidence for all rush classes.

### 🔒 Fail-Closed Device Authentication
- **Header Authentication**: Telemetry and GPS registration require `X-Device-Token` matching server-side `LEGACY_DEVICE_TOKEN` using constant-time comparison (`hmac.compare_digest`).
- **Immutable Coordinate Locking**: Prevents unauthorized coordinate tampering once initial GPS fix is registered.

---

## 3. Directory Architecture

```
GottaGo/
├── android/                    # Native Android host project (Kotlin & Gradle)
├── assets/                     # Static assets (system icons, illustrations)
│   ├── icons/
│   └── images/
├── backend/                    # FastAPI backend & Machine Learning service
│   ├── alembic/                # Alembic database migration scripts
│   ├── alembic.ini             # Alembic configuration
│   ├── database.py             # SQLAlchemy engine, session maker, and DB init
│   ├── features.json           # 9-feature specification metadata
│   ├── features.py             # Telemetry feature extraction logic
│   ├── geo.py                  # Haversine distance, bounding box, and scoring
│   ├── gottago.db              # SQLite production database
│   ├── main.py                 # FastAPI application, route handlers, and auth
│   ├── model.py                # ModelService loading rush_model.pkl
│   ├── models.py               # SQLAlchemy ORM and Pydantic validation schemas
│   ├── requirements.txt        # Backend Python dependencies
│   ├── rush_model.pkl          # Trained Random Forest classifier
│   └── test_backend.py         # 45 backend unit and integration tests
├── firmware/                   # IoT Microcontroller firmware
│   └── gottago_esp32/
│       ├── config.h            # Pinouts, Wi-Fi, and backend endpoints
│       ├── config.example.h    # Config template with placeholders
│       └── gottago_esp32.ino   # ESP32 sensing, counting, and telemetry sketch
├── lib/                        # Flutter cross-platform source code
│   ├── main.dart               # App entrypoint and Material 3 theme configuration
│   ├── models/                 # Domain data models (WashroomStatus, NearbyWashroom)
│   ├── screens/                # UI screens (Home, Nearby, Washroom Details, Main Nav)
│   ├── services/               # Typed API client (ApiService) and LocationService
│   ├── utils/                  # App colors, constants, and formatters
│   └── widgets/                # Reusable UI cards (Occupancy, Rush, People Count)
└── test/                       # Flutter unit, widget, and integration tests
    ├── live_integration_test.dart
    ├── nearby_discovery_test.dart
    └── widget_test.dart
```

---

## 4. Getting Started

### Prerequisites
- **Flutter SDK**: `>= 3.47.0`
- **Dart SDK**: `>= 3.13.0`
- **Python**: `>= 3.10`
- **Android Studio / Android SDK**: Platform API 35

---

### Step 1: Start the Backend Server

1. Navigate to the `backend` directory:
   ```bash
   cd backend
   ```

2. Create and activate a Python virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install backend dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure environment variables (create `.env` from template):
   ```bash
   cp .env.example .env
   ```
   *Edit `.env` to set `LEGACY_DEVICE_TOKEN=YOUR_SECRET_DEVICE_TOKEN`.*

5. Launch the backend server:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```
   *The server initializes `gottago.db` automatically and listens at `http://0.0.0.0:8000`.*

---

### Step 2: Run the Flutter Mobile App

1. In a new terminal, navigate to the project root:
   ```bash
   cd ..
   ```

2. Fetch Flutter dependencies:
   ```bash
   flutter pub get
   ```

3. Verify code health:
   ```bash
   flutter analyze
   ```

4. Launch the application on an Android emulator or connected device:
   ```bash
   flutter run
   ```
   > **Note on Emulator Network Routing**:
   > The Android emulator automatically communicates with the host machine's backend via `http://10.0.2.2:8000`, pre-configured in `lib/utils/constants.dart`.

---

## 5. Verification & Testing

### Backend Test Suite
Run all 45 automated backend tests (testing model inference, database isolation, geospatial queries, and device authentication):
```bash
python backend/test_backend.py
```

### Flutter Test Suite
Run all 18 automated widget and integration tests:
```bash
flutter test
```

---

## 6. Security & Configuration Best Practices

- **Never Commit Secrets**: Keep `.env`, device tokens, and Wi-Fi credentials out of version control.
- **Fail-Closed Hardware Authentication**: Hardware endpoints require a valid `X-Device-Token`. If `LEGACY_DEVICE_TOKEN` is unset on the backend, device endpoints respond with `503 Service Unavailable`.
- **Placeholders in Documentation**: Use placeholder values (`YOUR_DEVICE_TOKEN`, `YOUR_WIFI_SSID`) when creating configuration files.
