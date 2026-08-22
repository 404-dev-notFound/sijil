from app.models.classification_result import ClassificationResult
from app.models.line_item import LineItem
from app.services.line_item_helpers import effective_hs_code


def _line_item_with_classification(
    *, hs_code: str | None, user_override_hs_code: str | None = None
) -> LineItem:
    line_item = LineItem(description="irrelevant")
    line_item.classification = ClassificationResult(
        hs_code=hs_code,
        confidence=0.9,
        reasoning="irrelevant",
        requires_manual_review=False,
        user_override_hs_code=user_override_hs_code,
    )
    return line_item


def test_effective_hs_code_prefers_user_override() -> None:
    line_item = _line_item_with_classification(
        hs_code="8471.30", user_override_hs_code="8517.12"
    )

    assert effective_hs_code(line_item) == "8517.12"


def test_effective_hs_code_falls_back_to_ai_suggestion() -> None:
    line_item = _line_item_with_classification(hs_code="8471.30")

    assert effective_hs_code(line_item) == "8471.30"


def test_effective_hs_code_is_none_when_not_classified() -> None:
    line_item = LineItem(description="irrelevant")
    line_item.classification = None

    assert effective_hs_code(line_item) is None


def test_effective_hs_code_is_none_when_hs_code_never_determined() -> None:
    line_item = _line_item_with_classification(hs_code=None)

    assert effective_hs_code(line_item) is None
