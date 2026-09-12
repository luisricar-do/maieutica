"""Registro estruturado por turno: conteúdo, ausência de ``studentName`` e destino."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services import interaction_log
from services.tutor_help import process_help_request

_PAYLOAD = {
    "code": "escreva(1)",
    "errors": ["erro na linha 1"],
    "compilerErrorLines": [1],
    "history": [{"role": "user", "content": "não entendi"}],
    "hintLevel": 1,
    "includeDocumentation": False,
    "previousCode": "escreva(0)",
    "previousErrors": [],
    "studentName": "Fulana",
    "sessionId": "sessao-01",
}


def test_desligado_sem_configuracao(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INTERACTION_LOG_DIR", raising=False)
    monkeypatch.setenv("INTERACTION_LOG_TO_BLOB", "0")
    assert interaction_log.is_enabled() is False


def test_registro_nao_guarda_o_nome_do_estudante() -> None:
    record = interaction_log.build_record(
        _PAYLOAD,
        endpoint="/api/help",
        session_id="sessao-01",
        response={"message": "e agora?"},
        intent="DEBUG",
        student_movement="ESTAGNACAO",
        movement_source="texto",
        model="gpt-4o-mini",
        latency_ms=120,
    )
    assert "studentName" not in record["request"]
    assert record["request"]["previousCode"] == "escreva(0)"
    assert record["sessionId"] == "sessao-01"
    assert record["studentMovement"] == "ESTAGNACAO"
    assert record["model"] == "gpt-4o-mini"
    assert record["latencyMs"] == 120


@pytest.mark.asyncio
async def test_grava_ndjson_local(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("INTERACTION_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("INTERACTION_LOG_TO_BLOB", "0")
    record = interaction_log.build_record(
        _PAYLOAD,
        endpoint="/api/help",
        session_id="sessao-01",
        response={"message": "e agora?"},
    )
    await interaction_log.log_interaction(record)

    files = list(tmp_path.glob("interactions-*.ndjson"))
    assert len(files) == 1
    linha = json.loads(files[0].read_text(encoding="utf-8").strip())
    assert linha["response"]["message"] == "e agora?"
    assert linha["endpoint"] == "/api/help"


@pytest.mark.asyncio
async def test_falha_de_escrita_nao_derruba_a_resposta(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("INTERACTION_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("INTERACTION_LOG_TO_BLOB", "0")
    monkeypatch.setattr(
        interaction_log,
        "_write_local",
        MagicMock(side_effect=OSError("disco cheio")),
    )
    record = interaction_log.build_record(
        _PAYLOAD, endpoint="/api/help", session_id="s", response={}
    )
    await interaction_log.log_interaction(record)  # não levanta


@pytest.mark.asyncio
async def test_help_registra_o_turno(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("INTERACTION_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("INTERACTION_LOG_TO_BLOB", "0")
    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(
        return_value={
            "tutor_response": "O que muda em i a cada volta?",
            "diagnosis": {"errorType": "logic"},
            "actions": [],
            "intent": "DEBUG",
        }
    )
    with patch("services.tutor_help.tutor_graph", mock_graph):
        body, status = await process_help_request(dict(_PAYLOAD))

    assert status == 200
    # Editou o código e surgiu erro de compilação: a regra do código decide, não o texto.
    assert body["tutorMeta"]["studentMovement"] == "REGRESSAO"
    assert body["tutorMeta"]["intent"] == "DEBUG"

    linha = json.loads(
        next(tmp_path.glob("interactions-*.ndjson")).read_text(encoding="utf-8").strip()
    )
    assert linha["sessionId"] == "sessao-01"
    assert linha["studentMovement"] == "REGRESSAO"
    assert linha["response"]["message"] == "O que muda em i a cada volta?"
    assert "studentName" not in linha["request"]
