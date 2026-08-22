from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.api.v1 import auth, classification, companies, discrepancies, shipments
from app.config.database import engine
from app.config.settings import get_settings
from app.integrations.object_storage import ObjectStorageClient
from app.middleware.error_handling import register_error_handlers

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    # Idempotent — safe on every startup. Real deployments provision the bucket
    # out-of-band instead; this exists for local dev/CI convenience (architecture doc
    # Section 13 / integrations/object_storage.py).
    ObjectStorageClient().ensure_bucket()
    yield


app = FastAPI(title="Sijil API", version="0.1.0", lifespan=lifespan)

register_error_handlers(app)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(companies.router, prefix="/api/v1/companies", tags=["companies"])
app.include_router(shipments.router, prefix="/api/v1/shipments", tags=["shipments"])
app.include_router(
    classification.router, prefix="/api/v1/shipments", tags=["classification"]
)
app.include_router(
    discrepancies.router, prefix="/api/v1/shipments", tags=["discrepancies"]
)
# Phase 5+: permit_triage.py, cepa.py, billing.py mount here once their business
# logic exists.


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check."""
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready() -> dict[str, str]:
    """Readiness check — verifies DB connectivity. Queue (Celery/Redis) connectivity
    check is added once workers exist starting Phase 2."""
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return {"status": "ok"}
