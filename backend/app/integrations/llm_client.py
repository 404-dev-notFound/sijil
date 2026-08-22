import re
from typing import Any, Protocol

import anthropic
from pydantic import BaseModel, Field

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
_LINE_ITEM_LINE = re.compile(
    r"^\s*Line Item:\s*(?P<description>.+?)\s*\|\s*Qty:\s*(?P<quantity>[\d.,]+)"
    r"\s*\|\s*Unit Value:\s*(?P<amount>\d[\d,]*\.\d{2})\s+(?P<currency>[A-Z]{3})\s*$"
)


def _compute_field_confidence(doc_type: str, fields: dict[str, Any]) -> float:
    """Shared by every LLMClient implementation (mock and real) so a document's
    confidence always means the same thing regardless of provider: the fraction of
    that doc_type's expected fields the extraction actually populated — not a number
    the model self-reports. Self-reported extraction confidence isn't reliably
    calibrated; a measured completeness ratio is.
    """
    expected = _EXPECTED_FIELDS.get(doc_type, ())
    if not expected:
        return 0.0
    matched = sum(1 for name in expected if fields.get(name))
    return round(matched / len(expected), 2)


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
    than always returning an empty result — this lets the document-extraction pipeline
    (confidence threshold, needs_manual_review routing, manual-correction flow) be
    exercised end-to-end against realistic fixture documents without a live LLM key.

    classify_product picks the nearest real vector-search candidate (vector search
    itself is real — local embeddings + real pgvector cosine distance, see
    app/integrations/embedding_client.py) rather than doing GRI reasoning — enough to
    exercise the classification pipeline's mechanics (thresholding, override/reclassify)
    without a live LLM key. It does NOT validate real classification accuracy; that
    needs LLM_PROVIDER=claude and a real key (see ClaudeLLMClient).
    """

    def classify_product(
        self, description: str, candidates: list[dict[str, Any]]
    ) -> dict[str, Any]:
        if not candidates:
            return {
                "hs_code": None,
                "confidence": 0.0,
                "reasoning": "No tariff heading candidates found in the knowledge base "
                "for this description.",
                "alternatives": [],
            }

        ranked = sorted(candidates, key=lambda c: c.get("distance", 1.0))
        top = ranked[0]
        return {
            "hs_code": top["hs_code"],
            "confidence": _distance_to_confidence(top.get("distance", 1.0)),
            "reasoning": "MockLLMClient stub — nearest vector-search match by "
            "description similarity; no GRI reasoning performed.",
            "alternatives": [
                {
                    "hs_code": candidate["hs_code"],
                    "confidence": _distance_to_confidence(candidate.get("distance", 1.0)),
                }
                for candidate in ranked[1:4]
            ],
        }

    def extract_document_fields(self, raw_text: str, doc_type: str) -> dict[str, Any]:
        if not raw_text.strip():
            return {"fields": {}, "confidence": 0.0}

        fields: dict[str, Any] = {}
        line_items: list[dict[str, Any]] = []
        for line in raw_text.splitlines():
            item_match = _LINE_ITEM_LINE.match(line)
            if item_match:
                line_items.append(
                    {
                        "description": item_match.group("description"),
                        "quantity": item_match.group("quantity"),
                        "unit_value": {
                            "amount": item_match.group("amount"),
                            "currency": item_match.group("currency"),
                        },
                    }
                )
                continue

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

        if line_items:
            fields["line_items"] = line_items

        return {"fields": fields, "confidence": _compute_field_confidence(doc_type, fields)}


def _distance_to_confidence(distance: float) -> float:
    return round(max(0.0, min(1.0, 1.0 - distance)), 2)


# --- Real Claude-backed implementation -------------------------------------------


class _MoneyAmount(BaseModel):
    amount: str
    currency: str


class _ExtractedLineItem(BaseModel):
    description: str
    quantity: str | None = None
    unit_value: _MoneyAmount | None = None


class _ExtractedDocumentFields(BaseModel):
    """Covers all four document types (API SPEC Section 7) — only the fields relevant
    to the given doc_type are expected to be populated; the rest stay null."""

    invoice_number: str | None = None
    seller: str | None = None
    buyer: str | None = None
    total_value: _MoneyAmount | None = None
    packing_list_number: str | None = None
    total_packages: str | None = None
    total_gross_weight: str | None = None
    bl_number: str | None = None
    awb_number: str | None = None
    shipper: str | None = None
    consignee: str | None = None
    line_items: list[_ExtractedLineItem] = Field(default_factory=list)


class _AlternativeClassification(BaseModel):
    hs_code: str
    confidence: float = Field(ge=0, le=1)


class _ClassificationResult(BaseModel):
    hs_code: str | None
    confidence: float = Field(ge=0, le=1)
    reasoning: str
    alternatives: list[_AlternativeClassification] = Field(default_factory=list)


_EXTRACTION_SYSTEM_PROMPT = (
    "You extract structured fields from raw shipping-document text (OCR or native PDF "
    "text, may be noisy). Only populate fields relevant to the given document type; "
    "leave everything else null. Never invent a value that isn't actually present in "
    "the text — leave the field null instead. For commercial invoices, populate "
    "line_items with every distinct product line you can find."
)

_CLASSIFICATION_SYSTEM_PROMPT = (
    "You are a customs classification expert applying the WCO Harmonized System "
    "General Rules of Interpretation (GRI) to classify a product against a shortlist "
    "of candidate tariff headings retrieved by vector search. Pick the single best "
    "matching hs_code from the candidate list only — never invent a code that isn't in "
    "the candidates. If no candidate is a reasonable match (e.g. a genuinely novel "
    "product, or a composite good the GRI rules can't cleanly resolve from this "
    "shortlist), set hs_code to null and give confidence a low score reflecting that "
    "uncertainty — never return a confident-looking guess. confidence should reflect "
    "your genuine certainty in the GRI-based reasoning, not just similarity."
)


class ClaudeLLMClient:
    """Real LLM provider backed by the Anthropic Claude API. Selected via
    LLM_PROVIDER=claude + LLM_API_KEY (get_llm_client() below) — swaps in for
    MockLLMClient with no change to any calling code (architecture doc Section 8).
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._client = anthropic.Anthropic(api_key=settings.llm_api_key)
        self._model = settings.llm_model

    def extract_document_fields(self, raw_text: str, doc_type: str) -> dict[str, Any]:
        if not raw_text.strip():
            return {"fields": {}, "confidence": 0.0}

        response = self._client.messages.parse(
            model=self._model,
            max_tokens=4096,
            system=_EXTRACTION_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Document type: {doc_type}\n\nDocument text:\n{raw_text}",
                }
            ],
            output_format=_ExtractedDocumentFields,
        )
        parsed = response.parsed_output
        if parsed is None:
            raise ValueError("Claude returned no parsed structured output for extraction.")
        fields = parsed.model_dump(exclude_none=True, exclude_defaults=True)
        return {"fields": fields, "confidence": _compute_field_confidence(doc_type, fields)}

    def classify_product(
        self, description: str, candidates: list[dict[str, Any]]
    ) -> dict[str, Any]:
        if not candidates:
            return {
                "hs_code": None,
                "confidence": 0.0,
                "reasoning": "No tariff heading candidates found in the knowledge base "
                "for this description.",
                "alternatives": [],
            }

        candidate_list = "\n".join(
            f"- {candidate['hs_code']}: {candidate['description']}" for candidate in candidates
        )
        response = self._client.messages.parse(
            model=self._model,
            max_tokens=2048,
            system=_CLASSIFICATION_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Product description: {description}\n\n"
                        f"Candidate tariff headings:\n{candidate_list}"
                    ),
                }
            ],
            output_format=_ClassificationResult,
        )
        parsed = response.parsed_output
        if parsed is None:
            raise ValueError("Claude returned no parsed structured output for classification.")
        return {
            "hs_code": parsed.hs_code,
            "confidence": parsed.confidence,
            "reasoning": parsed.reasoning,
            "alternatives": [alt.model_dump() for alt in parsed.alternatives],
        }


def get_llm_client() -> LLMClient:
    settings = get_settings()
    if settings.llm_provider == "mock":
        return MockLLMClient()
    if settings.llm_provider == "claude":
        return ClaudeLLMClient()
    raise NotImplementedError(f"Unsupported LLM_PROVIDER: {settings.llm_provider!r}")
