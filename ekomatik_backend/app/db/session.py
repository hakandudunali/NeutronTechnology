"""SQLAlchemy engine and database session helpers."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """Base class inherited by all SQLAlchemy ORM models."""


# The synchronous engine keeps the project easy to run and understand while still
# supporting PostgreSQL row-level locks and real ACID transactions.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# expire_on_commit=False means values can still be returned after committing a transaction.
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Yield one database session per API request and close it afterwards.

    Any route that raises an exception before committing can safely rely on the
    session context being closed; explicit transaction rollback is handled inside
    service functions where multi-step ACID operations are performed.
    """

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()