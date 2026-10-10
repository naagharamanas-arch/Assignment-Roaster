"""Shared OpenAI helpers: client construction, model resolution, completion checks."""

import logging
from typing import Any

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o-mini"
_warned_default_model = False


def build_client() -> AsyncOpenAI:
    """Build an OpenAI client with a bounded timeout and a single SDK retry."""
    return AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        timeout=settings.OPENAI_TIMEOUT_SECONDS,
        max_retries=1,
    )


def model_name() -> str:
    """Return the configured model, warning once when falling back to the default."""
    global _warned_default_model
    if settings.OPENAI_MODEL:
        return settings.OPENAI_MODEL
    if not _warned_default_model:
        logger.warning("OPENAI_MODEL is empty; falling back to default model %s", DEFAULT_MODEL)
        _warned_default_model = True
    return DEFAULT_MODEL


def strict_response_format(name: str, schema: dict[str, Any]) -> dict[str, Any]:
    """Wrap a JSON schema as a strict structured-output response_format."""
    return {
        "type": "json_schema",
        "json_schema": {"name": name, "strict": True, "schema": schema},
    }


def finish_reason(response: Any) -> str | None:
    """finish_reason of the first choice, if any."""
    reason = getattr(response.choices[0], "finish_reason", None)
    return reason if isinstance(reason, str) else None


def refusal(response: Any) -> str | None:
    """Model refusal text of the first choice, if any."""
    value = getattr(response.choices[0].message, "refusal", None)
    return value if isinstance(value, str) and value else None
