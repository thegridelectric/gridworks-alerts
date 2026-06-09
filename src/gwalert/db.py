import dotenv
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from gwalert.config import DEFAULT_ENV_FILE, Settings

SessionLocal: sessionmaker | None = None


def configure(settings: Settings | None = None) -> None:
    """Bind the journal DB session factory (call once at process startup)."""
    global SessionLocal
    resolved = settings or Settings(_env_file=dotenv.find_dotenv(DEFAULT_ENV_FILE))
    engine = create_engine(
        resolved.db_url.get_secret_value(),
        echo=False,
        pool_size=10,
        max_overflow=20,
        pool_timeout=30,
    )
    SessionLocal = sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
    )


def get_db() -> Generator[Session, None, None]:
    if SessionLocal is None:
        configure()
    assert SessionLocal is not None
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
