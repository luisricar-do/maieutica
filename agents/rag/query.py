"""Consulta ao índice RAG a partir do estado do tutor (erros, diagnóstico, histórico)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agents.analyst import Diagnosis


def build_rag_query(
    diagnosis: Diagnosis,
    errors: list[str],
    history: list[dict],
) -> str:
    """Monta texto de consulta para o retriever (curto, focado no contexto atual)."""
    parts: list[str] = []
    if errors:
        parts.append("Erros: " + "; ".join(str(e) for e in errors[:8]))
    desc = str(diagnosis.get("errorDescription", "")).strip()
    if desc:
        parts.append(desc)
    hint = str(diagnosis.get("hintAngle", "")).strip()
    if hint:
        parts.append(hint)
    for h in reversed(history):
        if isinstance(h, dict) and h.get("role") == "user":
            parts.append(str(h.get("content", "")).strip())
            break
    text = "\n".join(p for p in parts if p)
    return text[:4000]


def build_theory_rag_query(history: list[dict], code: str = "") -> str:
    """Monta consulta para RAG em perguntas teóricas (sem diagnóstico do analista)."""
    parts: list[str] = []
    for h in reversed(history):
        if isinstance(h, dict) and h.get("role") == "user":
            u = str(h.get("content", "")).strip()
            if u:
                parts.append(u)
            break
    if not parts and code.strip():
        preview = code.strip()[:1500]
        parts.append("Contexto do código no editor:\n" + preview)
    text = "\n".join(parts) if parts else ""
    return text[:4000]


def retrieve_doc_chunks(
    query: str,
    k: int = 4,
    *,
    _get_retriever: Callable[[int], Any] | None = None,
) -> list[str]:
    """Recupera fragmentos da documentação; lista vazia se a consulta for vazia.

    ``_get_retriever`` é opcional (uso em testes) e substitui ``indexer.get_retriever``.
    """
    text = query.strip()
    if not text:
        return []
    if _get_retriever is None:
        from agents.rag.indexer import get_retriever as _gr

        retriever = _gr(k=k)
    else:
        retriever = _get_retriever(k)
    docs = retriever.invoke(text)
    return [d.page_content for d in docs]
