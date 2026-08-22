from decimal import Decimal, InvalidOperation
from typing import Any


def parse_decimal(value: Any) -> Decimal | None:
    """Best-effort parse of an extracted-field value (str, int, float, or already a
    Decimal) into a Decimal, or None if it isn't parseable — used wherever extracted
    document text needs numeric comparison without crashing on a garbled value."""
    if value is None:
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except InvalidOperation:
        return None
