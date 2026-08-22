import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.integrations.embedding_client import EmbeddingClient, get_embedding_client
from app.integrations.llm_client import LLMClient, get_llm_client
from app.models.classification_result import ClassificationResult
from app.models.line_item import LineItem
from app.repositories.classification_result_repository import ClassificationResultRepository
from app.repositories.line_item_repository import LineItemRepository
from app.repositories.tariff_kb_repository import TariffKBRepository

logger = logging.getLogger(__name__)


class ClassificationService:
    """Given a line item, returns ranked HS code candidates with confidence and
    reasoning (architecture doc Section 6.1): (1) embed the product description, (2)
    vector-search the nearest tariff headings, (3) pass candidates + description to
    the LLM with a GRI-reasoning prompt, (4) parse the structured result, (5) apply a
    confidence floor — below threshold, requires_manual_review=True. Worker-only, same
    rationale as DocumentExtractionService (architecture doc Section 14).
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        llm_client: LLMClient | None = None,
        embedding_client: EmbeddingClient | None = None,
    ) -> None:
        self._line_items = LineItemRepository(session)
        self._tariff_kb = TariffKBRepository(session)
        self._results = ClassificationResultRepository(session)
        self._llm = llm_client or get_llm_client()
        self._embeddings = embedding_client or get_embedding_client()
        self._settings = get_settings()

    async def classify(self, line_item: LineItem) -> ClassificationResult:
        matches = await self._tariff_kb.vector_search(
            self._embeddings.embed(line_item.description),
            limit=self._settings.tariff_kb_search_limit,
        )
        candidates = [
            {
                "hs_code": heading.hs_code,
                "description": heading.description,
                "distance": distance,
            }
            for heading, distance in matches
        ]

        try:
            result = self._llm.classify_product(line_item.description, candidates)
        except Exception:
            # LLM timeout/error -> fail gracefully with requires_manual_review=True
            # rather than crashing the rest of the shipment's classification
            # (architecture doc Section 6.1 error handling).
            logger.exception("Classification failed for line_item_id=%s", line_item.id)
            result = {"hs_code": None, "confidence": 0.0, "reasoning": "", "alternatives": []}

        confidence = float(result.get("confidence", 0.0))
        hs_code = result.get("hs_code")
        requires_manual_review = hs_code is None or (
            confidence < self._settings.classification_confidence_threshold
        )
        reasoning = result.get("reasoning") or (
            "Classification failed — no reliable result could be produced."
            if hs_code is None and confidence == 0.0
            else ""
        )

        return await self._results.upsert(
            line_item.id,
            hs_code=hs_code,
            confidence=confidence,
            reasoning=reasoning,
            requires_manual_review=requires_manual_review,
            alternatives=result.get("alternatives", []),
        )

    async def classify_shipment(self, shipment_id: uuid.UUID) -> None:
        """Worker-only, unscoped line-item fetch (architecture doc Section 14)."""
        for line_item in await self._line_items.list_by_shipment(shipment_id):
            await self.classify(line_item)
