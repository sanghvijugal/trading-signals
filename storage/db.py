import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from storage.models import Base


def _build_engine():
    database_url = os.getenv("DATABASE_URL")

    if database_url:
        # Supabase / Postgres in production
        # SQLAlchemy requires postgresql:// not postgres://
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        return create_engine(database_url, echo=False)
    else:
        # SQLite for local development
        os.makedirs("data", exist_ok=True)
        return create_engine("sqlite:///data/signals.db", echo=False)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine)


def init_db():
    """Create all tables if they don't exist."""
    Base.metadata.create_all(engine)


def get_session():
    return SessionLocal()
