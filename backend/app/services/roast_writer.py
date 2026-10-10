"""Roast generation: analysis JSON in, moderated RoastResult out."""

import json
import logging
from pathlib import Path
from typing import Any, cast

from openai import AsyncOpenAI
from openai.types.shared_params import ResponseFormatJSONSchema
from pydantic import BaseModel, ConfigDict, ValidationError

from app.config import settings
from app.schemas.pipeline import AnalysisResult, RoastResult
from app.services import moderation, openai_common

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "roast_tamil.md"
DEFAULT_MODEL = openai_common.DEFAULT_MODEL
VALID_LEVELS = ("mild", "medium", "savage")
VALID_STYLES = ("tamil_script", "tanglish")

SAFER_INSTRUCTION = (
    "IMPORTANT: a previous draft was flagged by a content filter. Write a much gentler version: "
    "mild teasing only, no profanity, no insults, nothing aimed at a person. Focus on the code."
)


class _LLMRoast(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    roast_text: str
    one_liner: str
    fixes: list[str]


class _RoastRefused(Exception):
    """The model refused to write a roast."""


def get_client() -> AsyncOpenAI:
    """Build an OpenAI client from settings (patched in tests)."""
    return openai_common.build_client()


def _model_name() -> str:
    return openai_common.model_name()


def llm_schema() -> dict[str, Any]:
    """JSON schema for strict structured outputs."""
    return _LLMRoast.model_json_schema()


def build_user_message(analysis: AnalysisResult, level: str, style: str) -> str:
    """Build the roast input: only the analysis JSON plus level and style."""
    payload = analysis.model_dump(
        exclude={"model", "prompt_tokens", "completion_tokens"}, mode="json"
    )
    return json.dumps({"level": level, "style": style, "review": payload}, ensure_ascii=False)


def _flatten(roast: _LLMRoast | RoastResult) -> str:
    return "\n".join([roast.title, roast.roast_text, roast.one_liner, *roast.fixes])


async def _generate(analysis: AnalysisResult, level: str, style: str, safer: bool) -> _LLMRoast:
    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    if safer:
        system_prompt = f"{system_prompt}\n\n{SAFER_INSTRUCTION}"
    client = get_client()
    response = await client.chat.completions.create(
        model=_model_name(),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": build_user_message(analysis, level, style)},
        ],
        response_format=cast(
            "ResponseFormatJSONSchema",
            openai_common.strict_response_format("roast_result", llm_schema()),
        ),
        max_completion_tokens=settings.ROAST_MAX_COMPLETION_TOKENS,
    )
    usage = getattr(response, "usage", None)
    if usage is not None:
        logger.info(
            "Roast generated prompt_tokens=%s completion_tokens=%s",
            usage.prompt_tokens,
            usage.completion_tokens,
        )
    if openai_common.refusal(response):
        logger.warning("Model refused to write a roast")
        raise _RoastRefused
    if openai_common.finish_reason(response) == "length":
        logger.error(
            "Roast output hit max_completion_tokens=%d (safer=%s)",
            settings.ROAST_MAX_COMPLETION_TOKENS,
            safer,
        )
        raise ValueError("roast output truncated (finish_reason=length)")
    roast = _LLMRoast.model_validate(json.loads(response.choices[0].message.content or ""))
    roast.fixes = roast.fixes[:5]
    if not roast.fixes:
        raise ValueError("no fixes")
    return roast


def fallback_feedback(analysis: AnalysisResult) -> RoastResult:
    """Plain, non-roast feedback built from the analysis (no LLM text)."""
    ordered = sorted(analysis.issues, key=lambda i: {"high": 0, "medium": 1, "low": 2}[i.severity])
    fixes = [f"{i.file}: {i.problem}" if i.file else i.problem for i in ordered[:5]] or [
        "Add tests, a clear README and a .gitignore to improve the repo."
    ]
    while len(fixes) < 3:
        fixes.append("Review the lowest scoring category and improve it first.")
    strengths = "; ".join(analysis.strengths[:3]) or "none noted"
    return RoastResult(
        title=f"Feedback summary (score {analysis.score}/100)",
        roast_text=f"Overall score: {analysis.score}/100. Strengths: {strengths}.",
        one_liner=f"Scored {analysis.score}/100 - see the fixes below.",
        fixes=fixes,
        model=_model_name(),
        moderated_fallback=True,
    )


def _minimal_feedback(analysis: AnalysisResult) -> RoastResult:
    """Last-resort feedback containing no repo- or model-derived free text."""
    return RoastResult(
        title=f"Feedback summary (score {analysis.score}/100)",
        roast_text=f"Overall score: {analysis.score}/100.",
        one_liner=f"Scored {analysis.score}/100 - see the fixes below.",
        fixes=[
            "Add automated tests for the core logic.",
            "Write a README that explains what the project does and how to run it.",
            "Add a .gitignore and remove committed secrets, build output and dependencies.",
        ],
        model=_model_name(),
        moderated_fallback=True,
    )


async def _is_safe_retry(text: str) -> bool | None:
    """Moderate text, retrying once on API errors; None when moderation is unavailable."""
    for attempt in (1, 2):
        try:
            return await moderation.is_safe(text)
        except Exception as exc:
            logger.warning("Moderation call failed (attempt %d): %s", attempt, exc)
    return None


async def _safe_fallback(analysis: AnalysisResult) -> RoastResult:
    """Fallback feedback that has itself passed moderation (or a neutral minimal one)."""
    feedback = fallback_feedback(analysis)
    verdict = await _is_safe_retry(_flatten(feedback))
    if verdict is False:
        logger.warning("Fallback feedback flagged by moderation; using minimal feedback")
        return _minimal_feedback(analysis)
    return feedback


async def write_roast(analysis: AnalysisResult, level: str, style: str) -> RoastResult:
    """Generate a moderated roast; fall back to plain feedback if it stays unsafe."""
    if level not in VALID_LEVELS:
        raise ValueError(f"invalid level: {level}")
    if style not in VALID_STYLES:
        raise ValueError(f"invalid style: {style}")

    for safer in (False, True):
        try:
            roast = await _generate(analysis, level, style, safer)
        except _RoastRefused:
            return await _safe_fallback(analysis)
        except (ValueError, ValidationError) as exc:
            logger.warning("Invalid roast output (safer=%s): %s", safer, exc)
            continue
        verdict = await _is_safe_retry(_flatten(roast))
        if verdict is None:
            logger.error("Moderation unavailable; returning plain feedback instead of a roast")
            return await _safe_fallback(analysis)
        if verdict:
            return RoastResult(
                title=roast.title,
                roast_text=roast.roast_text,
                one_liner=roast.one_liner,
                fixes=roast.fixes,
                model=_model_name(),
                moderated_fallback=False,
            )
        logger.warning("Roast flagged by moderation (safer=%s)", safer)

    return await _safe_fallback(analysis)
