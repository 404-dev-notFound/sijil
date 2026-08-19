MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20MB, per API SPEC Section 7

# Magic-byte signatures, not just the file extension or client-supplied Content-Type
# header — both are trivially spoofable (architecture doc Section 15).
_MAGIC_SIGNATURES: dict[bytes, str] = {
    b"%PDF-": "application/pdf",
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
}


def sniff_content_type(header_bytes: bytes) -> str | None:
    """Returns the detected MIME type from the file's leading bytes, or None if it
    doesn't match any supported signature."""
    for signature, content_type in _MAGIC_SIGNATURES.items():
        if header_bytes.startswith(signature):
            return content_type
    return None
