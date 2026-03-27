"""Grafo LangGraph: recuperação + geração (LiteLLM / API OpenAI-compatível)."""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from agents.llm import create_chat_client

logger = logging.getLogger(__name__)


class RagState(TypedDict):
    question: str
    context: list[str]
    answer: str


def _chat_llm():
    """Chat para geração RAG (mesmo proxy que o tutor; modelo ``LITELLM_MODEL``)."""
    return create_chat_client(max_tokens=1024, temperature=0)


def build_graph():
    from agents.rag.indexer import get_retriever

    retriever = get_retriever(k=4)
    llm = _chat_llm()

    def retrieve(state: RagState) -> dict:
        docs = retriever.invoke(state["question"])
        return {"context": [d.page_content for d in docs]}

    def generate(state: RagState) -> dict:
        ctx = state.get("context") or []
        context_str = "\n\n---\n\n".join(ctx) if ctx else "(sem trechos recuperados)"
        system = (
            "És um especialista em Portugol. Respondes apenas com base no contexto "
            "fornecido abaixo. Se não encontrares a resposta no contexto, diz "
            "explicitamente que não encontraste informação suficiente na documentação "
            "fornecida e não inventes."
        )
        user = (
            f"Contexto (documentação Portugol):\n\n{context_str}\n\n"
            f"Pergunta: {state['question']}"
        )
        resp = llm.invoke(
            [SystemMessage(content=system), HumanMessage(content=user)]
        )
        return {"answer": resp.content}

    builder = StateGraph(RagState)
    builder.add_node("retrieve", retrieve)
    builder.add_node("generate", generate)
    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "generate")
    builder.add_edge("generate", END)
    return builder.compile()


_COMPILED_RAG_GRAPH: Any | None = None


def get_compiled_rag_graph():
    """Compila o grafo RAG uma única vez (lazy singleton)."""
    global _COMPILED_RAG_GRAPH
    if _COMPILED_RAG_GRAPH is None:
        try:
            _COMPILED_RAG_GRAPH = build_graph()
        except Exception:
            logger.exception(
                "RAG: FALHA ao compilar grafo (índice, embeddings ou chat via LiteLLM)."
            )
            raise
        logger.info(
            "RAG: grafo LangGraph OK (retrieve → generate); pronto para /api/portugol/ask."
        )
    return _COMPILED_RAG_GRAPH
