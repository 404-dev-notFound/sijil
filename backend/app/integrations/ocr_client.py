from typing import Protocol


class OCRClient(Protocol):
    """Swappable OCR provider interface, mirroring LLMClient (architecture doc Section 13)."""

    def extract_text(self, file_bytes: bytes, content_type: str) -> str: ...


class MockOCRClient:
    """Deterministic stand-in for local dev/testing. Never calls a real OCR API."""

    def extract_text(self, file_bytes: bytes, content_type: str) -> str:
        return ""
