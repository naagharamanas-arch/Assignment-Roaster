"""Domain exceptions and their FastAPI handlers."""

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded


class AppError(Exception):
    """Base application error."""

    status_code = 400
    default_detail = "Bad request"

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.default_detail
        super().__init__(self.detail)


class NotFoundError(AppError):
    """Resource not found (404)."""

    status_code = 404
    default_detail = "Not found"


class ConflictError(AppError):
    """Conflicting state (409)."""

    status_code = 409
    default_detail = "Conflict"


class ForbiddenError(AppError):
    """Action not permitted (403)."""

    status_code = 403
    default_detail = "Forbidden"


class RateLimitError(AppError):
    """Usage limit exceeded (429)."""

    status_code = 429
    default_detail = "Rate limit exceeded"


async def app_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Convert an AppError into a JSON response."""
    assert isinstance(exc, AppError)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


def _retry_after_seconds(exc: RateLimitExceeded) -> int:
    """Best-effort seconds until the exceeded limit window resets."""
    try:
        return max(1, int(exc.limit.limit.get_expiry()))  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001 - fall back when slowapi internals differ
        return 60


async def rate_limit_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Return 429 with a human-readable detail and a Retry-After header."""
    assert isinstance(exc, RateLimitExceeded)
    seconds = _retry_after_seconds(exc)
    return JSONResponse(
        status_code=429,
        content={"detail": f"Too many requests, try again in {seconds}s"},
        headers={"Retry-After": str(seconds)},
    )


async def validation_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Return 422 with a string `detail` (first message) plus the full error list."""
    assert isinstance(exc, RequestValidationError)
    errors = jsonable_encoder(exc.errors(), custom_encoder={Exception: str})
    first = errors[0] if errors else {}
    message = str(first.get("msg", "Invalid request"))
    message = message.removeprefix("Value error, ")
    loc = [str(p) for p in first.get("loc", []) if p not in ("body", "query", "path")]
    detail = f"{loc[-1]}: {message}" if loc else message
    return JSONResponse(status_code=422, content={"detail": detail, "errors": errors})


def register_exception_handlers(app: FastAPI) -> None:
    """Attach domain, rate-limit and validation handlers to the app.

    Registered after main.py's slowapi default handler, so this one wins.
    """
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
