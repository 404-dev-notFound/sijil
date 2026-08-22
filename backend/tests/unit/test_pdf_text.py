from app.utils.pdf_text import extract_native_pdf_text
from tests.fixtures.pdf_builder import build_text_pdf


def test_extract_native_pdf_text_reads_embedded_text() -> None:
    pdf_bytes = build_text_pdf([["Invoice Number: INV-2026-0451"]])

    text = extract_native_pdf_text(pdf_bytes)

    assert "Invoice Number: INV-2026-0451" in text


def test_extract_native_pdf_text_concatenates_multiple_pages() -> None:
    pdf_bytes = build_text_pdf([["Page one line"], ["Page two line"]])

    text = extract_native_pdf_text(pdf_bytes)

    assert "Page one line" in text
    assert "Page two line" in text


def test_extract_native_pdf_text_returns_empty_string_for_malformed_pdf() -> None:
    malformed = b"%PDF-1.4\nnot a real pdf structure\n%%EOF"

    text = extract_native_pdf_text(malformed)

    assert text == ""
