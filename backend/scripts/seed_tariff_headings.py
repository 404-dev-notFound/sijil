"""One-time ETL: loads the illustrative tariff-heading seed set into the
TariffKBRepository vector store (architecture doc Section 6.1's "ingest the published
UAE/GCC tariff schedule" step, implementation plan Section 5).

This seed set (data/tariff_headings/seed_v1.json) is NOT the real UAE/GCC 12-digit
tariff schedule — see app/models/tariff_heading.py's docstring. Replace it with real
ingested data once Track A-style research produces the actual schedule; this script's
job then becomes ingesting that file instead, unchanged otherwise.

Run from backend/: python -m scripts.seed_tariff_headings
"""

import asyncio

from app.config.database import async_session_factory, engine
from app.integrations.embedding_client import get_embedding_client
from app.services.tariff_seed_service import seed_tariff_headings_if_empty


async def main() -> None:
    async with async_session_factory() as session:
        inserted = await seed_tariff_headings_if_empty(session, get_embedding_client())
    if inserted:
        print(f"Seeded {inserted} illustrative tariff headings.")
    else:
        print("tariff_headings already populated — no changes made.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
