"""Cliente de chat via proxy OpenAI-compatível (ex.: LiteLLM)."""

import logging
import os

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o-mini"


def _normalize_litellm_base_url(url: str) -> str:
    u = url.strip().rstrip("/")
    if not u.endswith("/v1"):
        return f"{u}/v1"
    return u


def create_chat_client(*, max_tokens: int, temperature: float) -> BaseChatModel:
    """
    Usa o servidor LiteLLM (ou outro proxy) através da API compatível com OpenAI.

    Exige ``LITELLM_BASE_URL`` (ex.: ``http://localhost:4000``).
    """
    litellm_base = os.getenv("LITELLM_BASE_URL", "").strip()
    if not litellm_base:
        raise ValueError(
            "LITELLM_BASE_URL não está definido. Configure a URL do proxy "
            "(LiteLLM ou compatível com OpenAI /v1)."
        )

    api_key = (
        os.getenv("LITELLM_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or "litellm"
    )
    model = os.getenv("LITELLM_MODEL", DEFAULT_MODEL)
    base_url = _normalize_litellm_base_url(litellm_base)
    logger.debug(
        "LLM via proxy OpenAI-compatível (base_url=%s, model=%s)",
        base_url,
        model,
    )
    return ChatOpenAI(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        api_key=api_key,
        base_url=base_url,
    )


def create_embeddings_client() -> Embeddings:
    """
    Embeddings via proxy OpenAI-compatível (ex.: LiteLLM), mesmo ``LITELLM_BASE_URL`` do chat.

    Modelo: ``LITELLM_EMBEDDING_MODEL`` (default: ``text-embedding-3-small``).
    """
    litellm_base = os.getenv("LITELLM_BASE_URL", "").strip()
    if not litellm_base:
        raise ValueError(
            "LITELLM_BASE_URL não está definido. Necessário para embeddings do RAG "
            "(API OpenAI-compatível em /v1)."
        )

    api_key = (
        os.getenv("LITELLM_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or "litellm"
    )
    model = os.getenv("LITELLM_EMBEDDING_MODEL", "text-embedding-3-small")
    base_url = _normalize_litellm_base_url(litellm_base)
    logger.debug(
        "Embeddings via proxy OpenAI-compatível (base_url=%s, model=%s)",
        base_url,
        model,
    )
    return OpenAIEmbeddings(
        model=model,
        api_key=api_key,
        base_url=base_url,
    )
