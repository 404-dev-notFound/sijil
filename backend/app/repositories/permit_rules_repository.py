import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# backend/app/repositories/permit_rules_repository.py -> parents[3] is the repo root,
# where data/ lives alongside backend/, frontend/, docs/ (architecture doc Section 7).
_RULES_FILE = Path(__file__).resolve().parents[3] / "data" / "permit_rules" / "rules_v1.json"


@dataclass(frozen=True)
class PermitRule:
    regulator: str
    permit_type: str
    hs_code_prefixes: tuple[str, ...]
    estimated_processing_time_days: int
    reference_link: str
    source: str


class PermitRulesRepository:
    """Reads permit rules from the versioned data file under data/permit_rules/ —
    never hardcoded as scattered if-statements, so rules stay auditable and editable
    without a code deploy (architecture doc Section 23 / CLAUDE.md's "Do Not Do This"
    rules). Not database-backed like the other repositories in this codebase: permit
    rules are reference data maintained by editing and reviewing a file, not by
    running a migration.

    rules_v1.json currently holds a small, clearly-labeled illustrative set of ~6
    UAE regulator categories (MOCCAE, MOHAP, TDRA, ESMA/MoIAT, Ministry of Interior) —
    NOT the real researched HS-code-to-regulator mapping the implementation plan's
    Track A calls for. This module's accuracy is only as good as this file's
    completeness — an ongoing operational responsibility, not a one-time engineering
    task (architecture doc Section 6.3).
    """

    def __init__(self) -> None:
        self._rules = _load_rules()

    def find_matching(self, hs_code: str) -> list[PermitRule]:
        normalized = hs_code.replace(".", "").replace(" ", "")
        return [
            rule
            for rule in self._rules
            if any(
                normalized.startswith(prefix.replace(".", ""))
                for prefix in rule.hs_code_prefixes
            )
        ]


@lru_cache
def _load_rules() -> tuple[PermitRule, ...]:
    raw = json.loads(_RULES_FILE.read_text(encoding="utf-8"))
    return tuple(
        PermitRule(
            regulator=entry["regulator"],
            permit_type=entry["permit_type"],
            hs_code_prefixes=tuple(entry["hs_code_prefixes"]),
            estimated_processing_time_days=entry["estimated_processing_time_days"],
            reference_link=entry["reference_link"],
            source=entry.get("source", "unknown"),
        )
        for entry in raw
    )
