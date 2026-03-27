import json
import logging
from typing import Literal, NotRequired, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage

from agents.llm import create_chat_client

logger = logging.getLogger(__name__)

ANALYST_SYSTEM_PROMPT = """You are a technical analyzer for Portugol (Brazilian pseudocode) programs.
Your ONLY job is to return a structured JSON diagnosis. You NEVER speak to the learner directly.

Given the code and compiler error messages, output ONLY a JSON object with this shape:
{
  "errorType": "syntax" | "logic" | "infinite_loop" | "none",
  "errorLine": number or null,
  "affectedVariable": string or null,
  "errorDescription": "short technical description",
  "hintAngle": "a question that could help the learner discover the issue",
  "severity": "low" | "medium" | "high"
}

Language rules for string fields:
- Write **errorDescription** and **hintAngle** in **Portuguese** (they inform a Portuguese-speaking tutor experience).

Guidelines for hintAngle and errorDescription:
- For **string** issues (mismatched quotes, mixing `"` and `'`, wrong delimiter such as an accent, missing quotes where needed): hintAngle should steer toward **comparing the character that opens and the one that closes** the text inside `escreva` (or the literal), without giving the exact fix.
- For other errors, keep a concrete question aligned with the symptom (loop, condition, variable), always discovery-oriented.

Return ONLY the JSON. No extra text. No markdown. No code fences."""


class Diagnosis(TypedDict):
    errorType: Literal["syntax", "logic", "infinite_loop", "none"]
    errorLine: int | None
    affectedVariable: str | None
    errorDescription: str
    hintAngle: str
    severity: Literal["low", "medium", "high"]


class DiagnosisPartial(TypedDict, total=False):
    """Campos opcionais ao validar JSON parcial do modelo."""

    errorType: str
    errorLine: NotRequired[int | None]
    affectedVariable: NotRequired[str | None]
    errorDescription: NotRequired[str]
    hintAngle: NotRequired[str]
    severity: NotRequired[str]


def _default_diagnosis() -> Diagnosis:
    return {
        "errorType": "none",
        "errorLine": None,
        "affectedVariable": None,
        "errorDescription": "",
        "hintAngle": "",
        "severity": "low",
    }


def _parse_diagnosis(raw: str) -> Diagnosis:
    text = raw.strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Resposta do analista não é um objeto JSON")

    partial: DiagnosisPartial = data  # type: ignore[assignment]
    error_type = partial.get("errorType", "none")
    if error_type not in ("syntax", "logic", "infinite_loop", "none"):
        error_type = "none"

    severity = partial.get("severity", "low")
    if severity not in ("low", "medium", "high"):
        severity = "low"

    return {
        "errorType": error_type,  # type: ignore[typeddict-item]
        "errorLine": partial.get("errorLine"),
        "affectedVariable": partial.get("affectedVariable"),
        "errorDescription": partial.get("errorDescription", ""),
        "hintAngle": partial.get("hintAngle", ""),
        "severity": severity,  # type: ignore[typeddict-item]
    }


async def run_analyst(code: str, errors: list[str]) -> dict:
    llm = create_chat_client(max_tokens=512, temperature=0)

    errors_block = "\n".join(f"- {e}" for e in errors) if errors else "(no compiler error messages)"
    human_content = f"""Portugol code:
```
{code}
```

Compiler error messages:
{errors_block}
"""

    messages = [
        SystemMessage(content=ANALYST_SYSTEM_PROMPT),
        HumanMessage(content=human_content),
    ]

    response = await llm.ainvoke(messages)
    content = response.content
    if isinstance(content, list):
        text = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    else:
        text = str(content)

    try:
        return _parse_diagnosis(text)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.exception("Falha ao interpretar JSON do analista: %s", exc)
        return _default_diagnosis()
