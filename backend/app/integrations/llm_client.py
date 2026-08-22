import re
from typing import Any, Protocol

from app.config.settings import get_settings

# Fields a well-formed extraction is expected to surface per document type — drives the
# MockLLMClient's confidence score (matched / expected) so the mock behaves like a real
# extraction call would: partial/garbled text legitimately yields partial confidence,
# never a false-confident 1.0 on an obviously incomplete read.
_EXPECTED_FIELDS: dict[str, tuple[str, ...]] = {
    "commercial_invoice": ("invoice_number", "seller", "buyer", "total_value"),
    "packing_list": ("packing_list_number", "total_packages", "total_gross_weight"),
    "bill_of_lading": ("bl_number", "shipper", "consignee"),
    "air_waybill": ("awb_number", "shipper", "consignee"),
}

_KEY_VALUE_LINE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 ]*):\s*(.+?)\s*$")
_AMOUNT_CURRENCY = re.compile(r"^(\d[\d,]*\.\d{2})\s+([A-Z]{3})$")


class LLMClient(Protocol):
    """Swappable LLM provider interface — the one abstraction in this codebase that's
    justified up front (architecture doc Section 8), because the LLM provider is the
    one component with a real, near-term reason to change.
    """

    def classify_product(
        self, description: str, candidates: list[dict[str, Any]]
    ) -> dict[str, Any]: ...

    def extract_document_fields(self, raw_text: str, doc_type: str) -> dict[str, Any]: ...


class MockLLMClient:
    """Deterministic stand-in for local dev/testing. Never calls a real LLM API, so
    development never burns real API credits or requires live credentials (architecture
    doc Section 13).

    extract_document_fields does real, deterministic "key: value" line parsing rather
    than always returning an empty result — this lets the Phase 2 extraction pipeline
    (confidence threshold, needs_manual_review routing, manual-correction flow) be
    exercised end-to-end against realistic fixture documents without a live LLM key.
    A garbled/near-empty raw_text (e.g. from a scanned document our mock OCR can't
    read) still legitimately produces low confidence, exactly as a real provider would.
    """

    def classify_product(
        self, description: str, candidates: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return {
            "hs_code": None,
            "confidence": 0.0,
            "reasoning": "MockLLMClient stub — no real classification performed.",
            "requires_manual_review": True,
        }

    def extract_document_fields(self, raw_text: str, doc_type: str) -> dict[str, Any]:
        if not raw_text.strip():
            return {"fields": {}, "confidence": 0.0}

        fields: dict[str, Any] = {}
        for line in raw_text.splitlines():
            match = _KEY_VALUE_LINE.match(line)
            if not match:
                continue
            key = match.group(1).strip().lower().replace(" ", "_")
            value = match.group(2).strip()
            amount_match = _AMOUNT_CURRENCY.match(value)
            if amount_match:
                fields[key] = {"amount": amount_match.group(1), "currency": amount_match.group(2)}
            else:
                fields[key] = value

        expected = _EXPECTED_FIELDS.get(doc_type, ())
        if not expected:
            confidence = 0.0
        else:
            matched = sum(1 for name in expected if fields.get(name))
            confidence = round(matched / len(expected), 2)

        return {"fields": fields, "confidence": confidence}


def get_llm_client() -> LLMClient:
    settings = get_settings()
    if settings.llm_provider == "mock":
        return MockLLMClient()
    # Real providers (e.g. Claude) are wired up starting Phase 3, when classification
    # needs one — failing loudly here beats silently falling back to the mock.
    raise NotImplementedError(f"Unsupported LLM_PROVIDER: {settings.llm_provider!r}")
