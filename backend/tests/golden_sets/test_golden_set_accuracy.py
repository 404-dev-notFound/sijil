import json
from pathlib import Path

from app.config.database import async_session_factory
from app.integrations.embedding_client import get_embedding_client
from app.integrations.llm_client import get_llm_client
from app.repositories.tariff_kb_repository import TariffKBRepository
from app.services.tariff_seed_service import seed_tariff_headings_if_empty

_PAIRS_FILE = Path(__file__).parent / "classification_pairs.json"
_BASELINE_FILE = Path(__file__).parent / "baseline.json"
_SEARCH_LIMIT = 10


async def test_classification_accuracy_meets_baseline() -> None:
    """The single most important test suite in the system (architecture doc Section
    21) — tracks HS classification accuracy against a curated set of known-correct
    pairs and fails the build if accuracy regresses (architecture doc Section 25).

    This golden set is intentionally small — the implementation plan's 200+ pair
    target needs real domain research this scaffold doesn't fabricate (see
    app/models/tariff_heading.py's docstring) — but the harness itself is the real,
    permanent mechanism: point it at a larger, real dataset later without touching
    this test. Runs against whichever LLM_PROVIDER is configured (mock in CI; set
    LLM_PROVIDER=claude with a real key locally to validate actual GRI-reasoning
    accuracy, not just vector-search retrieval quality).
    """
    embedding_client = get_embedding_client()
    llm_client = get_llm_client()

    async with async_session_factory() as session:
        await seed_tariff_headings_if_empty(session, embedding_client)
        tariff_kb = TariffKBRepository(session)

        pairs = json.loads(_PAIRS_FILE.read_text(encoding="utf-8"))
        correct = 0
        for pair in pairs:
            matches = await tariff_kb.vector_search(
                embedding_client.embed(pair["description"]), limit=_SEARCH_LIMIT
            )
            candidates = [
                {"hs_code": heading.hs_code, "description": heading.description, "distance": d}
                for heading, d in matches
            ]
            result = llm_client.classify_product(pair["description"], candidates)
            if result.get("hs_code") == pair["expected_hs_code"]:
                correct += 1

    accuracy = correct / len(pairs)
    baseline = json.loads(_BASELINE_FILE.read_text(encoding="utf-8"))["accuracy"]
    assert accuracy >= baseline, (
        f"Golden-set classification accuracy dropped: {accuracy:.2%} "
        f"(baseline: {baseline:.2%}) — {correct}/{len(pairs)} correct."
    )
