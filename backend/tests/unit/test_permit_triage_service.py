import uuid

from app.repositories.permit_rules_repository import PermitRule
from app.services.permit_triage_service import _to_permit_requirement


def test_to_permit_requirement_starts_with_empty_applies_to_line_items() -> None:
    rule = PermitRule(
        regulator="TDRA",
        permit_type="Telecom equipment type approval",
        hs_code_prefixes=("8517",),
        estimated_processing_time_days=10,
        reference_link="https://tdra.gov.ae/",
        source="illustrative_seed",
    )

    requirement = _to_permit_requirement(uuid.uuid4(), rule)

    assert requirement.regulator == "TDRA"
    assert requirement.permit_type == "Telecom equipment type approval"
    assert requirement.applies_to_line_items == []
    assert requirement.estimated_processing_time_days == 10
