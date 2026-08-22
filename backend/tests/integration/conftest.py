import asyncio
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.config.database import async_session_factory, engine
from app.integrations.embedding_client import get_embedding_client
from app.integrations.object_storage import ObjectStorageClient
from app.main import app
from app.services.tariff_seed_service import seed_tariff_headings_if_empty

# Deletes in FK-safe order (children first). Using DELETE rather than TRUNCATE so this
# also works cleanly if a test ever runs inside its own transaction in the future.
# tariff_headings is deliberately excluded — it's shared reference data (the vector-
# search knowledge base), not per-company data, so it persists across tests the same
# way it would in production.
_TABLES_IN_DELETE_ORDER = [
    "classification_results",
    "permit_requirements",
    "line_items",
    "discrepancies",
    "documents",
    "shipments",
    "users",
    "companies",
]

# httpx's ASGITransport does not run FastAPI's lifespan protocol (that's what
# app/main.py's `ensure_bucket()` startup hook relies on for real `uvicorn` runs), so
# tests need to ensure the bucket exists themselves. Once, not per-test — cheap and
# idempotent, but no need to call it on every single test.
ObjectStorageClient().ensure_bucket()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _seeded_tariff_kb() -> None:
    """Session-scoped, not per-test — tariff_headings is shared reference data (see
    _TABLES_IN_DELETE_ORDER above), and seeding calls a real local embedding model per
    row, which is too slow to repeat before every single test."""
    async with async_session_factory() as session:
        await seed_tariff_headings_if_empty(session, get_embedding_client())


_CLEANUP_MAX_ATTEMPTS = 10
_CLEANUP_RETRY_DELAY_SECONDS = 0.3


@pytest_asyncio.fixture(autouse=True)
async def _clean_database() -> AsyncGenerator[None]:
    """Every integration test starts against an empty database — this is what makes
    the tenant-isolation tests trustworthy (no leftover rows from a previous test could
    accidentally satisfy a query).

    Retries on a transient FK violation rather than assuming the real Celery worker is
    always idle by the time a test function returns: a test that triggers a multi-hop
    chain (e.g. classify -> triage_shipment_permits) isn't obligated to wait for every
    downstream hop to finish before it ends, so the worker can still be inserting a
    row for the previous test's shipment while this fixture's delete sequence is
    mid-flight. The alternative — auditing every test that touches any chained task
    for a "wait until fully settled" call, forever, as more phases add more hops — is
    the wrong fix for what's fundamentally a timing overlap, not a test bug.
    """
    for attempt in range(_CLEANUP_MAX_ATTEMPTS):
        try:
            async with engine.begin() as conn:
                for table in _TABLES_IN_DELETE_ORDER:
                    await conn.execute(text(f"DELETE FROM {table}"))
            break
        except IntegrityError:
            if attempt == _CLEANUP_MAX_ATTEMPTS - 1:
                raise
            await asyncio.sleep(_CLEANUP_RETRY_DELAY_SECONDS)
    yield


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
