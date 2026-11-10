from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hmac
import logging
import os
from typing import Annotated, Optional
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from database import get_db, init_db
from features import (
    FeatureExtractionError,
    NoSensorDataError,
    StaleDataError,
    extract_features_from_db,
)
from geo import (
    calculate_recommendation_score,
    get_bounding_box,
    haversine_distance,
)
from model import (
    InvalidFeatureError,
    ModelNotLoadedError,
    ModelPredictionError,
    model_service,
)
from models import (
    CleanlinessRating,
    CleanlinessSummary,
    Device,
    DeviceLocationCreate,
    DeviceLocationResponse,
    HealthResponse,
    HistoryResponse,
    NearbyDiscoveryResponse,
    NearbyWashroomItem,
    PredictionResponse,
    RushProbabilities,
    SensorDataCreate,
    SensorDataOut,
    SensorDataResponse,
    SensorRecord,
    StatusResponse,
    UserCoordinates,
    Washroom,
    WashroomDetailResponse,
)

# Load environment configuration
load_dotenv()
# ==========================================
# Device Authentication
# ==========================================

def verify_device_token(x_device_token: Optional[str]) -> None:
    """Validate device authentication and fail closed if server configuration is missing."""

    expected_token = os.getenv("LEGACY_DEVICE_TOKEN")

    if not expected_token or not expected_token.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Device authentication is not configured on the server.",
        )

    if not x_device_token or not hmac.compare_digest(
        x_device_token, expected_token
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Device-Token header.",
        )

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("gottago-backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager: initializes the database tables and loads the ML model on startup."""
    logger.info("Initializing GottaGo SQLite database schema...")
    init_db()
    logger.info("Database schema initialized successfully.")

    logger.info("Loading trained rush prediction model...")
    model_loaded = model_service.load()
    if model_loaded:
        logger.info(
            f"Rush prediction model loaded successfully with {len(model_service.feature_names)} features: {model_service.feature_names}"
        )
    else:
        logger.warning(f"Rush prediction model could not be loaded: {model_service.load_error}")

    yield
    logger.info("GottaGo backend shutting down.")


app = FastAPI(
    title="GottaGo Backend API",
    description="Backend API for GottaGo smart washroom availability and rush prediction.",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS for Flutter mobile/web and development tools
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# Endpoints
# ==========================================

@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Service Health Check",
    tags=["System"],
)
def get_health() -> HealthResponse:
    """Returns server health, application name, and server UTC timestamp."""
    return HealthResponse(
        status="healthy",
        backend="GottaGo Backend",
        timestamp=datetime.now(timezone.utc),
    )


@app.post(
    "/api/sensor-data",
    response_model=SensorDataResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest Sensor Telemetry",
    tags=["Telemetry"],
)
def record_sensor_data(
    payload: SensorDataCreate,
    x_device_token: Annotated[
        Optional[str],
        Header(alias="X-Device-Token", description="Device authentication secret token"),
    ] = None,
    db: Session = Depends(get_db),
) -> SensorDataResponse:
    """
    Ingests authenticated sensor readings from the physical ESP32 (IR1, IR2, PIR), validated people count,
    and occupancy state. Automatically persists to the SQLite database.
    Authenticated legacy hardware telemetry is strictly mapped to active legacy Device #1 and Washroom #1.
    """
    # 1. Device authentication verification (fail-closed)
    verify_device_token(x_device_token)

    # 2. Security Check: Legacy hardware cannot target non-legacy washrooms
    if payload.washroom_id is not None and payload.washroom_id != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Legacy hardware telemetry is restricted to Washroom #1. Multi-washroom hardware requires dedicated device provisioning.",
        )

    # 2. Resolve active legacy hardware device
    legacy_device = (
        db.query(Device)
        .filter(Device.is_legacy == True, Device.status == "ACTIVE")
        .first()
    )
    if legacy_device is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No active legacy ESP32 hardware device is registered in the system.",
        )

    # 3. Verify target washroom exists and is active
    target_washroom_id = legacy_device.washroom_id or 1
    washroom = (
        db.query(Washroom)
        .filter(Washroom.id == target_washroom_id, Washroom.is_active == True)
        .first()
    )
    if washroom is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Target washroom #{target_washroom_id} for legacy sensor hardware is unavailable or inactive.",
        )

    # 4. Generate timestamp exclusively on backend using server UTC time
    timestamp = datetime.now(timezone.utc)

    try:
        record = SensorRecord(
            washroom_id=target_washroom_id,
            device_id=legacy_device.id,
            ir1_state=payload.ir1_state,
            ir2_state=payload.ir2_state,
            pir_state=payload.pir_state,
            people_count=payload.people_count,
            occupancy_status=payload.occupancy_status,
            timestamp=timestamp,
        )
        db.add(record)
        legacy_device.last_heartbeat = timestamp
        db.commit()
        db.refresh(record)

        logger.info(
            f"Sensor record #{record.id} stored for washroom #{record.washroom_id} (device #{record.device_id}): "
            f"status={record.occupancy_status}, count={record.people_count}"
        )
        return SensorDataResponse(
            message="Sensor data recorded successfully",
            record_id=record.id,
            data=SensorDataOut.model_validate(record),
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to persist sensor data: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist sensor record to the database.",
        )


@app.post(
    "/api/devices/location",
    response_model=DeviceLocationResponse,
    status_code=status.HTTP_200_OK,
    summary="Register Device Geographical Location",
    tags=["Hardware Devices"],
)
def register_device_location(
    payload: DeviceLocationCreate,
    x_device_token: Annotated[
        Optional[str],
        Header(alias="X-Device-Token", description="Device authentication secret token"),
    ] = None,
    db: Session = Depends(get_db),
) -> DeviceLocationResponse:
    """
    Registers the fixed geographical coordinates of the active legacy hardware device.
    - Authenticates caller using X-Device-Token against LEGACY_DEVICE_TOKEN.
    - Dynamically resolves the active legacy device (is_legacy=True, status='ACTIVE').
    - Validates washroom association from database.
    - Enforces immutable tri-state coordinate registration:
      * UNINITIALIZED (both coords NULL): registers new coordinates.
      * LOCKED (both coords populated): returns authoritative coordinates without overwriting.
      * INCONSISTENT (one NULL, one populated): returns HTTP 409 Conflict.
    - Returns authoritative database coordinates.
    """
    # 1. Authenticate device token (fail-closed verification)
    verify_device_token(x_device_token)

    # 2. Dynamically resolve active legacy device using actual ORM fields
    legacy_device = (
        db.query(Device)
        .filter(Device.is_legacy == True, Device.status == "ACTIVE")
        .first()
    )
    if legacy_device is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No active legacy ESP32 hardware device is registered in the system.",
        )

    # 3. Validate washroom association
    if legacy_device.washroom_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Active legacy device '{legacy_device.device_uid}' is not assigned to any washroom.",
        )

    washroom = (
        db.query(Washroom)
        .filter(Washroom.id == legacy_device.washroom_id, Washroom.is_active == True)
        .first()
    )
    if washroom is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Target washroom #{legacy_device.washroom_id} for legacy device is inactive or not found.",
        )

    # 4. Tri-state coordinate lock evaluation
    now_utc = datetime.now(timezone.utc)

    # Case C: Exactly one coordinate is populated (inconsistent state)
    if (washroom.latitude is None) ^ (washroom.longitude is None):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Inconsistent coordinates in database for Washroom #{washroom.id}: "
                f"latitude={washroom.latitude}, longitude={washroom.longitude}. "
                "Manual administrator intervention required."
            ),
        )

    # Case A: Both coordinates are NULL -> initial registration permitted
    if washroom.latitude is None and washroom.longitude is None:
        washroom.latitude = payload.latitude
        washroom.longitude = payload.longitude
        washroom.updated_at = now_utc
        legacy_device.last_heartbeat = now_utc
        db.commit()
        db.refresh(washroom)
        coordinates_updated = True
        reg_status = "REGISTERED"
        logger.info(
            f"Registered coordinates ({payload.latitude}, {payload.longitude}) for Washroom #{washroom.id} via Device #{legacy_device.id}"
        )

    # Case B: Both coordinates are already populated -> immutable lock, no overwrite
    else:
        legacy_device.last_heartbeat = now_utc
        db.commit()
        coordinates_updated = False
        reg_status = "ALREADY_REGISTERED"
        logger.info(
            f"Device #{legacy_device.id} attempted coordinate registration for Washroom #{washroom.id}, but coordinates are locked at ({washroom.latitude}, {washroom.longitude})"
        )

    return DeviceLocationResponse(
        device_id=legacy_device.id,
        device_uid=legacy_device.device_uid,
        washroom_id=washroom.id,
        washroom_name=washroom.name,
        latitude=washroom.latitude,
        longitude=washroom.longitude,
        coordinates_updated=coordinates_updated,
        status=reg_status,
        timestamp=now_utc,
    )



@app.get(
    "/api/status",
    response_model=StatusResponse,
    summary="Current Washroom Status",
    tags=["Telemetry"],
)
def get_current_status(
    washroom_id: Annotated[
        int,
        Query(ge=1, description="Washroom ID to inspect status"),
    ] = 1,
    db: Session = Depends(get_db),
) -> StatusResponse:
    """
    Retrieves the most recent washroom occupancy status from the database.
    Defaults to Washroom #1 for backward compatibility.
    """
    washroom = db.query(Washroom).filter(Washroom.id == washroom_id).first()
    if washroom is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Washroom #{washroom_id} not found.",
        )

    if not washroom.has_hardware:
        return StatusResponse(
            washroom_id=washroom.id,
            washroom_name=washroom.name,
            occupancy_status=washroom.manual_occupancy_override or "VACANT",
            people_count=0,
            esp32_connected=False,
            last_updated=None,
        )

    latest_record = (
        db.query(SensorRecord)
        .filter(SensorRecord.washroom_id == washroom_id)
        .order_by(SensorRecord.timestamp.desc(), SensorRecord.id.desc())
        .first()
    )

    if latest_record:
        # Determine if ESP32 is actively communicating (received within 35 seconds)
        now = datetime.now(timezone.utc)
        record_time = latest_record.timestamp
        if record_time and record_time.tzinfo is None:
            record_time = record_time.replace(tzinfo=timezone.utc)
        is_connected = bool(record_time and (now - record_time).total_seconds() <= 35)

        return StatusResponse(
            washroom_id=washroom.id,
            washroom_name=washroom.name,
            occupancy_status=latest_record.occupancy_status,
            people_count=latest_record.people_count,
            esp32_connected=is_connected,
            last_updated=latest_record.timestamp,
        )

    return StatusResponse(
        washroom_id=washroom.id,
        washroom_name=washroom.name,
        occupancy_status="VACANT",
        people_count=0,
        esp32_connected=False,
        last_updated=None,
    )


@app.get(
    "/api/prediction",
    response_model=PredictionResponse,
    summary="AI Washroom Rush Prediction",
    tags=["Analytics"],
)
def get_rush_prediction(
    washroom_id: Annotated[
        int,
        Query(ge=1, description="Washroom ID for rush prediction"),
    ] = 1,
    allow_stale: Annotated[
        bool,
        Query(
            description="If true, generates prediction using latest recorded telemetry even if older than 5 minutes",
        ),
    ] = False,
    db: Session = Depends(get_db),
) -> PredictionResponse:
    """
    Returns real machine-learning rush prediction (LOW, MEDIUM, HIGH)
    and class probabilities generated by the trained Random Forest model.
    Features are dynamically engineered from live SQLite sensor telemetry isolated per washroom.
    """
    now_utc = datetime.now(timezone.utc)

    # 1. Validate washroom existence
    washroom = db.query(Washroom).filter(Washroom.id == washroom_id).first()
    if washroom is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Washroom #{washroom_id} not found.",
        )

    # 2. Check if washroom has IoT hardware installed
    if not washroom.has_hardware:
        return PredictionResponse(
            washroom_id=washroom.id,
            washroom_name=washroom.name,
            predicted_rush="UNAVAILABLE",
            predicted_rush_level="UNAVAILABLE",
            prediction_status="UNAVAILABLE",
            prediction_timestamp=now_utc,
            current_occupancy=None,
            occupancy_percent=None,
            capacity=washroom.capacity,
            probabilities=None,
            features_used=None,
            model_status="LOADED" if model_service.is_loaded else "NOT_LOADED",
            note=f"Prediction unavailable: washroom #{washroom_id} ('{washroom.name}') has no IoT sensor hardware installed.",
        )

    # 3. Verify model is loaded
    if not model_service.is_loaded:
        model_service.load()
        if not model_service.is_loaded:
            return PredictionResponse(
                washroom_id=washroom.id,
                washroom_name=washroom.name,
                predicted_rush="UNAVAILABLE",
                predicted_rush_level="UNAVAILABLE",
                prediction_status="UNAVAILABLE",
                prediction_timestamp=now_utc,
                model_status="NOT_LOADED",
                note=f"Trained model is not available: {model_service.load_error or 'Model file missing'}",
            )

    # 4. Extract features from database isolated to this washroom
    try:
        features, meta = extract_features_from_db(
            db,
            washroom_id=washroom_id,
            capacity=washroom.capacity,
            allow_stale=allow_stale,
        )
    except NoSensorDataError as e:
        logger.warning(f"Prediction unavailable: {e}")
        return PredictionResponse(
            washroom_id=washroom.id,
            washroom_name=washroom.name,
            predicted_rush="UNAVAILABLE",
            predicted_rush_level="UNAVAILABLE",
            prediction_status="UNAVAILABLE",
            prediction_timestamp=now_utc,
            model_status="LOADED",
            note=str(e),
        )
    except StaleDataError as e:
        logger.info(f"Sensor data stale: {e}")
        return PredictionResponse(
            washroom_id=washroom.id,
            washroom_name=washroom.name,
            predicted_rush="UNAVAILABLE",
            predicted_rush_level="UNAVAILABLE",
            prediction_status="UNAVAILABLE",
            prediction_timestamp=now_utc,
            model_status="LOADED",
            note=str(e),
        )
    except FeatureExtractionError as e:
        logger.error(f"Feature calculation error: {e}")
        return PredictionResponse(
            washroom_id=washroom.id,
            washroom_name=washroom.name,
            predicted_rush="UNAVAILABLE",
            predicted_rush_level="UNAVAILABLE",
            prediction_status="ERROR",
            prediction_timestamp=now_utc,
            model_status="LOADED",
            note=f"Feature calculation error: {e}",
        )

    # 5. Execute inference using trained Random Forest
    try:
        pred_res = model_service.predict(features)
        predicted_rush = pred_res["predicted_rush"]
        probabilities = RushProbabilities(**pred_res["probabilities"])

        return PredictionResponse(
            washroom_id=washroom.id,
            washroom_name=washroom.name,
            predicted_rush=predicted_rush,
            predicted_rush_level=predicted_rush,
            prediction_status="SUCCESS",
            prediction_timestamp=now_utc,
            current_occupancy=features["current_occupancy"],
            occupancy_percent=features["occupancy_percent"],
            capacity=features["capacity"],
            probabilities=probabilities,
            features_used=pred_res["features_used"],
            model_status="LOADED",
            note="Prediction generated from real trained Random Forest model.",
        )
    except Exception as e:
        logger.error(f"Prediction failed: {e}", exc_info=True)
        return PredictionResponse(
            washroom_id=washroom.id,
            washroom_name=washroom.name,
            predicted_rush="UNAVAILABLE",
            predicted_rush_level="UNAVAILABLE",
            prediction_status="ERROR",
            prediction_timestamp=now_utc,
            model_status="LOADED",
            note=f"Prediction inference error: {e}",
        )


@app.get(
    "/api/history",
    response_model=HistoryResponse,
    summary="Recent Sensor Records",
    tags=["Telemetry"],
)
def get_sensor_history(
    washroom_id: Annotated[
        int,
        Query(ge=1, description="Washroom ID to retrieve history for"),
    ] = 1,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Number of recent records to retrieve (1-100)",
        ),
    ] = 10,
    db: Session = Depends(get_db),
) -> HistoryResponse:
    """Returns recent sensor records for the specified washroom, ordered by timestamp descending."""
    washroom = db.query(Washroom).filter(Washroom.id == washroom_id).first()
    if washroom is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Washroom #{washroom_id} not found.",
        )

    total = (
        db.query(SensorRecord)
        .filter(SensorRecord.washroom_id == washroom_id)
        .count()
    )
    records = (
        db.query(SensorRecord)
        .filter(SensorRecord.washroom_id == washroom_id)
        .order_by(SensorRecord.timestamp.desc(), SensorRecord.id.desc())
        .limit(limit)
        .all()
    )

    return HistoryResponse(
        washroom_id=washroom.id,
        total=total,
        count=len(records),
        records=[SensorDataOut.model_validate(r) for r in records],
    )


# ==========================================
# Discovery & Detail Helpers & Endpoints (Milestone 3A)
# ==========================================

def _resolve_washroom_live_state(db: Session, washroom: Washroom) -> dict:
    """
    Resolves live occupancy, connectivity, rush prediction, and cleanliness
    for a washroom, strictly honoring hardware-enabled vs hardware-less rules.
    """
    # 1. Cleanliness ratings summary
    ratings = (
        db.query(CleanlinessRating)
        .filter(CleanlinessRating.washroom_id == washroom.id)
        .all()
    )
    if ratings:
        avg_rating = round(sum(r.rating for r in ratings) / len(ratings), 1)
        cleanliness = CleanlinessSummary(
            rating=avg_rating,
            review_count=len(ratings),
            status_label=f"{avg_rating}/5.0",
        )
    else:
        cleanliness = CleanlinessSummary(
            rating=None,
            review_count=0,
            status_label="Not yet rated",
        )

    # 2. Hardware-less washroom: never invoke Random Forest model
    if not washroom.has_hardware:
        return {
            "occupancy_status": washroom.manual_occupancy_override or "VACANT",
            "people_count": 0,
            "esp32_connected": False,
            "last_updated": None,
            "predicted_rush": "UNAVAILABLE",
            "predicted_rush_level": "UNAVAILABLE",
            "prediction_status": "UNAVAILABLE",
            "probabilities": None,
            "cleanliness": cleanliness,
        }

    # 3. Hardware-enabled washroom: resolve latest sensor record
    latest_record = (
        db.query(SensorRecord)
        .filter(SensorRecord.washroom_id == washroom.id)
        .order_by(SensorRecord.timestamp.desc(), SensorRecord.id.desc())
        .first()
    )

    now_utc = datetime.now(timezone.utc)
    if latest_record:
        rec_time = latest_record.timestamp
        if rec_time and rec_time.tzinfo is None:
            rec_time = rec_time.replace(tzinfo=timezone.utc)
        connected = bool(rec_time and (now_utc - rec_time).total_seconds() <= 35)
        occ_status = latest_record.occupancy_status
        people_count = latest_record.people_count
        last_updated = latest_record.timestamp
    else:
        connected = False
        occ_status = "VACANT"
        people_count = 0
        last_updated = None

    # AI Rush Prediction
    predicted_rush = "UNAVAILABLE"
    predicted_rush_level = "UNAVAILABLE"
    prediction_status = "UNAVAILABLE"
    probabilities = None

    if model_service.is_loaded:
        try:
            features, _ = extract_features_from_db(
                db,
                washroom_id=washroom.id,
                capacity=washroom.capacity,
                allow_stale=False,
            )
            pred_res = model_service.predict(features)
            predicted_rush = pred_res["predicted_rush"]
            predicted_rush_level = pred_res["predicted_rush"]
            prediction_status = "SUCCESS"
            probabilities = RushProbabilities(**pred_res["probabilities"])
        except Exception:
            predicted_rush = "UNAVAILABLE"
            predicted_rush_level = "UNAVAILABLE"
            prediction_status = "UNAVAILABLE"
            probabilities = None

    return {
        "occupancy_status": occ_status,
        "people_count": people_count,
        "esp32_connected": connected,
        "last_updated": last_updated,
        "predicted_rush": predicted_rush,
        "predicted_rush_level": predicted_rush_level,
        "prediction_status": prediction_status,
        "probabilities": probabilities,
        "cleanliness": cleanliness,
    }


@app.get(
    "/api/washrooms/nearby",
    response_model=NearbyDiscoveryResponse,
    summary="Discover Nearby Washrooms",
    tags=["Discovery"],
)
def get_nearby_washrooms(
    latitude: Annotated[
        float,
        Query(ge=-90.0, le=90.0, description="User smartphone latitude"),
    ],
    longitude: Annotated[
        float,
        Query(ge=-180.0, le=180.0, description="User smartphone longitude"),
    ],
    radius_km: Annotated[
        float,
        Query(ge=0.1, le=50.0, description="Search radius in kilometers"),
    ] = 5.0,
    gender: Annotated[
        Optional[str],
        Query(description="Gender filter: MALE, FEMALE, UNISEX"),
    ] = None,
    accessibility_required: Annotated[
        bool,
        Query(description="Filter for wheelchair accessible facilities"),
    ] = False,
    limit: Annotated[
        int,
        Query(ge=1, le=50, description="Maximum number of washrooms returned"),
    ] = 10,
    db: Session = Depends(get_db),
) -> NearbyDiscoveryResponse:
    """
    Discovers active public washrooms within radius_km of the user's coordinates.
    Sorts results using multi-factor recommendation scoring (distance, occupancy, rush, connectivity).
    """
    # 1. Validate gender parameter if supplied
    gender_norm = None
    if gender is not None:
        gender_norm = gender.strip().upper()
        if gender_norm not in ("MALE", "FEMALE", "UNISEX"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid gender filter. Must be MALE, FEMALE, or UNISEX.",
            )

    # 2. Build base query for active washrooms with valid stored coordinates
    query = (
        db.query(Washroom)
        .filter(
            Washroom.is_active == True,
            Washroom.latitude.isnot(None),
            Washroom.longitude.isnot(None),
        )
    )

    # 3. Apply gender filtering (UNKNOWN gender is strictly excluded when filter is active)
    if gender_norm == "MALE":
        query = query.filter(Washroom.gender_type.in_(["MALE", "UNISEX"]))
    elif gender_norm == "FEMALE":
        query = query.filter(Washroom.gender_type.in_(["FEMALE", "UNISEX"]))
    elif gender_norm == "UNISEX":
        query = query.filter(Washroom.gender_type == "UNISEX")

    # 4. Apply accessibility filter (NULL or False is excluded when required)
    if accessibility_required:
        query = query.filter(Washroom.is_accessible == True)

    # 5. Safe bounding-box pre-filtering in SQL
    min_lat, max_lat, min_lon, max_lon = get_bounding_box(latitude, longitude, radius_km)
    query = query.filter(
        Washroom.latitude >= min_lat,
        Washroom.latitude <= max_lat,
        Washroom.longitude >= min_lon,
        Washroom.longitude <= max_lon,
    )

    candidates = query.all()

    # 6. Haversine distance, live enrichment, and recommendation scoring
    evaluated_items = []
    for w in candidates:
        dist = haversine_distance(latitude, longitude, w.latitude, w.longitude)
        if dist > radius_km:
            continue

        live_state = _resolve_washroom_live_state(db, w)
        score = calculate_recommendation_score(
            distance_km=dist,
            occupancy_status=live_state["occupancy_status"],
            rush_level=live_state["predicted_rush"],
            esp32_connected=live_state["esp32_connected"],
        )

        item = NearbyWashroomItem(
            washroom_id=w.id,
            slug=w.slug,
            name=w.name,
            building=w.building,
            floor=w.floor,
            room_number=w.room_number,
            latitude=w.latitude,
            longitude=w.longitude,
            distance_km=dist,
            gender_type=w.gender_type,
            is_accessible=w.is_accessible,
            capacity=w.capacity,
            has_hardware=w.has_hardware,
            is_active=w.is_active,
            occupancy_status=live_state["occupancy_status"],
            people_count=live_state["people_count"],
            esp32_connected=live_state["esp32_connected"],
            last_updated=live_state["last_updated"],
            predicted_rush=live_state["predicted_rush"],
            predicted_rush_level=live_state["predicted_rush_level"],
            prediction_status=live_state["prediction_status"],
            rush_probabilities=live_state["probabilities"],
            cleanliness=live_state["cleanliness"],
            recommendation_score=score,
            recommendation_rank=0,  # Assigned after sorting
        )
        evaluated_items.append(item)

    # 7. Sort: recommendation_score ASC, distance_km ASC, washroom_id ASC
    evaluated_items.sort(key=lambda x: (x.recommendation_score, x.distance_km, x.washroom_id))

    # 8. Limit and rank assignment
    final_items = evaluated_items[:limit]
    for idx, item in enumerate(final_items, start=1):
        item.recommendation_rank = idx

    return NearbyDiscoveryResponse(
        user_location=UserCoordinates(latitude=latitude, longitude=longitude),
        search_radius_km=radius_km,
        total_found=len(final_items),
        washrooms=final_items,
    )


@app.get(
    "/api/washrooms/{washroom_id}",
    response_model=WashroomDetailResponse,
    summary="Get Washroom Details",
    tags=["Discovery"],
)
def get_washroom_details(
    washroom_id: int,
    user_lat: Annotated[
        Optional[float],
        Query(ge=-90.0, le=90.0, description="Optional user latitude to calculate distance"),
    ] = None,
    user_lng: Annotated[
        Optional[float],
        Query(ge=-180.0, le=180.0, description="Optional user longitude to calculate distance"),
    ] = None,
    db: Session = Depends(get_db),
) -> WashroomDetailResponse:
    """
    Retrieves full details for a specific washroom, including metadata, live status,
    AI rush predictions, cleanliness summary, and distance if user coordinates are supplied.
    """
    washroom = db.query(Washroom).filter(Washroom.id == washroom_id).first()
    if washroom is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Washroom #{washroom_id} not found.",
        )

    # Calculate distance if both user coordinates and washroom coordinates are present
    distance_km = None
    if (
        user_lat is not None
        and user_lng is not None
        and washroom.latitude is not None
        and washroom.longitude is not None
    ):
        distance_km = haversine_distance(user_lat, user_lng, washroom.latitude, washroom.longitude)

    live_state = _resolve_washroom_live_state(db, washroom)

    return WashroomDetailResponse(
        washroom_id=washroom.id,
        slug=washroom.slug,
        name=washroom.name,
        building=washroom.building,
        floor=washroom.floor,
        room_number=washroom.room_number,
        latitude=washroom.latitude,
        longitude=washroom.longitude,
        distance_km=distance_km,
        gender_type=washroom.gender_type,
        is_accessible=washroom.is_accessible,
        capacity=washroom.capacity,
        operating_status=washroom.operating_status,
        operating_hours=washroom.operating_hours,
        amenities=washroom.amenities,
        has_hardware=washroom.has_hardware,
        is_active=washroom.is_active,
        occupancy_status=live_state["occupancy_status"],
        people_count=live_state["people_count"],
        esp32_connected=live_state["esp32_connected"],
        last_updated=live_state["last_updated"],
        predicted_rush=live_state["predicted_rush"],
        predicted_rush_level=live_state["predicted_rush_level"],
        prediction_status=live_state["prediction_status"],
        rush_probabilities=live_state["probabilities"],
        cleanliness=live_state["cleanliness"],
    )



if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    logger.info(f"Starting GottaGo development server on {host}:{port}")
    uvicorn.run("main:app", host=host, port=port, reload=True)
