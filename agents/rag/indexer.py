"""Carrega e indexa `docs/portugol_referencia.md` em memória (singleton por worker)."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from langchain_core.vectorstores import InMemoryVectorStore
from langchain_openai import AzureOpenAIEmbeddings
from langchain_text_splitters import MarkdownHeaderTextSplitter

from agents.rag.azure import azure_openai_api_key

logger = logging.getLogger(__name__)


def _doc_path() -> Path:
    # agents/rag/indexer.py → raiz do projeto
    return Path(__file__).resolve().parent.parent.parent / "docs" / "portugol_referencia.md"


def _embeddings() -> AzureOpenAIEmbeddings:
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "") or None
    api_key = azure_openai_api_key()
    deployment = os.environ.get(
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
        "text-embedding-3-small",
    )
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
    return AzureOpenAIEmbeddings(
        azure_endpoint=endpoint,
        api_key=api_key,
        azure_deployment=deployment,
        api_version=api_version,
    )


def _load_and_index() -> InMemoryVectorStore:
    path = _doc_path()
    logger.info("A criar índice RAG a partir de %s (cold start / arranque a frio)", path)
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
    emb = _embeddings()
    store = InMemoryVectorStore.from_documents(
        documents=splits,
        embedding=emb,
    )
    logger.info("Índice RAG criado: %d fragmentos indexados.", len(splits))
    return store


_VECTOR_STORE: InMemoryVectorStore = _load_and_index()


def get_retriever(k: int = 4):
    """Retriever sobre o vectorstore singleton (k vizinhos)."""
    return _VECTOR_STORE.as_retriever(search_kwargs={"k": k})
