"""Roteamento de intenção: classificação rápida antes do grafo principal."""

from __future__ import annotations

import unicodedata
from enum import Enum
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agents.llm import create_chat_client

ROUTER_SYSTEM = """Classify the user's intent into exactly one label:
CASUAL — greeting, thanks, goodbye, small talk (no programming help).
THEORY — conceptual question about programming or Portugol (what is X, how does Y work).
DEBUG — fixing code, understanding errors, or debugging.
OUT_OF_SCOPE — unrelated to programming, Portugol, the IDE, or the learner's code (e.g. celebrity biographies, general trivia, sports, politics).

Use the latest user message. If history is empty, prefer DEBUG if there are compiler/runtime errors listed; else use code presence as weak hint for DEBUG vs THEORY.
If the user asks an unrelated factual question, choose OUT_OF_SCOPE even if code is present."""

CASUAL_STRATEGIST_PLAN = (
    "Respond warmly as ADA: brief, friendly, no code debugging unless the user asks."
)

OUT_OF_SCOPE_STRATEGIST_PLAN = (
    "Redirect briefly: ADA only helps with Portugol, programming logic, and the open code. "
    "Do not answer the unrelated factual question."
)

_PROGRAMMING_TERMS = frozenset(
    {
        "algoritmo",
        "codigo",
        "compilador",
        "debug",
        "erro",
        "funcao",
        "ide",
        "laco",
        "linha",
        "loop",
        "portugol",
        "programa",
        "programacao",
        "variavel",
    }
)

_CLEAR_OUT_OF_SCOPE_TERMS = frozenset(
    {
        "biografia",
        "einstein",
        "futebol",
        "historia",
        "piada",
        "politica",
        "receita",
    }
)


class IntentLabel(str, Enum):
    CASUAL = "CASUAL"
    THEORY = "THEORY"
    DEBUG = "DEBUG"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class IntentClassification(BaseModel):
    intent: IntentLabel = Field(description="Single intent label for routing.")


def _create_router_llm():
    return create_chat_client(max_tokens=96, temperature=0.0)


def _last_user_content(history: list[dict]) -> str:
    for h in reversed(history):
        if isinstance(h, dict) and h.get("role") == "user":
            return str(h.get("content", "")).strip()
    return ""


def _normalize_for_rules(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _has_any_term(text: str, terms: frozenset[str]) -> bool:
    return any(term in text for term in terms)


def _looks_deterministically_out_of_scope(message: str) -> bool:
    normalized = _normalize_for_rules(message)
    if not normalized:
        return False

    if _has_any_term(normalized, _PROGRAMMING_TERMS):
        return False

    if _has_any_term(normalized, _CLEAR_OUT_OF_SCOPE_TERMS):
        return True

    return any(
        phrase in normalized
        for phrase in (
            "conte uma",
            "conta uma",
            "me conte",
            "quem foi",
            "quem e",
            "quem era",
        )
    )


def _router_user_payload(state: dict[str, Any]) -> str:
    parts: list[str] = []
    last = _last_user_content(state.get("history") or [])
    if last:
        parts.append(f"Última mensagem do aluno:\n{last}")
    code = str(state.get("code") or "").strip()
    if code:
        preview = code[:2000] + ("…" if len(code) > 2000 else "")
        parts.append(f"Código no editor (trecho):\n{preview}")
    errors = state.get("errors") or []
    if errors:
        parts.append("Erros reportados:\n" + "\n".join(str(e) for e in errors[:12]))
    if not parts:
        parts.append("(Sem mensagem nem contexto; classificar pelo melhor palpite.)")
    return "\n\n".join(parts)


async def run_router(state: dict[str, Any]) -> dict[str, Any]:
    """Classifica intenção e, se CASUAL, preenche plano/ações para o tutor sem estrategista."""
    if _looks_deterministically_out_of_scope(
        _last_user_content(state.get("history") or [])
    ):
        return {
            "intent": "OUT_OF_SCOPE",
            "strategist_plan": OUT_OF_SCOPE_STRATEGIST_PLAN,
            "actions": [],
        }

    structured_llm = _create_router_llm().with_structured_output(IntentClassification)
    messages = [
        SystemMessage(content=ROUTER_SYSTEM),
        HumanMessage(content=_router_user_payload(state)),
    ]
    result = await structured_llm.ainvoke(messages)
    assert isinstance(result, IntentClassification)
    intent = result.intent.value
    out: dict[str, Any] = {"intent": intent}
    if intent == "CASUAL":
        out["strategist_plan"] = CASUAL_STRATEGIST_PLAN
        out["actions"] = []
    if intent == "OUT_OF_SCOPE":
        out["strategist_plan"] = OUT_OF_SCOPE_STRATEGIST_PLAN
        out["actions"] = []
    return out
