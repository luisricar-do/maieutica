"""
Streaming SSE do tutor: roteamento → (analista opcional) → RAG/estrag. → tokens do comunicador + ``done``.
"""

import json
import logging
from collections.abc import AsyncIterator
from typing import Any, cast

from agents.graph import analyst_node, rag_retrieve_node, strategist_node
from agents.router import run_router
from agents.tutor import run_communicator_stream
from services.tutor_help import build_tutor_meta_from_actions, parse_help_payload

logger = logging.getLogger(__name__)

# Diagnóstico mínimo quando o analista não corre (CASUAL / THEORY); compatível com o cliente IDE.
_MINIMAL_SSE_DIAGNOSIS: dict[str, str] = {"errorType": "none", "severity": "low"}


def _communicator_stream_kwargs(state: dict[str, Any], intent: str, documentation_context: list[str]) -> dict[str, Any]:
    return {
        "intent": intent,
        "documentation_context": documentation_context,
        "student_name": str(state.get("student_name") or ""),
        "hint_level": int(state.get("hint_level") or 1),
        "cursor_line": state.get("cursor_line"),
        "cursor_column": state.get("cursor_column"),
        "ast_summary": str(state.get("ast_summary") or ""),
        "data_flow_context": str(state.get("data_flow_context") or ""),
    }


def format_sse(event: str | None, data: dict[str, Any]) -> bytes:
    """Uma mensagem SSE (``event`` opcional + uma linha ``data`` JSON)."""
    payload = json.dumps(data, ensure_ascii=False)
    parts: list[str] = []
    if event:
        parts.append(f"event: {event}")
    parts.append(f"data: {payload}")
    parts.append("")
    parts.append("")
    return "\n".join(parts).encode("utf-8")


async def iter_help_sse(payload: Any) -> AsyncIterator[bytes]:
    """
    Gera bytes SSE. Em erro de validação ou falha interna, emite ``event: error`` e encerra.
    """
    initial, err_body, status = parse_help_payload(payload)
    if initial is None:
        assert err_body is not None
        yield format_sse(
            "error",
            {"status": status, "error": err_body.get("error", "Erro na requisição.")},
        )
        return

    try:
        state: dict[str, Any] = dict(initial)
        state.update(await run_router(state))
        intent = state.get("intent") or "DEBUG"

        if intent == "CASUAL":
            yield format_sse("diagnosis", dict(_MINIMAL_SSE_DIAGNOSIS))
            async for delta in run_communicator_stream(
                state["strategist_plan"],
                state["history"],
                **_communicator_stream_kwargs(state, "CASUAL", []),
            ):
                yield format_sse("token", {"text": delta})
            yield format_sse("done", {"tutorMeta": build_tutor_meta_from_actions([])})
            return

        if intent == "THEORY":
            yield format_sse("diagnosis", dict(_MINIMAL_SSE_DIAGNOSIS))
            state.update(await rag_retrieve_node(cast(Any, state)))
            async for delta in run_communicator_stream(
                state["strategist_plan"],
                state["history"],
                **_communicator_stream_kwargs(state, "THEORY", state.get("documentation_context") or []),
            ):
                yield format_sse("token", {"text": delta})
            yield format_sse("done", {"tutorMeta": build_tutor_meta_from_actions([])})
            return

        state.update(await analyst_node(cast(Any, state)))
        yield format_sse("diagnosis", state["diagnosis"])
        state.update(await rag_retrieve_node(cast(Any, state)))
        state.update(await strategist_node(cast(Any, state)))
        actions = state["actions"]
        for action in actions:
            yield format_sse("action", action)
        async for delta in run_communicator_stream(
            state["strategist_plan"],
            state["history"],
            **_communicator_stream_kwargs(state, "DEBUG", state.get("documentation_context") or []),
        ):
            yield format_sse("token", {"text": delta})
        yield format_sse("done", {"tutorMeta": build_tutor_meta_from_actions(actions)})
    except Exception:
        logger.exception("Falha no streaming SSE (/help/stream)")
        yield format_sse(
            "error",
            {"status": 500, "error": "Erro interno ao gerar a resposta."},
        )
