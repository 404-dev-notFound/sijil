import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# backend/app/repositories/cepa_rules_repository.py -> parents[3] is the repo root,
# where data/ lives alongside backend/, frontend/, docs/ (architecture doc Section 7).
_RULES_FILE = Path(__file__).resolve().parents[3] / "data" / "cepa_rules" / "rules_v1.json"


@dataclass(frozen=True)
class CepaRule:
    agreement: str
    origin_country: str
    destination_country: str
    hs_code_prefixes: tuple[str, ...]
    regional_value_content_threshold_percent: int
    required_documents: tuple[str, ...]
    duty_rate_without_percent: int
    duty_rate_with_percent: int
    source: str


class CepaRulesRepository:
    """Reads CEPA rules-of-origin data from the versioned data file under
    data/cepa_rules/ — same rationale and file-backed (not database-backed) pattern
    as PermitRulesRepository (architecture doc Section 23 / CLAUDE.md's "Do Not Do
    This" rules): auditable and editable without a code deploy.

    rules_v1.json currently holds 2 clearly-labeled illustrative agreements
    (UAE-India CEPA, UAE-Indonesia CEPA — the implementation plan's own suggested
    starting candidates) covering a handful of HS headings — NOT the real researched
    rules-of-origin data the plan's Track B calls for. This module's accuracy is only
    as good as this file's completeness — an ongoing operational responsibility, not
    a one-time engineering task (architecture doc Section 6.4).
    """

    def __init__(self) -> None:
        self._rules = _load_rules()

    def find_matching(
        self, *, hs_code: str, origin_country: str | None, destination_country: str | None
    ) -> CepaRule | None:
        if not origin_country or not destination_country:
            return None
        normalized_hs = hs_code.replace(".", "").replace(" ", "")
        for rule in self._rules:
            if (
                rule.origin_country.casefold() == origin_country.casefold()
                and rule.destination_country.casefold() == destination_country.casefold()
                and any(
                    normalized_hs.startswith(prefix.replace(".", ""))
                    for prefix in rule.hs_code_prefixes
                )
            ):
                return rule
        return None


@lru_cache
def _load_rules() -> tuple[CepaRule, ...]:
    raw = json.loads(_RULES_FILE.read_text(encoding="utf-8"))
    return tuple(
        CepaRule(
            agreement=entry["agreement"],
            origin_country=entry["origin_country"],
            destination_country=entry["destination_country"],
            hs_code_prefixes=tuple(entry["hs_code_prefixes"]),
            regional_value_content_threshold_percent=entry[
                "regional_value_content_threshold_percent"
            ],
            required_documents=tuple(entry["required_documents"]),
            duty_rate_without_percent=entry["duty_rate_without_percent"],
            duty_rate_with_percent=entry["duty_rate_with_percent"],
            source=entry.get("source", "unknown"),
        )
        for entry in raw
    )
