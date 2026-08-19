from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.config.database import engine
from app.integrations.object_storage import ObjectStorageClient
from app.main import app

# Deletes in FK-safe order (children first). Using DELETE rather than TRUNCATE so this
# also works cleanly if a test ever runs inside its own transaction in the future.
_TABLES_IN_DELETE_ORDER = ["documents", "shipments", "users", "companies"]

# httpx's ASGITransport does not run FastAPI's lifespan protocol (that's what
# app/main.py's `ensure_bucket()` startup hook relies on for real `uvicorn` runs), so
# tests need to ensure the bucket exists themselves. Once, not per-test — cheap and
# idempotent, but no need to call it on every single test.
ObjectStorageClient().ensure_bucket()


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
