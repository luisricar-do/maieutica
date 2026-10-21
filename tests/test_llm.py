from unittest.mock import MagicMock, patch

import pytest

from agents.llm import create_chat_client, create_embeddings_client


def test_create_chat_client_openai_compatible_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LITELLM_BASE_URL", "http://localhost:4000")
    monkeypatch.setenv("LITELLM_API_KEY", "sk-test")
    monkeypatch.setenv("LITELLM_MODEL", "anthropic/claude-3-5-sonnet-latest")

    with patch("agents.llm.ChatOpenAI") as mock_openai:
        mock_openai.return_value = MagicMock()
        create_chat_client(max_tokens=100, temperature=0.5)

    mock_openai.assert_called_once()
    _, kwargs = mock_openai.call_args
    assert kwargs["base_url"] == "http://localhost:4000/v1"
    assert kwargs["model"] == "anthropic/claude-3-5-sonnet-latest"
    assert kwargs["api_key"] == "sk-test"
    assert kwargs["max_tokens"] == 100
    assert kwargs["temperature"] == 0.5


def test_create_chat_client_keeps_v1_suffix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LITELLM_BASE_URL", "https://proxy.example/v1")
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with patch("agents.llm.ChatOpenAI") as mock_openai:
        mock_openai.return_value = MagicMock()
        create_chat_client(max_tokens=1, temperature=0)

    _, kwargs = mock_openai.call_args
    assert kwargs["base_url"] == "https://proxy.example/v1"


def test_create_chat_client_requires_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LITELLM_BASE_URL", raising=False)

    with patch("agents.llm.ChatOpenAI") as mock_openai:
        with pytest.raises(ValueError, match="LITELLM_BASE_URL"):
            create_chat_client(max_tokens=1, temperature=0)

    mock_openai.assert_not_called()


def test_create_embeddings_client_openai_compatible_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LITELLM_BASE_URL", "http://localhost:4000")
    monkeypatch.setenv("LITELLM_API_KEY", "sk-test")
    monkeypatch.setenv("LITELLM_EMBEDDING_MODEL", "text-embedding-3-small")

    with patch("agents.llm.OpenAIEmbeddings") as mock_emb:
        mock_emb.return_value = MagicMock()
        create_embeddings_client()

    mock_emb.assert_called_once()
    _, kwargs = mock_emb.call_args
    assert kwargs["base_url"] == "http://localhost:4000/v1"
    assert kwargs["model"] == "text-embedding-3-small"
    assert kwargs["api_key"] == "sk-test"


def test_create_embeddings_client_requires_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LITELLM_BASE_URL", raising=False)

    with patch("agents.llm.OpenAIEmbeddings") as mock_emb:
        with pytest.raises(ValueError, match="LITELLM_BASE_URL"):
            create_embeddings_client()

    mock_emb.assert_not_called()


def test_create_chat_client_sets_timeout_and_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LITELLM_BASE_URL", "http://localhost:4000")
    monkeypatch.delenv("LITELLM_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("LITELLM_MAX_RETRIES", raising=False)

    with patch("agents.llm.ChatOpenAI") as mock_openai:
        mock_openai.return_value = MagicMock()
        create_chat_client(max_tokens=1, temperature=0)

    _, kwargs = mock_openai.call_args
    assert kwargs["timeout"] == 12.0
    assert kwargs["max_retries"] == 1


@pytest.mark.parametrize(
    ("timeout_raw", "retries_raw", "timeout", "retries"),
    [("20", "0", 20.0, 0), ("abc", "x", 12.0, 1), ("0", "-1", 12.0, 1)],
)
def test_timeout_and_retries_from_env(
    monkeypatch: pytest.MonkeyPatch,
    timeout_raw: str,
    retries_raw: str,
    timeout: float,
    retries: int,
) -> None:
    monkeypatch.setenv("LITELLM_BASE_URL", "http://localhost:4000")
    monkeypatch.setenv("LITELLM_TIMEOUT_SECONDS", timeout_raw)
    monkeypatch.setenv("LITELLM_MAX_RETRIES", retries_raw)

    with patch("agents.llm.OpenAIEmbeddings") as mock_emb:
        mock_emb.return_value = MagicMock()
        create_embeddings_client()

    _, kwargs = mock_emb.call_args
    assert kwargs["timeout"] == timeout
    assert kwargs["max_retries"] == retries
