from fastapi import FastAPI

from app.config.settings import get_settings

settings = get_settings()

app = FastAPI(title="Sijil API", version="0.1.0")

# Phase 1+ routers (auth, companies, shipments, classification, billing) are mounted
# here under /api/v1/... once their business logic exists — see docs/API SPEC.pdf.


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check."""
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready() -> dict[str, str]:
    """Readiness check — will verify DB and queue connectivity once repositories and
    the Celery app are wired up (Phase 1+); currently a placeholder."""
    return {"status": "ok"}
