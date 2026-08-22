from io import BytesIO

from reportlab.pdfgen import canvas

# Test-only helper — generates real native-text PDFs so the extraction pipeline's
# "does this PDF have an embedded text layer" branch (app/utils/pdf_text.py) is
# exercised against genuine PDF structure, not a hand-rolled fake header.


def build_text_pdf(pages: list[list[str]]) -> bytes:
    """One page per inner list of lines. Splitting fields across pages (rather than
    always putting everything on page 1) is what proves multi-page text concatenation
    actually works end to end."""
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    for lines in pages:
        y = 750
        for line in lines:
            pdf.drawString(72, y, line)
            y -= 20
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def fake_scanned_image_bytes() -> bytes:
    """Magic-byte-valid JPEG bytes with no real image data — enough to pass the
    upload's content-type sniff (app/utils/file_validation.py) and route through the
    OCR path. MockOCRClient ignores the actual bytes, so no real image is needed."""
    return b"\xff\xd8\xff\xe0" + b"\x00" * 64
