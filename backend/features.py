from datetime import datetime, timezone, timedelta
import logging
import os
from typing import Any, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from models import SensorRecord, Washroom

logger = logging.getLogger("gottago-features")

DEFAULT_CAPACITY = int(os.getenv("WASHROOM_CAPACITY", "5"))
DEFAULT_MAX_STALE_SECONDS = int(os.getenv("MAX_STALE_SECONDS", "300"))  # 5 minutes


class FeatureExtractionError(Exception):
    """Base class for feature calculation errors."""
    pass


class NoSensorDataError(FeatureExtractionError):
    """Raised when no sensor records exist in the database."""
    pass


class StaleDataError(FeatureExtractionError):
    """Raised when the latest sensor record exceeds the acceptable freshness limit."""
    pass


def extract_features_from_db(
    db: Session,
    washroom_id: int = 1,
    capacity: Optional[int] = None,
    allow_stale: bool = False,
    max_stale_seconds: int = DEFAULT_MAX_STALE_SECONDS,
    reference_time: Optional[datetime] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Extracts and computes the authoritative 9 features required by rush_model.pkl
    from historical sensor telemetry in SQLite, strictly isolated to the specified washroom.

    Authoritative 9-feature schema:
      1. day_of_week       (0=Monday ... 6=Sunday)
      2. is_weekend        (1 if day_of_week >= 5 else 0)
      3. hour              (0 to 23)
      4. capacity          (washroom stall capacity)
      5. current_occupancy (latest valid people_count)
      6. occupancy_percent ((current_occupancy / capacity) * 100.0)
      7. entries_5min      (sum of positive count increments in last 5 minutes)
      8. exits_5min        (sum of negative count decrements in last 5 minutes)
      9. net_flow_5min     (entries_5min - exits_5min)

    Returns:
        (features_dict, metadata_dict)
    """
    # 0. Resolve washroom capacity independently per facility
    resolved_capacity = capacity
    if resolved_capacity is None:
        washroom_row = db.query(Washroom).filter(Washroom.id == washroom_id).first()
        if washroom_row and washroom_row.capacity is not None:
            resolved_capacity = washroom_row.capacity

    washroom_capacity = resolved_capacity or DEFAULT_CAPACITY
    if washroom_capacity <= 0:
        raise FeatureExtractionError(f"Invalid capacity: {washroom_capacity}. Must be positive.")

    # 1. Fetch latest sensor observation for the specified washroom
    latest_record = (
        db.query(SensorRecord)
        .filter(SensorRecord.washroom_id == washroom_id)
        .order_by(SensorRecord.timestamp.desc(), SensorRecord.id.desc())
        .first()
    )

    if latest_record is None:
        raise NoSensorDataError(
            f"No sensor records exist in database for washroom #{washroom_id}. Cannot determine occupancy or rush features."
        )

    # 2. Time context
    now_utc = reference_time or datetime.now(timezone.utc)
    rec_time = latest_record.timestamp
    if rec_time.tzinfo is None:
        rec_time = rec_time.replace(tzinfo=timezone.utc)

    data_age_seconds = (now_utc - rec_time).total_seconds()
    is_stale = data_age_seconds > max_stale_seconds

    if is_stale and not allow_stale:
        raise StaleDataError(
            f"Sensor data is stale ({int(data_age_seconds)}s old, exceeds {max_stale_seconds}s limit). "
            f"ESP32 telemetry stream for washroom #{washroom_id} is offline or discontinued."
        )

    # 3. Local calendar/time features (derived from local time or reference_time)
    if reference_time:
        local_time = reference_time.astimezone() if reference_time.tzinfo else reference_time
    else:
        local_time = datetime.now()

    day_of_week = int(local_time.weekday())  # 0=Monday, 6=Sunday
    is_weekend = 1 if day_of_week in (5, 6) else 0
    hour = int(local_time.hour)

    # 4. Occupancy metrics
    current_occupancy = int(max(0, latest_record.people_count))
    occupancy_percent = round((current_occupancy / washroom_capacity) * 100.0, 2)

    # 5. 5-minute sliding window flow calculation strictly isolated by washroom_id
    anchor_time = rec_time if (is_stale and allow_stale) else now_utc
    window_start = anchor_time - timedelta(minutes=5)

    records_in_window = (
        db.query(SensorRecord)
        .filter(
            SensorRecord.washroom_id == washroom_id,
            SensorRecord.timestamp >= window_start,
            SensorRecord.timestamp <= anchor_time,
        )
        .order_by(SensorRecord.timestamp.asc(), SensorRecord.id.asc())
        .all()
    )

    # Fetch baseline record immediately before the window for this specific washroom
    baseline_record = (
        db.query(SensorRecord)
        .filter(
            SensorRecord.washroom_id == washroom_id,
            SensorRecord.timestamp < window_start,
        )
        .order_by(SensorRecord.timestamp.desc(), SensorRecord.id.desc())
        .first()
    )

    chronological_chain = ([baseline_record] if baseline_record else []) + records_in_window

    entries_5min = 0
    exits_5min = 0

    if len(chronological_chain) >= 2:
        for i in range(1, len(chronological_chain)):
            prev_cnt = chronological_chain[i - 1].people_count
            curr_cnt = chronological_chain[i].people_count
            delta = curr_cnt - prev_cnt
            if delta > 0:
                entries_5min += delta
            elif delta < 0:
                exits_5min += abs(delta)

    net_flow_5min = entries_5min - exits_5min

    features = {
        "day_of_week": day_of_week,
        "is_weekend": is_weekend,
        "hour": hour,
        "capacity": washroom_capacity,
        "current_occupancy": current_occupancy,
        "occupancy_percent": occupancy_percent,
        "entries_5min": entries_5min,
        "exits_5min": exits_5min,
        "net_flow_5min": net_flow_5min,
    }

    metadata = {
        "washroom_id": washroom_id,
        "latest_record_id": latest_record.id,
        "latest_record_timestamp": rec_time.isoformat(),
        "data_age_seconds": round(data_age_seconds, 1),
        "is_stale": is_stale,
        "records_in_window": len(records_in_window),
        "window_start": window_start.isoformat(),
        "window_end": anchor_time.isoformat(),
    }

    return features, metadata
