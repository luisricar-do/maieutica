import json
import logging
from typing import Literal, NotRequired, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage

from agents.llm import create_chat_client

logger = logging.getLogger(__name__)

ANALYST_SYSTEM_PROMPT = """Você é um analisador técnico de código Portugol.
Sua ÚNICA função é retornar um diagnóstico estruturado em JSON.
Você NUNCA se comunica diretamente com o aluno.

Dado o código e as mensagens de erro, retorne SOMENTE um JSON com esta estrutura:
{
  "errorType": "syntax" | "logic" | "infinite_loop" | "none",
  "errorLine": número ou null,
  "affectedVariable": string ou null,
  "errorDescription": "descrição técnica em português",
  "hintAngle": "uma pergunta que poderia levar o aluno a descobrir o erro por conta própria",
  "severity": "low" | "medium" | "high"
}

Retorne APENAS o JSON. Sem texto adicional. Sem markdown. Sem blocos de código."""


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

    errors_block = "\n".join(f"- {e}" for e in errors) if errors else "(nenhuma mensagem de erro)"
    human_content = f"""Código Portugol:
```
{code}
```

Mensagens de erro do compilador:
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
