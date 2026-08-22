from typing import Protocol

from app.config.settings import get_settings


class OCRClient(Protocol):
    """Swappable OCR provider interface, mirroring LLMClient (architecture doc Section 13)."""

    def extract_text(self, file_bytes: bytes, content_type: str) -> str: ...


class MockOCRClient:
    """Deterministic stand-in for local dev/testing. Never calls a real OCR API.

    Always returns empty text — with no live OCR provider configured, a scanned/image
    document genuinely can't be read reliably, so it should honestly route to
    needs_manual_review rather than pretend to have extracted something (architecture
    doc's "never silently accept a low-confidence guess" rule).
    """

    def extract_text(self, file_bytes: bytes, content_type: str) -> str:
        return ""


def get_ocr_client() -> OCRClient:
    settings = get_settings()
    if settings.ocr_provider == "mock":
        return MockOCRClient()
    raise NotImplementedError(f"Unsupported OCR_PROVIDER: {settings.ocr_provider!r}")
