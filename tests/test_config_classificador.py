"""
``CLASSIFICADOR_DE_MOVIMENTO``: falha alto e fica gravado.

O que se prende aqui não é a leitura da variável — é a impossibilidade de correr uma coleta com
um valor que ninguém escolheu e de a descobrir depois. §4.3 da dissertação declara ``regra``; se
a App Setting da sala vier com outra coisa, ou com um erro de digitação, o serviço tem de parar
no arranque, e o valor que de facto correu tem de sair em cada artefato da sessão, porque depois
da aula o ambiente do serviço já não existe para ser consultado.
"""

import json

import pytest

from agents.config import (
    CLASSIFICADOR_ENV,
    ConfiguracaoInvalida,
    classificador_de_movimento,
    classificador_por_modelo,
    verificar_configuracao,
)
from services import interaction_log
from services.telemetry import parse_telemetry_payload, serialize_batch_ndjson
from services.tutor_help import build_tutor_meta_from_actions


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [(None, "regra"), ("", "regra"), ("  ", "regra"), ("regra", "regra"), ("modelo", "modelo"), ("MODELO ", "modelo")],
)
def test_valores_aceites(monkeypatch: pytest.MonkeyPatch, bruto: str | None, esperado: str) -> None:
    if bruto is None:
        monkeypatch.delenv(CLASSIFICADOR_ENV, raising=False)
    else:
        monkeypatch.setenv(CLASSIFICADOR_ENV, bruto)
    assert classificador_de_movimento() == esperado
    assert classificador_por_modelo() is (esperado == "modelo")


@pytest.mark.parametrize("bruto", ["modeo", "regra ou modelo", "rule", "1", "true"])
def test_valor_invalido_para_o_arranque(monkeypatch: pytest.MonkeyPatch, bruto: str) -> None:
    """Antes, qualquer valor que não fosse ``modelo`` caía em ``regra`` sem dizer nada."""
    monkeypatch.setenv(CLASSIFICADOR_ENV, bruto)
    with pytest.raises(ConfiguracaoInvalida) as erro:
        verificar_configuracao()
    # A mensagem tem de nomear a chave e o valor: é lida num log de arranque do Functions.
    assert CLASSIFICADOR_ENV in str(erro.value)
    assert bruto in str(erro.value)


def test_arranque_passa_com_o_padrao(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(CLASSIFICADOR_ENV, raising=False)
    assert verificar_configuracao() is None


@pytest.mark.parametrize("valor", ["regra", "modelo"])
def test_tutor_meta_carrega_o_valor_em_vigor(monkeypatch: pytest.MonkeyPatch, valor: str) -> None:
    monkeypatch.setenv(CLASSIFICADOR_ENV, valor)
    meta = build_tutor_meta_from_actions([], intent="DEBUG")
    assert meta["classificadorDeMovimento"] == valor


def test_registro_estruturado_carrega_o_valor_em_vigor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CLASSIFICADOR_ENV, "modelo")
    record = interaction_log.build_record(
        {"code": "escreva(0)"},
        endpoint="/api/help",
        session_id="sessao-01",
        response={"message": "e agora?"},
        student_movement="ESTAGNACAO",
    )
    assert record["classificadorDeMovimento"] == "modelo"


def test_telemetria_carimba_cada_linha_do_lote(monkeypatch: pytest.MonkeyPatch) -> None:
    """O envelope é do servidor: o cliente não manda o campo, e não o consegue falsear."""
    monkeypatch.setenv(CLASSIFICADOR_ENV, "regra")
    payload = {
        "installId": "inst-abc123",
        "sessionId": "sess-000111",
        "classificadorDeMovimento": "modelo",  # vindo do cliente: ignorado
        "events": [
            {"seq": 1, "type": "session_start"},
            {"seq": 2, "type": "code_edit"},
        ],
    }
    batch, _, status = parse_telemetry_payload(payload)
    assert status == 200
    linhas = [json.loads(linha) for linha in serialize_batch_ndjson(batch, server_ts="2026-09-16T00:00:00Z").splitlines()]
    assert len(linhas) == 2
    assert {linha["classificadorDeMovimento"] for linha in linhas} == {"regra"}
