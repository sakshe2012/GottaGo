from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from database import Base


# ==========================================
# 1. SQLAlchemy ORM Models
# ==========================================

class User(Base):
    """User accounts for role-based access (Public User, Cleaner, Administrator)."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=True)
    role = Column(String(20), nullable=False, default="USER", index=True)  # USER, CLEANER, ADMIN
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(DateTime(timezone=True), nullable=True)


class Washroom(Base):
    """
    Washroom facility entity.
    Unverified physical attributes are explicitly NULL or 'UNKNOWN'.
    """
    __tablename__ = "washrooms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(150), nullable=False)

    # Location details (nullable until verified)
    building = Column(String(100), nullable=True)
    floor = Column(String(50), nullable=True)
    room_number = Column(String(50), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # Classification & Accessibility
    gender_type = Column(
        String(20),
        nullable=False,
        default="UNKNOWN",
        index=True,
    )  # 'UNKNOWN', 'MALE', 'FEMALE', 'UNISEX'
    is_accessible = Column(Boolean, nullable=True, default=None)  # NULL until physically verified

    # Capacity & Operational Status
    capacity = Column(Integer, nullable=True, default=None)  # NULL until verified; API falls back to env DEFAULT
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    is_demo = Column(Boolean, nullable=False, default=False)
    has_hardware = Column(Boolean, nullable=False, default=False, index=True)
    operating_status = Column(
        String(20),
        nullable=False,
        default="UNKNOWN",
    )  # 'UNKNOWN', 'OPEN', 'CLOSED', 'CLEANING', 'MAINTENANCE'
    manual_occupancy_override = Column(String(20), nullable=True)  # NULL, 'VACANT', 'OCCUPIED'
    operating_hours = Column(String(100), nullable=True)
    amenities = Column(Text, nullable=True)  # JSON-encoded dictionary

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(DateTime(timezone=True), nullable=True)


class Device(Base):
    """
    Hardware inventory. Multiple devices can belong to one washroom (no UNIQUE on washroom_id).
    Database-level partial unique index ensures at most ONE active legacy device exists.
    """
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    device_uid = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    api_key = Column(String(128), nullable=True, index=True)  # NULL for legacy device
    washroom_id = Column(
        Integer,
        ForeignKey("washrooms.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    status = Column(String(20), nullable=False, default="ACTIVE")  # ACTIVE, INACTIVE, REVOKED
    is_legacy = Column(Boolean, nullable=False, default=False)
    firmware_version = Column(String(30), nullable=True)
    ip_address = Column(String(45), nullable=True)
    last_heartbeat = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index(
            "uq_devices_active_legacy",
            "is_legacy",
            "status",
            unique=True,
            sqlite_where=text("is_legacy = 1 AND status = 'ACTIVE'"),
        ),
    )


class SensorRecord(Base):
    """
    Individual sensor telemetry observation.
    Extends existing table preserving all 1,658 production rows.
    """
    __tablename__ = "sensor_records"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    washroom_id = Column(
        Integer,
        ForeignKey("washrooms.id", ondelete="RESTRICT"),
        nullable=False,
        default=1,
    )
    device_id = Column(
        Integer,
        ForeignKey("devices.id", ondelete="SET NULL"),
        nullable=True,
        default=1,
        index=True,
    )
    ir1_state = Column(Integer, nullable=False, default=0)
    ir2_state = Column(Integer, nullable=False, default=0)
    pir_state = Column(Integer, nullable=False, default=0)
    people_count = Column(Integer, nullable=False, default=0)
    occupancy_status = Column(String(20), nullable=False, default="VACANT")
    timestamp = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    __table_args__ = (
        Index("ix_sensor_records_washroom_time", "washroom_id", "timestamp"),
    )


class CleanlinessRating(Base):
    """User cleanliness feedback and reported facility issues."""
    __tablename__ = "cleanliness_ratings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    washroom_id = Column(
        Integer,
        ForeignKey("washrooms.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    rating = Column(Integer, nullable=False)  # 1 to 5
    reported_issue = Column(String(50), nullable=True)
    comments = Column(Text, nullable=True)
    aspects = Column(Text, nullable=True)  # JSON-encoded
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


class MaintenanceLog(Base):
    """Janitorial and facility servicing logs."""
    __tablename__ = "maintenance_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    washroom_id = Column(
        Integer,
        ForeignKey("washrooms.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    staff_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action = Column(String(50), nullable=False)
    notes = Column(Text, nullable=True)
    completed_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


# ==========================================
# 2. Pydantic Validation Schemas
# ==========================================

class OccupancyEnum(str, Enum):
    VACANT = "VACANT"
    OCCUPIED = "OCCUPIED"


class SensorDataCreate(BaseModel):
    """Payload sent by ESP32 or telemetry ingestion clients."""
    ir1_state: int = Field(..., ge=0, le=1, description="IR1 beam sensor: 0 (clear) or 1 (triggered)")
    ir2_state: int = Field(..., ge=0, le=1, description="IR2 beam sensor: 0 (clear) or 1 (triggered)")
    pir_state: int = Field(..., ge=0, le=1, description="PIR motion sensor: 0 (no motion) or 1 (motion)")
    people_count: int = Field(..., ge=0, description="Current count of occupants (cannot be negative)")
    occupancy_status: str = Field(..., description="Occupancy label: VACANT or OCCUPIED")
    timestamp: Optional[datetime] = Field(
        default=None,
        description="Observation timestamp; defaults to current UTC time if omitted",
    )
    washroom_id: Optional[int] = Field(
        default=None,
        description="Target washroom ID; unauthenticated legacy requests cannot target washrooms other than 1",
        ge=1,
    )
    device_id: Optional[int] = Field(
        default=None,
        description="Sending device ID; unauthenticated requests cannot specify arbitrary device IDs",
        ge=1,
    )

    @field_validator("occupancy_status")
    @classmethod
    def validate_occupancy_label(cls, v: str) -> str:
        upper = v.strip().upper()
        if upper not in ("VACANT", "OCCUPIED"):
            raise ValueError("occupancy_status must be either 'VACANT' or 'OCCUPIED'")
        return upper

    @model_validator(mode="after")
    def validate_occupancy_consistency(self) -> "SensorDataCreate":
        """
        Enforce strict consistency:
        - people_count = 0 MUST correspond to VACANT
        - people_count > 0 MUST correspond to OCCUPIED
        """
        if self.people_count == 0 and self.occupancy_status != "VACANT":
            raise ValueError(
                "Inconsistent state: people_count is 0, so occupancy_status must be 'VACANT'."
            )
        if self.people_count > 0 and self.occupancy_status != "OCCUPIED":
            raise ValueError(
                f"Inconsistent state: people_count is {self.people_count}, so occupancy_status must be 'OCCUPIED'."
            )
        return self


class SensorDataOut(BaseModel):
    """Serialized sensor record returned to API clients."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    washroom_id: int = 1
    device_id: Optional[int] = 1
    ir1_state: int
    ir2_state: int
    pir_state: int
    people_count: int
    occupancy_status: str
    timestamp: datetime


class SensorDataResponse(BaseModel):
    """API response after successfully persisting a sensor record."""
    message: str
    record_id: int
    data: SensorDataOut


class HealthResponse(BaseModel):
    status: str
    backend: str
    timestamp: datetime


class StatusResponse(BaseModel):
    washroom_id: int = 1
    washroom_name: Optional[str] = None
    occupancy_status: str
    people_count: int
    esp32_connected: bool
    last_updated: Optional[datetime]


class RushProbabilities(BaseModel):
    LOW: float = Field(..., description="Probability of LOW rush (0.0 to 1.0)")
    MEDIUM: float = Field(..., description="Probability of MEDIUM rush (0.0 to 1.0)")
    HIGH: float = Field(..., description="Probability of HIGH rush (0.0 to 1.0)")


class PredictionResponse(BaseModel):
    washroom_id: int = 1
    washroom_name: Optional[str] = None
    predicted_rush: str = Field(..., description="Rush category: LOW, MEDIUM, HIGH, or UNAVAILABLE")
    predicted_rush_level: str = Field(..., description="Explicit rush level alias: LOW, MEDIUM, HIGH, or UNAVAILABLE")
    prediction_status: str = Field(..., description="Status: SUCCESS, UNAVAILABLE, or ERROR")
    prediction_timestamp: datetime = Field(..., description="UTC timestamp of the prediction")
    current_occupancy: Optional[int] = Field(None, description="Headcount inside washroom at time of prediction")
    occupancy_percent: Optional[float] = Field(None, description="Percentage of washroom capacity occupied")
    capacity: Optional[int] = Field(None, description="Total washroom stall capacity")
    probabilities: Optional[RushProbabilities] = Field(None, description="Probabilities for each rush category")
    features_used: Optional[dict[str, Any]] = Field(None, description="The 9 features used for ML inference")
    model_status: str = Field(..., description="Model state: LOADED, NOT_FOUND, or ERROR")
    note: Optional[str] = Field(None, description="Human-readable explanation or diagnostic note")


class HistoryResponse(BaseModel):
    washroom_id: int = 1
    total: int
    count: int
    records: List[SensorDataOut]


class CleanlinessSummary(BaseModel):
    rating: Optional[float] = Field(None, description="Average cleanliness rating (1.0 to 5.0) or None")
    review_count: int = Field(0, description="Total verified ratings submitted")
    status_label: str = Field("Not yet rated", description="Cleanliness label or 'Not yet rated'")


class UserCoordinates(BaseModel):
    latitude: float
    longitude: float


class NearbyWashroomItem(BaseModel):
    washroom_id: int
    slug: str
    name: str
    building: Optional[str] = None
    floor: Optional[str] = None
    room_number: Optional[str] = None
    latitude: float
    longitude: float
    distance_km: float
    gender_type: str
    is_accessible: Optional[bool] = None
    capacity: Optional[int] = None
    has_hardware: bool
    is_active: bool
    occupancy_status: str
    people_count: int
    esp32_connected: bool
    last_updated: Optional[datetime] = None
    predicted_rush: str
    predicted_rush_level: str
    prediction_status: str
    rush_probabilities: Optional[RushProbabilities] = None
    cleanliness: CleanlinessSummary
    recommendation_score: float
    recommendation_rank: int


class NearbyDiscoveryResponse(BaseModel):
    user_location: UserCoordinates
    search_radius_km: float
    total_found: int
    washrooms: List[NearbyWashroomItem]


class WashroomDetailResponse(BaseModel):
    washroom_id: int
    slug: str
    name: str
    building: Optional[str] = None
    floor: Optional[str] = None
    room_number: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    distance_km: Optional[float] = None
    gender_type: str
    is_accessible: Optional[bool] = None
    capacity: Optional[int] = None
    operating_status: str
    operating_hours: Optional[str] = None
    amenities: Optional[str] = None
    has_hardware: bool
    is_active: bool
    occupancy_status: str
    people_count: int
    esp32_connected: bool
    last_updated: Optional[datetime] = None
    predicted_rush: str
    predicted_rush_level: str
    prediction_status: str
    rush_probabilities: Optional[RushProbabilities] = None
    cleanliness: CleanlinessSummary


class DeviceLocationCreate(BaseModel):
    """
    Payload sent by device to register its fixed geographical location.
    Mandatory HDOP (<= 3.5) and satellite count (>= 4) guarantee 3D fix quality.
    """
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees")
    altitude_m: Optional[float] = Field(None, ge=-500.0, le=9000.0, description="Altitude in meters above sea level")
    hdop: float = Field(..., gt=0.0, le=3.5, description="Horizontal dilution of precision (must be <= 3.5)")
    satellites: int = Field(..., ge=4, le=50, description="Satellites tracked (minimum 4 for 3D fix)")

    @model_validator(mode="after")
    def validate_not_null_island(self) -> "DeviceLocationCreate":
        if abs(self.latitude) < 1e-7 and abs(self.longitude) < 1e-7:
            raise ValueError("Uninitialized GPS coordinates (0.0, 0.0) rejected.")
        return self


class DeviceLocationResponse(BaseModel):
    """
    Response returned upon coordinate registration or immutable lock confirmation.
    Returned coordinates are always the authoritative database coordinates.
    """
    device_id: int = Field(..., description="ID of the resolved hardware device")
    device_uid: str = Field(..., description="Unique hardware identifier")
    washroom_id: int = Field(..., description="Assigned washroom ID")
    washroom_name: str = Field(..., description="Assigned washroom name")
    latitude: float = Field(..., description="Authoritative washroom latitude")
    longitude: float = Field(..., description="Authoritative washroom longitude")
    coordinates_updated: bool = Field(..., description="True if coordinates were newly registered; False if locked")
    status: str = Field(..., description="Registration status: REGISTERED or ALREADY_REGISTERED")
    timestamp: datetime = Field(..., description="UTC timestamp of the operation")
