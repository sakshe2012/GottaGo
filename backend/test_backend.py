from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import os
from pathlib import Path
import sys
import unittest
from fastapi.testclient import TestClient

# Ensure backend directory is in sys.path regardless of execution directory
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Set temporary test database with absolute path inside backend/ before importing app
TEST_DB_FILE = BACKEND_DIR / "test_gottago.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_FILE}"

# Dedicated test-only device authentication token (set before importing main app)
TEST_DEVICE_TOKEN = "test-only-gottago-device-token"
os.environ["LEGACY_DEVICE_TOKEN"] = TEST_DEVICE_TOKEN

from database import Base, engine, SessionLocal
from features import extract_features_from_db
from geo import haversine_distance, calculate_recommendation_score
from main import app
from model import model_service, EXPECTED_FEATURES, InvalidFeatureError
from models import SensorRecord, Washroom, Device


class TestGottaGoBackendAndML(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Using TestClient as a context manager triggers FastAPI lifespan startup
        # which automatically runs init_db() and model_service.load().
        cls._client_cm = TestClient(app)
        cls.client = cls._client_cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        try:
            if hasattr(cls, "_client_cm") and cls._client_cm:
                cls._client_cm.__exit__(None, None, None)
        finally:
            Base.metadata.drop_all(bind=engine)
            engine.dispose()
            # Safety check: ensure we only unlink the test database file
            if TEST_DB_FILE.exists() and TEST_DB_FILE.name == "test_gottago.db":
                TEST_DB_FILE.unlink(missing_ok=True)

    # ========================================================
    # 1. Model Service Unit Tests
    # ========================================================

    def test_01_model_loaded_successfully(self):
        """1. Verify that the trained model loads successfully."""
        self.assertTrue(model_service.is_loaded)
        self.assertIsNotNone(model_service.model)
        self.assertIsNone(model_service.load_error)

    def test_02_feature_names_and_ordering(self):
        """2. Verify that feature names and exact order match the 9-feature specification."""
        self.assertEqual(len(model_service.feature_names), 9)
        self.assertEqual(
            model_service.feature_names,
            [
                "day_of_week",
                "is_weekend",
                "hour",
                "capacity",
                "current_occupancy",
                "occupancy_percent",
                "entries_5min",
                "exits_5min",
                "net_flow_5min",
            ],
        )

    def test_03_classes_and_probability_ordering(self):
        """3. Verify trained class labels and probability mapping."""
        self.assertEqual(set(model_service.classes), {"LOW", "MEDIUM", "HIGH"})
        # Confirm model's internal class order
        self.assertEqual(model_service.classes, ["HIGH", "LOW", "MEDIUM"])

    def test_04_model_inference_low_and_high(self):
        """4. Verify model inference returns valid labels and calibrated probabilities."""
        # Low rush scenario
        low_input = {
            "day_of_week": 1,
            "is_weekend": 0,
            "hour": 6,
            "capacity": 5,
            "current_occupancy": 0,
            "occupancy_percent": 0.0,
            "entries_5min": 0,
            "exits_5min": 0,
            "net_flow_5min": 0,
        }
        res_low = model_service.predict(low_input)
        self.assertIn(res_low["predicted_rush"], ["LOW", "MEDIUM", "HIGH"])
        self.assertEqual(res_low["predicted_rush"], "LOW")
        self.assertIn("LOW", res_low["probabilities"])
        self.assertIn("MEDIUM", res_low["probabilities"])
        self.assertIn("HIGH", res_low["probabilities"])
        prob_sum = sum(res_low["probabilities"].values())
        self.assertAlmostEqual(prob_sum, 1.0, places=2)

        # High rush scenario
        high_input = {
            "day_of_week": 4,
            "is_weekend": 0,
            "hour": 13,
            "capacity": 5,
            "current_occupancy": 5,
            "occupancy_percent": 100.0,
            "entries_5min": 8,
            "exits_5min": 2,
            "net_flow_5min": 6,
        }
        res_high = model_service.predict(high_input)
        self.assertEqual(res_high["predicted_rush"], "HIGH")
        self.assertGreater(res_high["probabilities"]["HIGH"], 0.5)

    def test_05_missing_features_safety(self):
        """5. Verify that missing features are caught safely and raise InvalidFeatureError."""
        incomplete_input = {
            "day_of_week": 1,
            "is_weekend": 0,
            # hour missing
            "capacity": 5,
            "current_occupancy": 1,
            "occupancy_percent": 20.0,
            "entries_5min": 1,
            "exits_5min": 0,
            "net_flow_5min": 1,
        }
        with self.assertRaises(InvalidFeatureError):
            model_service.predict(incomplete_input)

    # ========================================================
    # 2. Existing Endpoints Verification
    # ========================================================

    def test_06_health_check(self):
        """6. Test GET /health returns valid health and timestamp."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["backend"], "GottaGo Backend")
        self.assertIn("timestamp", data)

    def test_07_initial_status_empty(self):
        """7. Test GET /api/status before records exist."""
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["occupancy_status"], "VACANT")
        self.assertEqual(data["people_count"], 0)
        self.assertFalse(data["esp32_connected"])

    def test_08_post_valid_sensor_data_vacant(self):
        """8. Test POST /api/sensor-data with valid VACANT data."""
        payload = {
            "ir1_state": 0,
            "ir2_state": 0,
            "pir_state": 0,
            "people_count": 0,
            "occupancy_status": "VACANT",
        }
        response = self.client.post(
            "/api/sensor-data",
            headers={"X-Device-Token": TEST_DEVICE_TOKEN},
            json=payload,
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["message"], "Sensor data recorded successfully")
        self.assertEqual(data["data"]["people_count"], 0)
        self.assertEqual(data["data"]["occupancy_status"], "VACANT")
        self.assertGreater(data["record_id"], 0)

    def test_09_post_valid_sensor_data_occupied(self):
        """9. Test POST /api/sensor-data with valid OCCUPIED data."""
        payload = {
            "ir1_state": 1,
            "ir2_state": 0,
            "pir_state": 1,
            "people_count": 1,
            "occupancy_status": "OCCUPIED",
        }
        response = self.client.post(
            "/api/sensor-data",
            headers={"X-Device-Token": TEST_DEVICE_TOKEN},
            json=payload,
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["data"]["people_count"], 1)
        self.assertEqual(data["data"]["occupancy_status"], "OCCUPIED")

    def test_10_post_validation_rules(self):
        """10. Test validation on negative count and state inconsistency."""
        # Negative count (fails schema validation when authenticated)
        res1 = self.client.post(
            "/api/sensor-data",
            headers={"X-Device-Token": TEST_DEVICE_TOKEN},
            json={"ir1_state": 0, "ir2_state": 0, "pir_state": 0, "people_count": -1, "occupancy_status": "VACANT"},
        )
        self.assertEqual(res1.status_code, 422)

        # Inconsistent count=0 with OCCUPIED (fails schema validation when authenticated)
        res2 = self.client.post(
            "/api/sensor-data",
            headers={"X-Device-Token": TEST_DEVICE_TOKEN},
            json={"ir1_state": 0, "ir2_state": 0, "pir_state": 0, "people_count": 0, "occupancy_status": "OCCUPIED"},
        )
        self.assertEqual(res2.status_code, 422)

    def test_11_get_status_reflects_latest_and_heartbeat(self):
        """11. Test GET /api/status accurately reflects latest stored record and heartbeat."""
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["occupancy_status"], "OCCUPIED")
        self.assertEqual(data["people_count"], 1)
        # Because we just posted a record seconds ago, esp32_connected should be True!
        self.assertTrue(data["esp32_connected"])
        self.assertIsNotNone(data["last_updated"])

    def test_12_get_history(self):
        """12. Test GET /api/history returns recorded entries."""
        response = self.client.get("/api/history?limit=10")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["count"], 2)
        self.assertEqual(len(data["records"]), 2)
        self.assertEqual(data["records"][0]["occupancy_status"], "OCCUPIED")
        self.assertEqual(data["records"][1]["occupancy_status"], "VACANT")

    # ========================================================
    # 3. Real Prediction Endpoint Integration Tests
    # ========================================================

    def test_13_get_prediction_real_inference_success(self):
        """13. Test GET /api/prediction returns real ML inference when fresh data is present."""
        response = self.client.get("/api/prediction")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["prediction_status"], "SUCCESS")
        self.assertIn(data["predicted_rush"], ["LOW", "MEDIUM", "HIGH"])
        self.assertEqual(data["predicted_rush"], data["predicted_rush_level"])
        self.assertEqual(data["model_status"], "LOADED")
        self.assertIsNotNone(data["prediction_timestamp"])

        # Check occupancy features
        self.assertEqual(data["current_occupancy"], 1)
        self.assertEqual(data["capacity"], 5)
        self.assertEqual(data["occupancy_percent"], 20.0)

        # Check probabilities
        self.assertIsNotNone(data["probabilities"])
        self.assertIn("LOW", data["probabilities"])
        self.assertIn("MEDIUM", data["probabilities"])
        self.assertIn("HIGH", data["probabilities"])
        total_p = sum(data["probabilities"].values())
        self.assertAlmostEqual(total_p, 1.0, places=2)

        # Check features used
        feats = data["features_used"]
        self.assertIsNotNone(feats)
        for expected_col in EXPECTED_FEATURES:
            self.assertIn(expected_col, feats)

    def test_14_get_prediction_high_rush_simulation(self):
        """14. Test GET /api/prediction dynamically updates to HIGH rush under peak load."""
        # Ingest 4 more people to reach capacity = 5
        self.client.post(
            "/api/sensor-data",
            headers={"X-Device-Token": TEST_DEVICE_TOKEN},
            json={"ir1_state": 1, "ir2_state": 1, "pir_state": 1, "people_count": 5, "occupancy_status": "OCCUPIED"},
        )
        response = self.client.get("/api/prediction")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["prediction_status"], "SUCCESS")
        self.assertEqual(data["predicted_rush"], "HIGH")
        self.assertEqual(data["current_occupancy"], 5)
        self.assertEqual(data["occupancy_percent"], 100.0)
        self.assertGreater(data["probabilities"]["HIGH"], 0.5)

    # ========================================================
    # 4. Milestone 2 Multi-Washroom Telemetry & ML Isolation
    # ========================================================

    def test_15_legacy_telemetry_defaults_to_washroom_1(self):
        """15. Test authenticated legacy ESP32 payload routes to active Device #1 and Washroom #1."""
        payload = {
            "ir1_state": 0,
            "ir2_state": 0,
            "pir_state": 0,
            "people_count": 0,
            "occupancy_status": "VACANT",
        }
        response = self.client.post(
            "/api/sensor-data",
            headers={"X-Device-Token": TEST_DEVICE_TOKEN},
            json=payload,
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["data"]["washroom_id"], 1)
        self.assertEqual(data["data"]["device_id"], 1)

    def test_16_legacy_hardware_non_legacy_washroom_rejected(self):
        """16. Test valid token targeting non-legacy washroom is rejected with 403."""
        payload = {
            "ir1_state": 1,
            "ir2_state": 0,
            "pir_state": 1,
            "people_count": 1,
            "occupancy_status": "OCCUPIED",
            "washroom_id": 2,
        }
        response = self.client.post(
            "/api/sensor-data",
            headers={"X-Device-Token": TEST_DEVICE_TOKEN},
            json=payload,
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("Legacy hardware telemetry is restricted to Washroom #1", response.json()["detail"])

    def test_17_post_sensor_data_missing_legacy_device_503(self):
        """17. Test telemetry ingestion returns 503 if registered legacy hardware is unavailable."""
        with SessionLocal() as db:
            dev = db.query(Device).filter(Device.id == 1).first()
            original_status = dev.status
            dev.status = "INACTIVE"
            db.commit()

        try:
            response = self.client.post(
                "/api/sensor-data",
                headers={"X-Device-Token": TEST_DEVICE_TOKEN},
                json={"ir1_state": 0, "ir2_state": 0, "pir_state": 0, "people_count": 0, "occupancy_status": "VACANT"},
            )
            self.assertEqual(response.status_code, 503)
            self.assertIn("No active legacy ESP32 hardware device", response.json()["detail"])
        finally:
            with SessionLocal() as db:
                dev = db.query(Device).filter(Device.id == 1).first()
                dev.status = original_status
                db.commit()

    def test_18_status_isolated_between_washrooms(self):
        """18. Test GET /api/status returns isolated occupancy states per washroom."""
        # Seed Washroom #2 with hardware in test database
        with SessionLocal() as db:
            if not db.query(Washroom).filter_by(id=2).first():
                w2 = Washroom(
                    id=2,
                    slug="secondary-washroom",
                    name="Secondary Washroom",
                    has_hardware=True,
                    is_active=True,
                    capacity=5,
                )
                db.add(w2)
            # Add a sensor record directly for Washroom 2 with people_count = 0 (VACANT)
            rec2 = SensorRecord(
                washroom_id=2,
                device_id=1,
                ir1_state=0,
                ir2_state=0,
                pir_state=0,
                people_count=0,
                occupancy_status="VACANT",
                timestamp=datetime.now(timezone.utc),
            )
            db.add(rec2)
            db.commit()

        # Query Washroom 1 (people_count = 0 from test_15)
        res1 = self.client.get("/api/status?washroom_id=1")
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.json()["washroom_id"], 1)

        # Ingest occupancy into Washroom 1 to ensure distinct states
        self.client.post(
            "/api/sensor-data",
            headers={"X-Device-Token": TEST_DEVICE_TOKEN},
            json={"ir1_state": 1, "ir2_state": 1, "pir_state": 1, "people_count": 4, "occupancy_status": "OCCUPIED"},
        )
        res1_occ = self.client.get("/api/status?washroom_id=1")
        self.assertEqual(res1_occ.status_code, 200)
        self.assertEqual(res1_occ.json()["people_count"], 4)
        self.assertEqual(res1_occ.json()["occupancy_status"], "OCCUPIED")

        # Query Washroom 2 - MUST remain 0 / VACANT
        res2 = self.client.get("/api/status?washroom_id=2")
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.json()["washroom_id"], 2)
        self.assertEqual(res2.json()["people_count"], 0)
        self.assertEqual(res2.json()["occupancy_status"], "VACANT")

    def test_19_history_isolated_between_washrooms(self):
        """19. Test GET /api/history strictly returns records belonging to queried washroom."""
        res_h1 = self.client.get("/api/history?washroom_id=1&limit=50")
        self.assertEqual(res_h1.status_code, 200)
        data_h1 = res_h1.json()
        self.assertEqual(data_h1["washroom_id"], 1)
        for r in data_h1["records"]:
            self.assertEqual(r["washroom_id"], 1)

        res_h2 = self.client.get("/api/history?washroom_id=2&limit=50")
        self.assertEqual(res_h2.status_code, 200)
        data_h2 = res_h2.json()
        self.assertEqual(data_h2["washroom_id"], 2)
        for r in data_h2["records"]:
            self.assertEqual(r["washroom_id"], 2)

    def test_20_bidirectional_ml_isolation_reference_time(self):
        """20. Test deterministic bidirectional ML feature isolation using fixed reference timestamps."""
        t0 = datetime(2026, 11, 6, 12, 0, 0, tzinfo=timezone.utc)
        t1 = t0 + timedelta(minutes=1)
        t2 = t0 + timedelta(minutes=2)
        t3 = t0 + timedelta(minutes=3)
        t4 = t0 + timedelta(minutes=4)

        with SessionLocal() as db:
            # Seed clean dedicated test washrooms to verify pure isolated calculation
            if not db.query(Washroom).filter_by(id=201).first():
                db.add(Washroom(id=201, slug="iso-washroom-1", name="Isolation W1", has_hardware=True, is_active=True, capacity=5))
            if not db.query(Washroom).filter_by(id=202).first():
                db.add(Washroom(id=202, slug="iso-washroom-2", name="Isolation W2", has_hardware=True, is_active=True, capacity=5))

            # Washroom 201 events: baseline at t0 (count=1), entry at t2 (count=3 -> delta +2)
            db.add(SensorRecord(washroom_id=201, device_id=1, people_count=1, occupancy_status="OCCUPIED", timestamp=t0))
            db.add(SensorRecord(washroom_id=201, device_id=1, people_count=3, occupancy_status="OCCUPIED", timestamp=t2))

            # Washroom 202 events: baseline at t0 (count=0), entry at t1 (count=4 -> delta +4), entry at t3 (count=5 -> delta +1)
            db.add(SensorRecord(washroom_id=202, device_id=1, people_count=0, occupancy_status="VACANT", timestamp=t0))
            db.add(SensorRecord(washroom_id=202, device_id=1, people_count=4, occupancy_status="OCCUPIED", timestamp=t1))
            db.add(SensorRecord(washroom_id=202, device_id=1, people_count=5, occupancy_status="OCCUPIED", timestamp=t3))
            db.commit()

            # Extract features for Washroom 201 at t4
            feat_w1, meta_w1 = extract_features_from_db(db, washroom_id=201, reference_time=t4)
            # Extract features for Washroom 202 at t4
            feat_w2, meta_w2 = extract_features_from_db(db, washroom_id=202, reference_time=t4)

        # Washroom 201 isolated metrics (must NOT reflect Washroom 202's 5 entries):
        self.assertEqual(feat_w1["current_occupancy"], 3)
        self.assertEqual(feat_w1["entries_5min"], 2)
        self.assertEqual(feat_w1["exits_5min"], 0)
        self.assertEqual(feat_w1["net_flow_5min"], 2)

        # Washroom 202 isolated metrics (must NOT reflect Washroom 201's records):
        self.assertEqual(feat_w2["current_occupancy"], 5)
        self.assertEqual(feat_w2["entries_5min"], 5)
        self.assertEqual(feat_w2["exits_5min"], 0)
        self.assertEqual(feat_w2["net_flow_5min"], 5)

        # Bidirectional cross-check
        self.assertNotEqual(feat_w1["current_occupancy"], feat_w2["current_occupancy"])
        self.assertNotEqual(feat_w1["entries_5min"], feat_w2["entries_5min"])

    def test_21_capacity_isolation_between_washrooms(self):
        """21. Test capacity and occupancy percentage resolve independently per washroom."""
        with SessionLocal() as db:
            w2 = db.query(Washroom).filter_by(id=202).first()
            w2.capacity = 10
            db.commit()

            t4 = datetime(2026, 11, 6, 12, 4, 0, tzinfo=timezone.utc)
            feat_w1, _ = extract_features_from_db(db, washroom_id=201, reference_time=t4)
            feat_w2, _ = extract_features_from_db(db, washroom_id=202, reference_time=t4)

        # Washroom 201: count=3, capacity=5 -> occupancy_percent=60.0%
        self.assertEqual(feat_w1["capacity"], 5)
        self.assertEqual(feat_w1["occupancy_percent"], 60.0)

        # Washroom 202: count=5, capacity=10 -> occupancy_percent=50.0%
        self.assertEqual(feat_w2["capacity"], 10)
        self.assertEqual(feat_w2["occupancy_percent"], 50.0)

    def test_22_feature_names_order_preserved_across_washrooms(self):
        """22. Test authoritative 9-feature order is identically preserved for all washrooms."""
        t4 = datetime(2026, 11, 6, 12, 4, 0, tzinfo=timezone.utc)
        with SessionLocal() as db:
            feat_w1, _ = extract_features_from_db(db, washroom_id=201, reference_time=t4)
            feat_w2, _ = extract_features_from_db(db, washroom_id=202, reference_time=t4)

        self.assertEqual(list(feat_w1.keys()), EXPECTED_FEATURES)
        self.assertEqual(list(feat_w2.keys()), EXPECTED_FEATURES)
        self.assertEqual(len(feat_w1), 9)
        self.assertEqual(len(feat_w2), 9)

    def test_23_prediction_manual_washroom_unavailable(self):
        """23. Test GET /api/prediction returns UNAVAILABLE for washrooms without hardware."""
        with SessionLocal() as db:
            if not db.query(Washroom).filter_by(id=3).first():
                w3 = Washroom(
                    id=3,
                    slug="demo-washroom-manual",
                    name="Demo Washroom (No Sensors)",
                    has_hardware=False,
                    is_active=True,
                    capacity=4,
                )
                db.add(w3)
                db.commit()

        res = self.client.get("/api/prediction?washroom_id=3")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["prediction_status"], "UNAVAILABLE")
        self.assertEqual(data["predicted_rush"], "UNAVAILABLE")
        self.assertEqual(data["predicted_rush_level"], "UNAVAILABLE")
        self.assertEqual(data["washroom_id"], 3)
        self.assertIn("has no IoT sensor hardware installed", data["note"])
        self.assertIsNone(data["features_used"])
        self.assertIsNone(data["probabilities"])
        self.assertIsNone(data["current_occupancy"])

    def test_24_invalid_washroom_id_returns_404(self):
        """24. Test invalid washroom IDs return HTTP 404 across all read endpoints."""
        res_status = self.client.get("/api/status?washroom_id=9999")
        self.assertEqual(res_status.status_code, 404)
        self.assertIn("Washroom #9999 not found", res_status.json()["detail"])

        res_pred = self.client.get("/api/prediction?washroom_id=9999")
        self.assertEqual(res_pred.status_code, 404)
        self.assertIn("Washroom #9999 not found", res_pred.json()["detail"])

        res_hist = self.client.get("/api/history?washroom_id=9999")
        self.assertEqual(res_hist.status_code, 404)
        self.assertIn("Washroom #9999 not found", res_hist.json()["detail"])

    # ========================================================
    # 5. Milestone 3A Haversine, Discovery, & Details Tests
    # ========================================================

    def test_25_haversine_identical_points(self):
        """25. Verify Haversine distance between identical coordinates is exactly 0.0 km."""
        dist = haversine_distance(18.5204, 73.8567, 18.5204, 73.8567)
        self.assertEqual(dist, 0.0)

    def test_26_haversine_known_benchmark(self):
        """26. Verify Haversine distance between Pune and Mumbai benchmarks (~120.15 km +- 0.5 km)."""
        dist = haversine_distance(18.5204, 73.8567, 19.0760, 72.8777)
        self.assertAlmostEqual(dist, 120.15, delta=0.5)

    def test_27_haversine_invalid_coordinates(self):
        """27. Verify out-of-bounds latitude and longitude raise ValueError."""
        with self.assertRaises(ValueError):
            haversine_distance(95.0, 73.0, 18.0, 72.0)
        with self.assertRaises(ValueError):
            haversine_distance(-95.0, 73.0, 18.0, 72.0)
        with self.assertRaises(ValueError):
            haversine_distance(18.0, 185.0, 18.0, 72.0)
        with self.assertRaises(ValueError):
            haversine_distance(18.0, -185.0, 18.0, 72.0)

    def test_28_nearby_discovery_recommendation_ordering(self):
        """28. Verify nearby discovery ranks vacant low-rush facility over closer occupied high-rush facility."""
        user_lat, user_lng = 18.5204, 73.8567

        with SessionLocal() as db:
            # Washroom 301: ~0.5 km away, vacant, low rush
            w301 = Washroom(
                id=301,
                slug="w301-vacant-low",
                name="Facility 301 Vacant Low",
                latitude=18.5249,
                longitude=73.8567,
                gender_type="UNISEX",
                has_hardware=True,
                is_active=True,
                capacity=5,
            )
            # Washroom 302: ~0.2 km away, occupied, high rush
            w302 = Washroom(
                id=302,
                slug="w302-occupied-high",
                name="Facility 302 Occupied High",
                latitude=18.5222,
                longitude=73.8567,
                gender_type="UNISEX",
                has_hardware=True,
                is_active=True,
                capacity=5,
            )
            db.merge(w301)
            db.merge(w302)

            now_time = datetime.now(timezone.utc)
            # 301 is vacant
            db.add(SensorRecord(washroom_id=301, device_id=1, people_count=0, occupancy_status="VACANT", timestamp=now_time))
            # 302 is occupied with 5 people (100% capacity)
            db.add(SensorRecord(washroom_id=302, device_id=1, people_count=5, occupancy_status="OCCUPIED", timestamp=now_time))
            db.commit()

        res = self.client.get(f"/api/washrooms/nearby?latitude={user_lat}&longitude={user_lng}&radius_km=5.0")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreaterEqual(data["total_found"], 2)

        found_ids = [w["washroom_id"] for w in data["washrooms"]]
        self.assertIn(301, found_ids)
        self.assertIn(302, found_ids)

        idx_301 = found_ids.index(301)
        idx_302 = found_ids.index(302)
        # Vacant facility 301 MUST rank ahead of congested facility 302 despite 302 being physically closer!
        self.assertLess(idx_301, idx_302)
        self.assertLess(data["washrooms"][idx_301]["recommendation_score"], data["washrooms"][idx_302]["recommendation_score"])

    def test_29_nearby_discovery_radius_filtering(self):
        """29. Verify facilities outside search radius are excluded from nearby discovery."""
        user_lat, user_lng = 18.5204, 73.8567

        with SessionLocal() as db:
            # Washroom 303: located ~7.7 km away (latitude 18.5900)
            w303 = Washroom(
                id=303,
                slug="w303-far",
                name="Facility 303 Far",
                latitude=18.5900,
                longitude=73.8567,
                gender_type="UNISEX",
                has_hardware=False,
                is_active=True,
            )
            db.merge(w303)
            db.commit()

        # Query with radius 5.0 km -> 303 must be excluded
        res_5km = self.client.get(f"/api/washrooms/nearby?latitude={user_lat}&longitude={user_lng}&radius_km=5.0")
        self.assertEqual(res_5km.status_code, 200)
        ids_5km = [w["washroom_id"] for w in res_5km.json()["washrooms"]]
        self.assertNotIn(303, ids_5km)

        # Query with radius 10.0 km -> 303 must be included
        res_10km = self.client.get(f"/api/washrooms/nearby?latitude={user_lat}&longitude={user_lng}&radius_km=10.0")
        self.assertEqual(res_10km.status_code, 200)
        ids_10km = [w["washroom_id"] for w in res_10km.json()["washrooms"]]
        self.assertIn(303, ids_10km)

    def test_30_nearby_discovery_inactive_washroom_excluded(self):
        """30. Verify inactive washrooms are strictly excluded from nearby discovery."""
        user_lat, user_lng = 18.5204, 73.8567

        with SessionLocal() as db:
            # Washroom 304: very close (~0.07 km), but is_active = False
            w304 = Washroom(
                id=304,
                slug="w304-inactive",
                name="Facility 304 Inactive",
                latitude=18.5210,
                longitude=73.8567,
                gender_type="UNISEX",
                has_hardware=False,
                is_active=False,
            )
            db.merge(w304)
            db.commit()

        res = self.client.get(f"/api/washrooms/nearby?latitude={user_lat}&longitude={user_lng}&radius_km=5.0")
        self.assertEqual(res.status_code, 200)
        ids = [w["washroom_id"] for w in res.json()["washrooms"]]
        self.assertNotIn(304, ids)

    def test_31_nearby_discovery_gender_filtering(self):
        """31. Verify gender filtering strictly excludes mismatched genders and UNKNOWN classifications."""
        user_lat, user_lng = 18.5204, 73.8567

        with SessionLocal() as db:
            w305 = Washroom(id=305, slug="w305-male", name="Facility Male", latitude=18.5215, longitude=73.8567, gender_type="MALE", is_active=True)
            w306 = Washroom(id=306, slug="w306-female", name="Facility Female", latitude=18.5216, longitude=73.8567, gender_type="FEMALE", is_active=True)
            w307 = Washroom(id=307, slug="w307-unisex", name="Facility Unisex", latitude=18.5217, longitude=73.8567, gender_type="UNISEX", is_active=True)
            w308 = Washroom(id=308, slug="w308-unknown", name="Facility Unknown", latitude=18.5218, longitude=73.8567, gender_type="UNKNOWN", is_active=True)
            for w in (w305, w306, w307, w308):
                db.merge(w)
            db.commit()

        # Query with gender=FEMALE: must return FEMALE and UNISEX; exclude MALE and UNKNOWN
        res_f = self.client.get(f"/api/washrooms/nearby?latitude={user_lat}&longitude={user_lng}&gender=FEMALE")
        self.assertEqual(res_f.status_code, 200)
        ids_f = [w["washroom_id"] for w in res_f.json()["washrooms"]]
        self.assertIn(306, ids_f)
        self.assertIn(307, ids_f)
        self.assertNotIn(305, ids_f)
        self.assertNotIn(308, ids_f)

        # Query with gender=MALE: must return MALE and UNISEX; exclude FEMALE and UNKNOWN
        res_m = self.client.get(f"/api/washrooms/nearby?latitude={user_lat}&longitude={user_lng}&gender=MALE")
        self.assertEqual(res_m.status_code, 200)
        ids_m = [w["washroom_id"] for w in res_m.json()["washrooms"]]
        self.assertIn(305, ids_m)
        self.assertIn(307, ids_m)
        self.assertNotIn(306, ids_m)
        self.assertNotIn(308, ids_m)

    def test_32_nearby_discovery_accessibility_filtering(self):
        """32. Verify accessibility filtering strictly matches is_accessible == True."""
        user_lat, user_lng = 18.5204, 73.8567

        with SessionLocal() as db:
            w309 = Washroom(id=309, slug="w309-acc-true", name="Facility Acc Yes", latitude=18.5211, longitude=73.8567, is_accessible=True, is_active=True)
            w310 = Washroom(id=310, slug="w310-acc-false", name="Facility Acc No", latitude=18.5212, longitude=73.8567, is_accessible=False, is_active=True)
            w311 = Washroom(id=311, slug="w311-acc-null", name="Facility Acc Null", latitude=18.5213, longitude=73.8567, is_accessible=None, is_active=True)
            for w in (w309, w310, w311):
                db.merge(w)
            db.commit()

        res = self.client.get(f"/api/washrooms/nearby?latitude={user_lat}&longitude={user_lng}&accessibility_required=true")
        self.assertEqual(res.status_code, 200)
        ids = [w["washroom_id"] for w in res.json()["washrooms"]]
        self.assertIn(309, ids)
        self.assertNotIn(310, ids)
        self.assertNotIn(311, ids)

    def test_33_nearby_discovery_hardware_vs_hardwareless(self):
        """33. Verify hardware vs hardware-less washroom response behaviors in discovery and details."""
        with SessionLocal() as db:
            # Hardware-less facility with manual occupancy override
            w312 = Washroom(
                id=312,
                slug="w312-hardwareless-override",
                name="Manual Facility Override",
                latitude=18.5208,
                longitude=73.8567,
                has_hardware=False,
                manual_occupancy_override="OCCUPIED",
                is_active=True,
            )
            db.merge(w312)
            db.commit()

        # Check in details API
        res = self.client.get(f"/api/washrooms/312?user_lat=18.5204&user_lng=73.8567")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["washroom_id"], 312)
        self.assertEqual(data["has_hardware"], False)
        self.assertEqual(data["occupancy_status"], "OCCUPIED")
        self.assertEqual(data["people_count"], 0)
        self.assertEqual(data["esp32_connected"], False)
        self.assertEqual(data["predicted_rush"], "UNAVAILABLE")
        self.assertEqual(data["predicted_rush_level"], "UNAVAILABLE")
        self.assertIsNotNone(data["distance_km"])

    def test_34_cleanliness_not_rated_behavior(self):
        """34. Verify facilities without ratings return 'Not yet rated' with null rating."""
        res = self.client.get("/api/washrooms/301")
        self.assertEqual(res.status_code, 200)
        cleanliness = res.json()["cleanliness"]
        self.assertIsNone(cleanliness["rating"])
        self.assertEqual(cleanliness["review_count"], 0)
        self.assertEqual(cleanliness["status_label"], "Not yet rated")

    def test_35_invalid_discovery_query_params_422(self):
        """35. Verify invalid discovery parameters return HTTP 422 Unprocessable Entity."""
        # Out-of-bounds latitude
        res1 = self.client.get("/api/washrooms/nearby?latitude=95.0&longitude=73.8")
        self.assertEqual(res1.status_code, 422)

        # Out-of-bounds longitude
        res2 = self.client.get("/api/washrooms/nearby?latitude=18.5&longitude=190.0")
        self.assertEqual(res2.status_code, 422)

        # Out-of-bounds radius (< 0.1)
        res3 = self.client.get("/api/washrooms/nearby?latitude=18.5&longitude=73.8&radius_km=0.05")
        self.assertEqual(res3.status_code, 422)

        # Out-of-bounds radius (> 50.0)
        res4 = self.client.get("/api/washrooms/nearby?latitude=18.5&longitude=73.8&radius_km=60.0")
        self.assertEqual(res4.status_code, 422)

        # Invalid gender
        res5 = self.client.get("/api/washrooms/nearby?latitude=18.5&longitude=73.8&gender=ALIEN")
        self.assertEqual(res5.status_code, 422)

        # Invalid limit (< 1)
        res6 = self.client.get("/api/washrooms/nearby?latitude=18.5&longitude=73.8&limit=0")
        self.assertEqual(res6.status_code, 422)

        # Invalid limit (> 50)
        res7 = self.client.get("/api/washrooms/nearby?latitude=18.5&longitude=73.8&limit=100")
        self.assertEqual(res7.status_code, 422)

    # ========================================================
    # 7. Milestone 3B: Device Location Registration Unit Tests
    # ========================================================

    @contextmanager
    def _isolated_device_and_washroom(self, washroom_id=1, initial_lat=None, initial_lng=None):
        """
        Transactional isolation fixture for Milestone 3B location tests.
        Captures the original state of the washroom and legacy device, sets desired
        initial test conditions, and unconditionally rolls back/restores the original
        clean state in a finally block so no state ever leaks between tests.
        """
        with SessionLocal() as db:
            w = db.query(Washroom).filter(Washroom.id == washroom_id).first()
            d = db.query(Device).filter(Device.is_legacy == True, Device.status == "ACTIVE").first()
            orig_w_lat = w.latitude if w else None
            orig_w_lng = w.longitude if w else None
            orig_w_active = w.is_active if w else True
            orig_d_washroom_id = d.washroom_id if d else None
            orig_d_status = d.status if d else "ACTIVE"

            if w:
                w.latitude = initial_lat
                w.longitude = initial_lng
                w.is_active = True
            if d:
                d.washroom_id = washroom_id
                d.status = "ACTIVE"
            db.commit()

        try:
            yield
        finally:
            with SessionLocal() as db:
                w = db.query(Washroom).filter(Washroom.id == washroom_id).first()
                d = db.query(Device).filter(Device.is_legacy == True).first()
                if w:
                    w.latitude = orig_w_lat
                    w.longitude = orig_w_lng
                    w.is_active = orig_w_active
                if d:
                    d.washroom_id = orig_d_washroom_id
                    d.status = orig_d_status
                db.commit()

    def test_36_device_location_missing_or_invalid_token_401(self):
        """36. Verify POST /api/devices/location requires valid X-Device-Token."""
        payload = {
            "latitude": 18.5204,
            "longitude": 73.8567,
            "altitude_m": 560.0,
            "hdop": 1.2,
            "satellites": 8,
        }
        # Missing token header -> 401
        res1 = self.client.post("/api/devices/location", json=payload)
        self.assertEqual(res1.status_code, 401)
        self.assertIn("Invalid or missing X-Device-Token", res1.json()["detail"])

        # Invalid token header -> 401
        res2 = self.client.post(
            "/api/devices/location",
            headers={"X-Device-Token": "unauthorized_forged_token"},
            json=payload,
        )
        self.assertEqual(res2.status_code, 401)
        self.assertIn("Invalid or missing X-Device-Token", res2.json()["detail"])

    def test_37_device_location_invalid_gps_metadata_422(self):
        """37. Verify GPS metadata validation: bounds, HDOP <= 3.5, satellites >= 4, and Null Island rejection."""
        headers = {"X-Device-Token": TEST_DEVICE_TOKEN}

        # Out-of-bounds latitude (> 90.0)
        res1 = self.client.post(
            "/api/devices/location",
            headers=headers,
            json={"latitude": 95.0, "longitude": 73.8567, "hdop": 1.2, "satellites": 8},
        )
        self.assertEqual(res1.status_code, 422)

        # Out-of-bounds longitude (> 180.0)
        res2 = self.client.post(
            "/api/devices/location",
            headers=headers,
            json={"latitude": 18.5204, "longitude": 185.0, "hdop": 1.2, "satellites": 8},
        )
        self.assertEqual(res2.status_code, 422)

        # Exact Null Island (0.0, 0.0) -> rejected with 422
        res3 = self.client.post(
            "/api/devices/location",
            headers=headers,
            json={"latitude": 0.0, "longitude": 0.0, "hdop": 1.0, "satellites": 8},
        )
        self.assertEqual(res3.status_code, 422)
        self.assertIn("Uninitialized GPS coordinates (0.0, 0.0) rejected", str(res3.json()))

        # Excessive HDOP (> 3.5)
        res4 = self.client.post(
            "/api/devices/location",
            headers=headers,
            json={"latitude": 18.5204, "longitude": 73.8567, "hdop": 3.6, "satellites": 8},
        )
        self.assertEqual(res4.status_code, 422)

        # Insufficient satellites (< 4)
        res5 = self.client.post(
            "/api/devices/location",
            headers=headers,
            json={"latitude": 18.5204, "longitude": 73.8567, "hdop": 1.2, "satellites": 3},
        )
        self.assertEqual(res5.status_code, 422)

    def test_38_device_location_equator_coordinates_registered(self):
        """38. Verify valid Equator coordinates (lat=0.0, lng!=0.0) are accepted and registered."""
        headers = {"X-Device-Token": TEST_DEVICE_TOKEN}

        with self._isolated_device_and_washroom(1, initial_lat=None, initial_lng=None):
            # Entebbe, Uganda / Pontianak, Indonesia lies near the Equator
            payload = {
                "latitude": 0.0,
                "longitude": 32.48,
                "altitude_m": 1130.0,
                "hdop": 1.4,
                "satellites": 7,
            }
            res = self.client.post("/api/devices/location", headers=headers, json=payload)
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data["status"], "REGISTERED")
            self.assertTrue(data["coordinates_updated"])
            self.assertEqual(data["latitude"], 0.0)
            self.assertEqual(data["longitude"], 32.48)
            self.assertEqual(data["washroom_id"], 1)

            # Confirm persistence in DB
            with SessionLocal() as db:
                w = db.query(Washroom).filter(Washroom.id == 1).first()
                self.assertEqual(w.latitude, 0.0)
                self.assertEqual(w.longitude, 32.48)

    def test_39_device_location_prime_meridian_coordinates_registered(self):
        """39. Verify valid Prime Meridian coordinates (lat!=0.0, lng=0.0) are accepted and registered."""
        headers = {"X-Device-Token": TEST_DEVICE_TOKEN}

        with self._isolated_device_and_washroom(1, initial_lat=None, initial_lng=None):
            # Greenwich, UK lies on the Prime Meridian
            payload = {
                "latitude": 51.48,
                "longitude": 0.0,
                "altitude_m": 46.0,
                "hdop": 1.1,
                "satellites": 9,
            }
            res = self.client.post("/api/devices/location", headers=headers, json=payload)
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data["status"], "REGISTERED")
            self.assertTrue(data["coordinates_updated"])
            self.assertEqual(data["latitude"], 51.48)
            self.assertEqual(data["longitude"], 0.0)
            self.assertEqual(data["washroom_id"], 1)

            with SessionLocal() as db:
                w = db.query(Washroom).filter(Washroom.id == 1).first()
                self.assertEqual(w.latitude, 51.48)
                self.assertEqual(w.longitude, 0.0)

    def test_40_device_location_first_registration_succeeds(self):
        """40. Verify initial registration succeeds when washroom coordinates are NULL."""
        headers = {"X-Device-Token": TEST_DEVICE_TOKEN}

        with self._isolated_device_and_washroom(1, initial_lat=None, initial_lng=None):
            payload = {
                "latitude": 18.5204,
                "longitude": 73.8567,
                "altitude_m": 560.0,
                "hdop": 1.2,
                "satellites": 8,
            }
            res = self.client.post("/api/devices/location", headers=headers, json=payload)
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data["status"], "REGISTERED")
            self.assertTrue(data["coordinates_updated"])
            self.assertEqual(data["latitude"], 18.5204)
            self.assertEqual(data["longitude"], 73.8567)
            self.assertEqual(data["washroom_id"], 1)
            self.assertEqual(data["washroom_name"], "Primary Washroom")
            self.assertEqual(data["device_uid"], "ESP32-PRIMARY-DEVICE")
            self.assertIsNotNone(data["timestamp"])

            # Verify GET /api/washrooms/1 reflects the new coordinates
            detail_res = self.client.get("/api/washrooms/1")
            self.assertEqual(detail_res.status_code, 200)
            detail_data = detail_res.json()
            self.assertEqual(detail_data["latitude"], 18.5204)
            self.assertEqual(detail_data["longitude"], 73.8567)

    def test_41_device_location_immutable_coordinate_lock(self):
        """41. Verify immutable coordinate lock prevents subsequent registrations from overwriting authoritative coordinates."""
        headers = {"X-Device-Token": TEST_DEVICE_TOKEN}

        with self._isolated_device_and_washroom(1, initial_lat=18.5204, initial_lng=73.8567):
            # Attempt second registration with completely different coordinates
            payload = {
                "latitude": 18.5555,
                "longitude": 73.8888,
                "altitude_m": 580.0,
                "hdop": 1.0,
                "satellites": 10,
            }
            res = self.client.post("/api/devices/location", headers=headers, json=payload)
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data["status"], "ALREADY_REGISTERED")
            self.assertFalse(data["coordinates_updated"])
            # Authoritative original coordinates returned, not the payload's
            self.assertEqual(data["latitude"], 18.5204)
            self.assertEqual(data["longitude"], 73.8567)

            # Confirm database coordinates remain untouched
            with SessionLocal() as db:
                w = db.query(Washroom).filter(Washroom.id == 1).first()
                self.assertEqual(w.latitude, 18.5204)
                self.assertEqual(w.longitude, 73.8567)

    def test_42_device_location_inconsistent_coordinates_409(self):
        """42. Verify inconsistent database coordinates (exactly one NULL) return HTTP 409 Conflict."""
        headers = {"X-Device-Token": TEST_DEVICE_TOKEN}
        payload = {
            "latitude": 18.5204,
            "longitude": 73.8567,
            "altitude_m": 560.0,
            "hdop": 1.2,
            "satellites": 8,
        }

        # Case 1: latitude populated, longitude NULL
        with self._isolated_device_and_washroom(1, initial_lat=18.5204, initial_lng=None):
            res1 = self.client.post("/api/devices/location", headers=headers, json=payload)
            self.assertEqual(res1.status_code, 409)
            self.assertIn("Inconsistent coordinates in database", res1.json()["detail"])

        # Case 2: latitude NULL, longitude populated
        with self._isolated_device_and_washroom(1, initial_lat=None, initial_lng=73.8567):
            res2 = self.client.post("/api/devices/location", headers=headers, json=payload)
            self.assertEqual(res2.status_code, 409)
            self.assertIn("Inconsistent coordinates in database", res2.json()["detail"])

    def test_43_device_location_unassigned_or_inactive_device_errors(self):
        """43. Verify errors for unassigned device (409), inactive washroom (503), or inactive device (503)."""
        headers = {"X-Device-Token": TEST_DEVICE_TOKEN}
        payload = {
            "latitude": 18.5204,
            "longitude": 73.8567,
            "altitude_m": 560.0,
            "hdop": 1.2,
            "satellites": 8,
        }

        # Subcase A: Legacy device not assigned to any washroom -> 409 Conflict
        with self._isolated_device_and_washroom(1, initial_lat=None, initial_lng=None):
            with SessionLocal() as db:
                d = db.query(Device).filter(Device.is_legacy == True).first()
                d.washroom_id = None
                db.commit()

            res_a = self.client.post("/api/devices/location", headers=headers, json=payload)
            self.assertEqual(res_a.status_code, 409)
            self.assertIn("is not assigned to any washroom", res_a.json()["detail"])

        # Subcase B: Assigned washroom is inactive -> 503 Service Unavailable
        with self._isolated_device_and_washroom(1, initial_lat=None, initial_lng=None):
            with SessionLocal() as db:
                w = db.query(Washroom).filter(Washroom.id == 1).first()
                w.is_active = False
                db.commit()

            res_b = self.client.post("/api/devices/location", headers=headers, json=payload)
            self.assertEqual(res_b.status_code, 503)
            self.assertIn("is inactive or not found", res_b.json()["detail"])

        # Subcase C: No active legacy device -> 503 Service Unavailable
        with self._isolated_device_and_washroom(1, initial_lat=None, initial_lng=None):
            with SessionLocal() as db:
                d = db.query(Device).filter(Device.is_legacy == True).first()
                d.status = "INACTIVE"
                db.commit()

            res_c = self.client.post("/api/devices/location", headers=headers, json=payload)
            self.assertEqual(res_c.status_code, 503)
            self.assertIn("No active legacy ESP32 hardware device", res_c.json()["detail"])

    # ========================================================
    # 7. Milestone 3B Telemetry & GPS Device Token Hardening
    # ========================================================

    def test_44_sensor_data_missing_or_invalid_token_401(self):
        """44. Verify POST /api/sensor-data fails closed with 401 if X-Device-Token is missing or invalid."""
        payload = {
            "ir1_state": 0,
            "ir2_state": 0,
            "pir_state": 0,
            "people_count": 0,
            "occupancy_status": "VACANT",
        }
        # Subcase A: Missing X-Device-Token header -> 401 Unauthorized
        res1 = self.client.post("/api/sensor-data", json=payload)
        self.assertEqual(res1.status_code, 401)
        self.assertIn("Invalid or missing X-Device-Token", res1.json()["detail"])

        # Subcase B: Invalid X-Device-Token header -> 401 Unauthorized
        res2 = self.client.post(
            "/api/sensor-data",
            headers={"X-Device-Token": "unauthorized_forged_device_token"},
            json=payload,
        )
        self.assertEqual(res2.status_code, 401)
        self.assertIn("Invalid or missing X-Device-Token", res2.json()["detail"])

    def test_45_server_missing_or_blank_device_token_503(self):
        """45. Verify both endpoints fail closed with 503 when server-side LEGACY_DEVICE_TOKEN is missing or blank."""
        orig_token = os.environ.get("LEGACY_DEVICE_TOKEN")
        sensor_payload = {
            "ir1_state": 0,
            "ir2_state": 0,
            "pir_state": 0,
            "people_count": 0,
            "occupancy_status": "VACANT",
        }
        gps_payload = {
            "latitude": 18.5204,
            "longitude": 73.8567,
            "altitude_m": 560.0,
            "hdop": 1.2,
            "satellites": 8,
        }

        try:
            # Subcase A: LEGACY_DEVICE_TOKEN is completely unset / missing from environment
            if "LEGACY_DEVICE_TOKEN" in os.environ:
                del os.environ["LEGACY_DEVICE_TOKEN"]

            res_sensor_missing = self.client.post(
                "/api/sensor-data",
                headers={"X-Device-Token": TEST_DEVICE_TOKEN},
                json=sensor_payload,
            )
            self.assertEqual(res_sensor_missing.status_code, 503)
            self.assertIn("Device authentication is not configured on the server", res_sensor_missing.json()["detail"])

            res_gps_missing = self.client.post(
                "/api/devices/location",
                headers={"X-Device-Token": TEST_DEVICE_TOKEN},
                json=gps_payload,
            )
            self.assertEqual(res_gps_missing.status_code, 503)
            self.assertIn("Device authentication is not configured on the server", res_gps_missing.json()["detail"])

            # Subcase B: LEGACY_DEVICE_TOKEN is blank / empty whitespace
            os.environ["LEGACY_DEVICE_TOKEN"] = "   "

            res_sensor_blank = self.client.post(
                "/api/sensor-data",
                headers={"X-Device-Token": TEST_DEVICE_TOKEN},
                json=sensor_payload,
            )
            self.assertEqual(res_sensor_blank.status_code, 503)
            self.assertIn("Device authentication is not configured on the server", res_sensor_blank.json()["detail"])

            res_gps_blank = self.client.post(
                "/api/devices/location",
                headers={"X-Device-Token": TEST_DEVICE_TOKEN},
                json=gps_payload,
            )
            self.assertEqual(res_gps_blank.status_code, 503)
            self.assertIn("Device authentication is not configured on the server", res_gps_blank.json()["detail"])

        finally:
            if orig_token is not None:
                os.environ["LEGACY_DEVICE_TOKEN"] = orig_token
            elif "LEGACY_DEVICE_TOKEN" in os.environ:
                del os.environ["LEGACY_DEVICE_TOKEN"]




if __name__ == "__main__":
    unittest.main()
