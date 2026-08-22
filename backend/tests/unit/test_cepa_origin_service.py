from decimal import Decimal

from app.models.enums import OriginQualificationStatus
from app.repositories.cepa_rules_repository import CepaRule
from app.services.cepa_origin_service import _evaluate

_RULE = CepaRule(
    agreement="UAE-India CEPA",
    origin_country="India",
    destination_country="UAE",
    hs_code_prefixes=("8517",),
    regional_value_content_threshold_percent=35,
    required_documents=("Preferential Certificate of Origin (India)",),
    duty_rate_without_percent=5,
    duty_rate_with_percent=0,
    source="illustrative_seed",
)


def test_qualifies_when_rvc_exceeds_threshold_and_computes_savings() -> None:
    """The Phase 6 definition of done: a sample shipment with known origin data
    correctly determines CEPA eligibility and estimated savings."""
    evaluation = _evaluate(
        rule=_RULE,
        hs_code="8517.62",
        local_content_value=Decimal("4200.00"),
        total_value=Decimal("10000.00"),
    )

    assert evaluation.qualifies == OriginQualificationStatus.QUALIFIES
    assert "42%" in evaluation.reasoning
    assert "exceeds" in evaluation.reasoning
    assert evaluation.estimated_duty_savings_amount == Decimal("500.00")
    assert evaluation.required_documents == ["Preferential Certificate of Origin (India)"]


def test_does_not_qualify_when_rvc_below_threshold_and_no_savings() -> None:
    evaluation = _evaluate(
        rule=_RULE,
        hs_code="8517.62",
        local_content_value=Decimal("2000.00"),
        total_value=Decimal("10000.00"),
    )

    assert evaluation.qualifies == OriginQualificationStatus.DOES_NOT_QUALIFY
    assert "20%" in evaluation.reasoning
    assert "does not meet" in evaluation.reasoning
    assert evaluation.estimated_duty_savings_amount is None


def test_missing_local_content_value_is_insufficient_data_not_a_false_negative() -> None:
    """architecture doc Section 6.4: missing value-content data must never silently
    default to does_not_qualify — a false negative costs the user real money."""
    evaluation = _evaluate(
        rule=_RULE, hs_code="8517.62", local_content_value=None, total_value=Decimal("10000.00")
    )

    assert evaluation.qualifies == OriginQualificationStatus.INSUFFICIENT_DATA
    assert evaluation.missing_fields == ["local_content_value"]
    assert evaluation.estimated_duty_savings_amount is None


def test_missing_total_value_is_insufficient_data() -> None:
    evaluation = _evaluate(
        rule=_RULE, hs_code="8517.62", local_content_value=Decimal("4200.00"), total_value=None
    )

    assert evaluation.qualifies == OriginQualificationStatus.INSUFFICIENT_DATA
    assert evaluation.missing_fields == ["total_value"]


def test_both_values_missing_lists_both_in_missing_fields() -> None:
    evaluation = _evaluate(
        rule=_RULE, hs_code="8517.62", local_content_value=None, total_value=None
    )

    assert evaluation.qualifies == OriginQualificationStatus.INSUFFICIENT_DATA
    assert set(evaluation.missing_fields) == {"local_content_value", "total_value"}


def test_unclassified_line_item_is_not_applicable() -> None:
    evaluation = _evaluate(rule=None, hs_code=None, local_content_value=None, total_value=None)

    assert evaluation.qualifies == OriginQualificationStatus.NOT_APPLICABLE
    assert "not been classified" in evaluation.reasoning


def test_no_covered_agreement_is_not_applicable_with_a_distinct_reason() -> None:
    evaluation = _evaluate(
        rule=None,
        hs_code="0101.21",
        local_content_value=Decimal("100.00"),
        total_value=Decimal("200.00"),
    )

    assert evaluation.qualifies == OriginQualificationStatus.NOT_APPLICABLE
    assert "No covered CEPA agreement" in evaluation.reasoning
