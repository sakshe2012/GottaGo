import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import joblib
import pandas as pd

logger = logging.getLogger("gottago-model")

BASE_DIR = Path(__file__).resolve().parent

# Authoritative 9-feature specification from train_model_v2.py and features.json
EXPECTED_FEATURES: List[str] = [
    "day_of_week",
    "is_weekend",
    "hour",
    "capacity",
    "current_occupancy",
    "occupancy_percent",
    "entries_5min",
    "exits_5min",
    "net_flow_5min",
]

VALID_CLASSES: List[str] = ["LOW", "MEDIUM", "HIGH"]


class ModelPredictionError(Exception):
    """Raised when prediction or probability computation fails."""
    pass


class ModelNotLoadedError(ModelPredictionError):
    """Raised when an inference is attempted but the model is not loaded."""
    pass


class InvalidFeatureError(ModelPredictionError):
    """Raised when input features are missing, invalid, or out of expected schema."""
    pass


def find_model_path() -> Optional[Path]:
    """Locates the trained model file with prioritized search paths."""
    env_path = os.getenv("MODEL_PATH")
    if env_path:
        p = Path(env_path)
        if p.is_file():
            return p

    # Local backend directory
    local_path = BASE_DIR / "rush_model.pkl"
    if local_path.is_file():
        return local_path

    return None


def find_features_path() -> Optional[Path]:
    """Locates the features.json file."""
    env_path = os.getenv("FEATURES_PATH")
    if env_path:
        p = Path(env_path)
        if p.is_file():
            return p

    local_path = BASE_DIR / "features.json"
    if local_path.is_file():
        return local_path

    return None


class RushPredictionModelService:
    """
    Service responsible for loading rush_model.pkl once at startup,
    validating model schema against features.json, and performing
    calibrated inference for the GottaGo rush prediction endpoint.
    """

    def __init__(self, model_path: Optional[Path] = None):
        self.model_path = model_path or find_model_path()
        self.model = None
        self.classes: List[str] = []
        self.feature_names: List[str] = EXPECTED_FEATURES
        self.is_loaded: bool = False
        self.load_error: Optional[str] = None

    def load(self) -> bool:
        """
        Loads the trained Random Forest model and validates its metadata.
        Returns True if successfully loaded, False otherwise.
        """
        if self.is_loaded and self.model is not None:
            return True

        if not self.model_path or not self.model_path.is_file():
            self.load_error = f"Model file not found. Checked: {self.model_path}"
            logger.error(self.load_error)
            self.is_loaded = False
            return False

        try:
            logger.info(f"Loading trained rush prediction model from: {self.model_path}")
            model = joblib.load(self.model_path)

            # Validate model object
            if not hasattr(model, "predict"):
                raise ValueError(f"Loaded object of type {type(model)} has no predict() method.")

            # Validate feature count
            n_features = getattr(model, "n_features_in_", None)
            if n_features is not None and n_features != len(EXPECTED_FEATURES):
                raise ValueError(
                    f"Model expects {n_features} features, but specification defines {len(EXPECTED_FEATURES)}."
                )

            # Validate feature names if present in model
            model_features = getattr(model, "feature_names_in_", None)
            if model_features is not None:
                model_feat_list = list(model_features)
                if model_feat_list != EXPECTED_FEATURES:
                    raise ValueError(
                        f"Model feature names mismatch. Expected: {EXPECTED_FEATURES}, got: {model_feat_list}"
                    )
                self.feature_names = model_feat_list

            # Validate classes and probabilities
            if hasattr(model, "classes_"):
                self.classes = [str(c) for c in model.classes_]
                logger.info(f"Model classes: {self.classes}")

            self.model = model
            self.is_loaded = True
            self.load_error = None
            logger.info("Rush prediction model successfully loaded and validated.")
            return True

        except Exception as e:
            self.model = None
            self.is_loaded = False
            self.load_error = str(e)
            logger.error(f"Failed to load rush prediction model: {e}", exc_info=True)
            return False

    def validate_features(self, features: Dict[str, Any]) -> pd.DataFrame:
        """
        Validates feature presence, non-null values, and strictly formats
        the input DataFrame with the exact authoritative column order.
        """
        missing = [f for f in self.feature_names if f not in features or features[f] is None]
        if missing:
            raise InvalidFeatureError(f"Missing required feature(s): {', '.join(missing)}")

        # Validate numeric types
        clean_row = {}
        for f in self.feature_names:
            val = features[f]
            try:
                if f in ("day_of_week", "is_weekend", "hour", "capacity", "current_occupancy", "entries_5min", "exits_5min", "net_flow_5min"):
                    clean_row[f] = int(val)
                elif f == "occupancy_percent":
                    clean_row[f] = float(val)
                else:
                    clean_row[f] = float(val)
            except (ValueError, TypeError) as e:
                raise InvalidFeatureError(f"Feature '{f}' value '{val}' cannot be converted to number: {e}")

        # Construct single-row DataFrame in the EXACT feature order
        df = pd.DataFrame([clean_row])[self.feature_names]
        return df

    def predict(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes prediction on the provided features dictionary.
        Returns a dictionary with predicted_rush, probabilities, and metadata.
        """
        if not self.is_loaded or self.model is None:
            raise ModelNotLoadedError(f"Model is not loaded. Error: {self.load_error or 'Unknown'}")

        df = self.validate_features(features)

        try:
            # 1. Predict rush class
            pred_arr = self.model.predict(df)
            predicted_class = str(pred_arr[0]).upper()

            # 2. Predict class probabilities if supported
            probabilities: Dict[str, float] = {}
            if hasattr(self.model, "predict_proba"):
                probs = self.model.predict_proba(df)[0]
                raw_prob_dict = {
                    str(cls_name).upper(): float(prob)
                    for cls_name, prob in zip(self.classes, probs)
                }
                # Map into clean dict with LOW, MEDIUM, HIGH keys
                probabilities = {
                    "LOW": round(raw_prob_dict.get("LOW", 0.0), 4),
                    "MEDIUM": round(raw_prob_dict.get("MEDIUM", 0.0), 4),
                    "HIGH": round(raw_prob_dict.get("HIGH", 0.0), 4),
                }

            # Convert features to native python types for JSON compatibility
            native_features = {}
            for col in self.feature_names:
                v = df.iloc[0][col]
                if col in ("day_of_week", "is_weekend", "hour", "capacity", "current_occupancy", "entries_5min", "exits_5min", "net_flow_5min"):
                    native_features[col] = int(v)
                else:
                    native_features[col] = float(v)

            return {
                "predicted_rush": predicted_class,
                "probabilities": probabilities,
                "features_used": native_features,
                "model_status": "LOADED",
            }
        except Exception as e:
            logger.error(f"Prediction inference failed: {e}", exc_info=True)
            raise ModelPredictionError(f"Inference execution failed: {e}")


# Global singleton instance
model_service = RushPredictionModelService()
