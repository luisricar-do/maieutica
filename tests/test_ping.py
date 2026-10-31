import pytest

from services.ping import ping_response


def test_ping_response_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BUILD_SHA", raising=False)
    assert ping_response() == {"pong": True, "build": None}


def test_ping_devolve_o_commit_da_imagem(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUILD_SHA", "abc1234")
    assert ping_response()["build"] == "abc1234"
