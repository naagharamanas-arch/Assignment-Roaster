"""Content moderation via the OpenAI moderation endpoint."""

import logging

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

MODERATION_MODEL = "omni-moderation-latest"


def get_client() -> AsyncOpenAI:
    """Build an OpenAI client from settings (patched in tests)."""
    return AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        timeout=settings.OPENAI_TIMEOUT_SECONDS,
        max_retries=1,
    )


async def is_safe(text: str) -> bool:
    """Return True when the text is not flagged by OpenAI moderation."""
    if not text.strip():
        return True
    client = get_client()
    response = await client.moderations.create(model=MODERATION_MODEL, input=text)
    flagged = any(result.flagged for result in response.results)
    if flagged:
        logger.warning("Moderation flagged generated text")
    return not flagged


async def flag_each(texts: list[str]) -> list[bool]:
    """Moderate several texts in one call; returns a flagged boolean per input."""
    indexes = [i for i, t in enumerate(texts) if t.strip()]
    flags = [False] * len(texts)
    if not indexes:
        return flags
    client = get_client()
    response = await client.moderations.create(
        model=MODERATION_MODEL, input=[texts[i] for i in indexes]
    )
    results = list(response.results)
    if len(results) != len(indexes):
        # Cannot align results; treat everything as flagged (fail closed).
        logger.warning("Moderation result count mismatch")
        return [True] * len(texts)
    for index, result in zip(indexes, results, strict=True):
        flags[index] = bool(result.flagged)
    return flags
