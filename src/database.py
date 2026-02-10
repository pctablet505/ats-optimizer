"""SQLAlchemy database setup for ATS Optimizer."""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.config import get_config, PROJECT_ROOT


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


def get_engine(db_url: str | None = None):
    """Create a SQLAlchemy engine."""
    if db_url is None:
        db_url = get_config().database.url

    # Handle relative sqlite paths — resolve relative to project root
    if db_url.startswith("sqlite:///") and not db_url.startswith("sqlite:////"):
        relative_path = db_url.replace("sqlite:///", "")
        abs_path = PROJECT_ROOT / relative_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        db_url = f"sqlite:///{abs_path}"

    return create_engine(db_url, echo=False)


def get_session_factory(engine=None) -> sessionmaker[Session]:
    """Create a session factory."""
    if engine is None:
        engine = get_engine()
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine=None):
    """Create all tables."""
    if engine is None:
        engine = get_engine()
    Base.metadata.create_all(engine)
