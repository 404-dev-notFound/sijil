from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

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


@pytest_asyncio.fixture(autouse=True)
async def _clean_database() -> AsyncGenerator[None]:
    """Every integration test starts against an empty database — this is what makes
    the tenant-isolation tests trustworthy (no leftover rows from a previous test could
    accidentally satisfy a query)."""
    async with engine.begin() as conn:
        for table in _TABLES_IN_DELETE_ORDER:
            await conn.execute(text(f"DELETE FROM {table}"))
    yield


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
