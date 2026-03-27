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
from services.tutor_help import parse_help_payload

logger = logging.getLogger(__name__)

# Diagnóstico mínimo quando o analista não corre (CASUAL / THEORY); compatível com o cliente IDE.
_MINIMAL_SSE_DIAGNOSIS: dict[str, str] = {"errorType": "none", "severity": "low"}


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
                intent="CASUAL",
                documentation_context=[],
            ):
                yield format_sse("token", {"text": delta})
            yield format_sse("done", {})
            return

        if intent == "THEORY":
            yield format_sse("diagnosis", dict(_MINIMAL_SSE_DIAGNOSIS))
            state.update(await rag_retrieve_node(cast(Any, state)))
            async for delta in run_communicator_stream(
                state["strategist_plan"],
                state["history"],
                intent="THEORY",
                documentation_context=state.get("documentation_context") or [],
            ):
                yield format_sse("token", {"text": delta})
            yield format_sse("done", {})
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
            intent="DEBUG",
            documentation_context=state.get("documentation_context") or [],
        ):
            yield format_sse("token", {"text": delta})
        yield format_sse("done", {})
    except Exception:
        logger.exception("Falha no streaming SSE (/help/stream)")
        yield format_sse(
            "error",
            {"status": 500, "error": "Erro interno ao gerar a resposta."},
        )
