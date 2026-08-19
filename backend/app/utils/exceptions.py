class DomainError(Exception):
    """Base for errors services raise on purpose. Caught once, centrally, by the
    handler registered in app/middleware/error_handling.py and translated into the
    standard {"error": {...}} envelope (architecture doc Section 16) — individual
    route handlers never need their own try/except for these.
    """

    status_code: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ValidationError(DomainError):
    status_code = 400
    code = "VALIDATION_ERROR"


class UnauthenticatedError(DomainError):
    status_code = 401
    code = "UNAUTHENTICATED"


class ForbiddenError(DomainError):
    status_code = 403
    code = "FORBIDDEN"


class NotFoundError(DomainError):
    status_code = 404
    code = "NOT_FOUND"


class ConflictError(DomainError):
    status_code = 409
    code = "CONFLICT"


class UnprocessableError(DomainError):
    status_code = 422
    code = "UNPROCESSABLE"
