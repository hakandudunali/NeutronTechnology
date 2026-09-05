"""Application entry point for the EkoMatik FastAPI backend."""

from fastapi import FastAPI

from app.api.routes import router
from app.core.config import settings
from app.db.session import Base, engine
from app.middleware.iot_hmac import IoTHMACMiddleware

# Import ORM models before metadata creation so SQLAlchemy knows every table.
from app import models as _models  # noqa: F401,E402


# FastAPI application instance used by Uvicorn/Gunicorn.
app = FastAPI(title=settings.app_name, version="1.0.0")

# The middleware is intentionally narrow: only the IoT earning route needs HMAC auth.
app.add_middleware(IoTHMACMiddleware)
app.include_router(router)


@app.on_event("startup")
def create_tables() -> None:
    """Create missing PostgreSQL tables on startup for easy local prototyping.

    In production, replace this with Alembic migrations so schema evolution is explicit,
    reviewable, and reversible. This development helper is idempotent for existing tables.
    """

    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health() -> dict[str, str]:
    """Return a minimal liveness response for load balancers and deployment checks."""

    return {"status": "ok"}