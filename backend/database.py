import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Set database path to backend directory
BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "gottago.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_FILE}")

# SQLite connection argument to allow multi-threaded access in FastAPI
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def init_db():
    """Create all database tables automatically on startup."""
    # Import models to ensure they are registered with Base metadata
    import models  # noqa: F401
    Base.metadata.create_all(bind=engine)

    # Ensure default washroom and legacy device exist if empty
    with SessionLocal() as db:
        try:
            if not db.query(models.Washroom).filter_by(id=1).first():
                default_washroom = models.Washroom(
                    id=1,
                    slug="primary-washroom",
                    name="Primary Washroom",
                    has_hardware=True,
                    is_active=True,
                    is_demo=False,
                    gender_type="UNKNOWN",
                )
                db.add(default_washroom)
                db.commit()
            if not db.query(models.Device).filter_by(id=1).first():
                default_device = models.Device(
                    id=1,
                    device_uid="ESP32-PRIMARY-DEVICE",
                    name="Primary ESP32",
                    washroom_id=1,
                    status="ACTIVE",
                    is_legacy=True,
                )
                db.add(default_device)
                db.commit()
        except Exception:
            db.rollback()


def get_db():
    """Dependency providing a transactional database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
