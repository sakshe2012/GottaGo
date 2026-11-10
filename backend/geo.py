"""
Geographical calculations and spatial utilities for GottaGo.
Implements the spherical Haversine formula, coordinate range validation,
bounding-box pre-filtering, and multi-factor recommendation scoring.
"""

from datetime import datetime, timezone
import math
from typing import Optional, Tuple

EARTH_RADIUS_KM: float = 6371.0


def validate_coordinates(latitude: float, longitude: float) -> None:
    """Validates that latitude and longitude fall within legal WGS84 spherical bounds."""
    if not isinstance(latitude, (int, float)) or math.isnan(latitude) or math.isinf(latitude):
        raise ValueError("Latitude must be a valid finite number.")
    if not isinstance(longitude, (int, float)) or math.isnan(longitude) or math.isinf(longitude):
        raise ValueError("Longitude must be a valid finite number.")
    if not (-90.0 <= latitude <= 90.0):
        raise ValueError(f"Latitude {latitude} out of bounds. Must be between -90.0 and +90.0 degrees.")
    if not (-180.0 <= longitude <= 180.0):
        raise ValueError(f"Longitude {longitude} out of bounds. Must be between -180.0 and +180.0 degrees.")


def haversine_distance(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Computes great-circle distance in kilometers between two GPS coordinates using the Haversine formula.

    Returns:
        Distance in kilometers rounded to 3 decimal places.
    Raises:
        ValueError: If any coordinate is out of bounds.
    """
    validate_coordinates(lat1, lon1)
    validate_coordinates(lat2, lon2)

    # Edge case: Identical coordinates
    if lat1 == lat2 and lon1 == lon2:
        return 0.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    # Clamp to prevent numerical domain errors near antipodes
    a = min(1.0, max(0.0, a))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    return round(EARTH_RADIUS_KM * c, 3)


def get_bounding_box(
    latitude: float,
    longitude: float,
    radius_km: float,
) -> Tuple[float, float, float, float]:
    """
    Computes a rectangular bounding box (min_lat, max_lat, min_lon, max_lon)
    surrounding a coordinate at distance radius_km.
    Used for safe SQL-side candidate pre-filtering.
    """
    validate_coordinates(latitude, longitude)
    if radius_km <= 0:
        raise ValueError("Radius must be strictly positive.")

    # 1 degree latitude ~= 111.0 km
    delta_lat = radius_km / 111.0
    min_lat = max(-90.0, latitude - delta_lat)
    max_lat = min(90.0, latitude + delta_lat)

    # 1 degree longitude ~= 111.0 * cos(lat) km
    cos_lat = math.cos(math.radians(latitude))
    if abs(cos_lat) > 1e-6:
        delta_lon = radius_km / (111.0 * abs(cos_lat))
    else:
        delta_lon = 180.0  # Near poles, encompass full longitude range

    min_lon = max(-180.0, longitude - delta_lon)
    max_lon = min(180.0, longitude + delta_lon)

    return (min_lat, max_lat, min_lon, max_lon)


def calculate_recommendation_score(
    distance_km: float,
    occupancy_status: str,
    rush_level: str,
    esp32_connected: bool,
) -> float:
    """
    Computes the multi-criteria recommendation ranking score.
    Lower score indicates a better recommendation.

    Weights:
      - Distance weight: 1.0
      - Occupancy weight: 1.5
      - Rush weight: 1.0
      - Connectivity weight: 0.5

    Penalties:
      - Occupancy:
          VACANT -> 0.0
          OCCUPIED -> 2.0
          UNKNOWN -> 0.5
      - Rush:
          LOW -> 0.0
          MEDIUM -> 1.0
          HIGH -> 3.0
          UNAVAILABLE -> 0.8
      - Connectivity:
          Connected -> 0.0
          Disconnected -> 0.5
    """
    # 1. Distance penalty
    dist_penalty = max(0.0, distance_km)

    # 2. Occupancy penalty
    occ_upper = (occupancy_status or "UNKNOWN").strip().upper()
    if occ_upper == "VACANT":
        occ_penalty = 0.0
    elif occ_upper == "OCCUPIED":
        occ_penalty = 2.0
    else:
        occ_penalty = 0.5

    # 3. Rush penalty
    rush_upper = (rush_level or "UNAVAILABLE").strip().upper()
    if rush_upper == "LOW":
        rush_penalty = 0.0
    elif rush_upper == "MEDIUM":
        rush_penalty = 1.0
    elif rush_upper == "HIGH":
        rush_penalty = 3.0
    else:
        rush_penalty = 0.8

    # 4. Connectivity penalty
    conn_penalty = 0.0 if esp32_connected else 0.5

    score = (
        1.0 * dist_penalty
        + 1.5 * occ_penalty
        + 1.0 * rush_penalty
        + 0.5 * conn_penalty
    )
    return round(score, 4)
