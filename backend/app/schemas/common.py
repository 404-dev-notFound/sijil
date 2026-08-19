from pydantic import BaseModel


class PaginatedResponse[T](BaseModel):
    """Matches the standard paginated envelope in docs/API SPEC.pdf Section 3."""

    items: list[T]
    page: int
    page_size: int
    total_items: int
    total_pages: int

    @classmethod
    def build(
        cls, items: list[T], *, page: int, page_size: int, total_items: int
    ) -> "PaginatedResponse[T]":
        total_pages = (total_items + page_size - 1) // page_size if page_size else 0
        return cls(
            items=items,
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
        )


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, object] = {}


class ErrorResponse(BaseModel):
    """Matches the standard error envelope in architecture doc Section 16 / API SPEC
    Section 2."""

    error: ErrorDetail
