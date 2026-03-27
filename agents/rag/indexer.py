"""Carrega e indexa `docs/portugol_referencia.md` em memória (singleton por worker)."""

from __future__ import annotations

import logging
from pathlib import Path

from langchain_core.vectorstores import InMemoryVectorStore
from langchain_text_splitters import MarkdownHeaderTextSplitter

from agents.llm import create_embeddings_client

logger = logging.getLogger(__name__)


def _doc_path() -> Path:
    # agents/rag/indexer.py → raiz do projeto
    return Path(__file__).resolve().parent.parent.parent / "docs" / "portugol_referencia.md"


def _load_and_index() -> InMemoryVectorStore:
    path = _doc_path()
    logger.info("RAG: a criar índice a partir de %s (cold start)", path)
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()

        splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[
                ("#", "Header 1"),
                ("##", "Header 2"),
                ("###", "Header 3"),
            ],
        )
        splits = splitter.split_text(text)
        emb = create_embeddings_client()
        store = InMemoryVectorStore.from_documents(
            documents=splits,
            embedding=emb,
        )
    except Exception:
        logger.exception(
            "RAG: FALHA ao construir InMemoryVectorStore (markdown, embeddings LiteLLM ou rede)."
        )
        raise

    logger.info(
        "RAG: índice OK — InMemoryVectorStore com %d fragmentos (embeddings aplicados).",
        len(splits),
    )
    return store


_VECTOR_STORE: InMemoryVectorStore = _load_and_index()


def get_retriever(k: int = 4):
    """Retriever sobre o vectorstore singleton (k vizinhos)."""
    return _VECTOR_STORE.as_retriever(search_kwargs={"k": k})
