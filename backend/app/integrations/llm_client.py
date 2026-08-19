from typing import Any, Protocol


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
    doc Section 13). Always reports low confidence — callers must never treat a mock
    result as a real classification.
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
        return {"fields": {}, "confidence": 0.0}
