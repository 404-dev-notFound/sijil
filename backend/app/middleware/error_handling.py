from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.utils.exceptions import DomainError


async def domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # FastAPI only ever dispatches DomainError (and subclasses) to this handler — see
    # register_error_handlers below. The isinstance check just narrows the type for mypy.
    if not isinstance(exc, DomainError):
        raise exc

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, domain_error_handler)
