"""Cliente de chat via proxy OpenAI-compatível (ex.: LiteLLM)."""

import logging
import os

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o-mini"

# Teto por chamada ao proxy e uma retentativa. Sem eles valem os defaults do SDK (600 s, duas
# retentativas): uma chamada que trava no proxy segura o turno por ~30 s antes de ser refeita, e a
# IDE já desistiu. Uma chamada sã do gpt-4o-mini fica em poucos segundos, e o analista e o
# estrategista têm reservas locais para quando a retentativa também falha.
DEFAULT_TIMEOUT_SECONDS = 12.0
DEFAULT_MAX_RETRIES = 1


def chat_model_name() -> str:
    """Modelo de chat em uso (registrado na resposta e no log para reprodutibilidade)."""
    return os.getenv("LITELLM_MODEL", DEFAULT_MODEL)


def request_timeout_seconds() -> float:
    """Teto por chamada (``LITELLM_TIMEOUT_SECONDS``); valor inválido cai no padrão."""
    raw = os.getenv("LITELLM_TIMEOUT_SECONDS", "").strip()
    try:
        value = float(raw) if raw else DEFAULT_TIMEOUT_SECONDS
    except ValueError:
        logger.warning("LITELLM_TIMEOUT_SECONDS inválido (%r); usando %s", raw, DEFAULT_TIMEOUT_SECONDS)
        return DEFAULT_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_TIMEOUT_SECONDS


def max_retries() -> int:
    """Retentativas por chamada (``LITELLM_MAX_RETRIES``); valor inválido cai no padrão."""
    raw = os.getenv("LITELLM_MAX_RETRIES", "").strip()
    try:
        value = int(raw) if raw else DEFAULT_MAX_RETRIES
    except ValueError:
        logger.warning("LITELLM_MAX_RETRIES inválido (%r); usando %s", raw, DEFAULT_MAX_RETRIES)
        return DEFAULT_MAX_RETRIES
    return value if value >= 0 else DEFAULT_MAX_RETRIES


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
    model = chat_model_name()
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
        timeout=request_timeout_seconds(),
        max_retries=max_retries(),
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
        timeout=request_timeout_seconds(),
        max_retries=max_retries(),
    )
