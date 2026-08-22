from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

# Below this length, a PDF's embedded text layer is treated as absent (a scanned PDF
# with no OCR text layer typically extracts to "" or near-empty noise) — the caller
# falls back to OCR rather than trusting a near-empty native read.
MIN_NATIVE_TEXT_CHARS = 20


def extract_native_pdf_text(file_bytes: bytes) -> str:
    """Reads the PDF's embedded text layer directly — no OCR needed for native-text
    PDFs (architecture doc Section 11.1: OCR only runs "if scanned"). Any parse failure
    (corrupt/malformed PDF) is treated the same as "no native text found" so the caller
    falls back to OCR rather than crashing the extraction pipeline.
    """
    try:
        reader = PdfReader(BytesIO(file_bytes))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except (PdfReadError, KeyError, ValueError):
        return ""
