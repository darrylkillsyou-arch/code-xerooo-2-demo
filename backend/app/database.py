"""Database connection and session configuration supporting SQLite and Supabase / PostgreSQL."""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import settings

raw_db_url = settings.DATABASE_URL or "sqlite:///./maccall.db"

# Supabase and Heroku often provide urls starting with postgres://, which SQLAlchemy 1.4+ deprecated
if raw_db_url.startswith("postgres://"):
    db_url = raw_db_url.replace("postgres://", "postgresql://", 1)
else:
    db_url = raw_db_url

engine_kwargs = {
    "echo": False,
}

if db_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # PostgreSQL / Neon serverless configuration
    # Using NullPool prevents leaking persistent connection pools across stateless serverless invocations.
    # Neon's PgBouncer pooler efficiently handles connection pooling at the infrastructure layer.
    from sqlalchemy.pool import NullPool
    engine_kwargs["poolclass"] = NullPool
    engine_kwargs["pool_pre_ping"] = True

engine = create_engine(db_url, **engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependency for obtaining database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
