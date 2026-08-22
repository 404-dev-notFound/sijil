import json
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.embedding_client import EmbeddingClient
from app.models.tariff_heading import TariffHeading
from app.repositories.tariff_kb_repository import TariffKBRepository

# backend/app/services/tariff_seed_service.py -> parents[3] is the repo root, where
# data/ lives alongside backend/, frontend/, docs/ (architecture doc Section 7).
_SEED_FILE = Path(__file__).resolve().parents[3] / "data" / "tariff_headings" / "seed_v1.json"


async def seed_tariff_headings_if_empty(
    session: AsyncSession, embedding_client: EmbeddingClient
) -> int:
    """Idempotent: seeds the illustrative placeholder tariff headings (see
    app/models/tariff_heading.py's docstring — NOT the real UAE/GCC schedule) only if
    the table is currently empty, so it never overwrites a real ingested schedule with
    placeholder data. Returns the number of rows inserted.
    """
    repo = TariffKBRepository(session)
    if await repo.count() > 0:
        return 0

    entries = json.loads(_SEED_FILE.read_text(encoding="utf-8"))
    for entry in entries:
        embedding = embedding_client.embed(entry["description"])
        await repo.create(
            TariffHeading(
                hs_code=entry["hs_code"],
                description=entry["description"],
                source=entry["source"],
                embedding=embedding,
            )
        )
    await session.commit()
    return len(entries)
