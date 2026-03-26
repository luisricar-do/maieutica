from unittest.mock import MagicMock, patch

import pytest

from agents.llm import create_chat_client


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
