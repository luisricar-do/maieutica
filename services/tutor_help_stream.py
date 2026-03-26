"""
Streaming SSE do tutor: analista (evento único) + tokens do LLM (eventos ``token``) + ``done``.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any, cast

from agents.analyst import Diagnosis, run_analyst
from agents.rag.query import build_rag_query, retrieve_doc_chunks
from agents.tutor import run_tutor_stream
from services.tutor_help import parse_help_payload

logger = logging.getLogger(__name__)


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
        diagnosis = await run_analyst(initial["code"], initial["errors"])
        yield format_sse("diagnosis", diagnosis)
        d = cast(Diagnosis, diagnosis)
        if initial.get("include_documentation"):
            query = build_rag_query(d, initial["errors"], initial["history"])
            doc_ctx = await asyncio.to_thread(retrieve_doc_chunks, query)
        else:
            doc_ctx = []
        async for delta in run_tutor_stream(
            d,
            initial["history"],
            initial["code"],
            initial["active_tutor_decorations"],
            documentation_context=doc_ctx,
        ):
            if isinstance(delta, str):
                yield format_sse("token", {"text": delta})
            else:
                yield format_sse("action", delta)
        yield format_sse("done", {})
    except Exception:
        logger.exception("Falha no streaming SSE (/help/stream)")
        yield format_sse(
            "error",
            {"status": 500, "error": "Erro interno ao gerar a resposta."},
        )
