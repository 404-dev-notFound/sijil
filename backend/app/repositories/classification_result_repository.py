import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.classification_result import ClassificationResult


class ClassificationResultRepository:
    """Worker-only (app/services/classification_service.py) — the API-facing override
    endpoint mutates an already-scoped LineItem.classification relationship directly
    (app/services/line_item_service.py) rather than going through this repository, so
    it never needs an unscoped lookup of its own.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        line_item_id: uuid.UUID,
        *,
        hs_code: str | None,
        confidence: float,
        reasoning: str,
        requires_manual_review: bool,
        alternatives: list[dict[str, Any]],
    ) -> ClassificationResult:
        """A reclassify overwrites the existing row in place — one classification per
        line item, never a growing history (the user_override fields are untouched
        here, so an override always survives a later reclassify)."""
        result = await self._session.execute(
            select(ClassificationResult).where(ClassificationResult.line_item_id == line_item_id)
        )
        classification = result.scalar_one_or_none()
        if classification is None:
            classification = ClassificationResult(line_item_id=line_item_id)
            self._session.add(classification)

        classification.hs_code = hs_code
        classification.confidence = confidence
        classification.reasoning = reasoning
        classification.requires_manual_review = requires_manual_review
        classification.alternatives = alternatives
        await self._session.flush()
        return classification
