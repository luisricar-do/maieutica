"""Define LITELLM_* mínimo para os testes (valores fictícios; o cliente é mockado)."""

import pytest


@pytest.fixture(autouse=True)
def _litellm_env_for_unit_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LITELLM_BASE_URL", "http://litellm.test")
    monkeypatch.setenv("LITELLM_API_KEY", "test-key")
