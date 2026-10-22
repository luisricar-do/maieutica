"""Coletas, lixeira e exportação pelo serviço — camada de blob mockada."""

import csv
import io
import json
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from services import coletas_service, painel_service, telemetry_store
from tests import test_painel_service as base
from tests.test_painel_service import AUTH, SID, _line, _ndjson

# Mesmo blob em memória e mesmo ambiente (token, connection string) do painel.
_env = base._env
store = base.store

OTHER = "sess-bbb"


def _put_session(store, sid, *events, modified=None):
    name = f"sessions/inst-1/{sid}/000000001-{len(events):09d}.ndjson"
    store.blobs[name] = _ndjson(*events)
    if modified is not None:
        store.modified[name] = modified
    return name


async def _create(nome="Turma A", abrir=True):
    body, status = await coletas_service.coleta_action(
        AUTH, {"acao": "criar", "nome": nome, "data": "2026-10-22", "abrir": abrir}
    )
    assert status == 201
    return body["coleta"]


async def test_routes_require_token(store):
    for call in (
        coletas_service.coleta_action("Bearer x", {"acao": "criar"}),
        coletas_service.session_action("Bearer x", {"acao": "descartar", "sessionIds": [SID]}),
    ):
        _, status = await call
        assert status == 401
    body, status, media, _ = await coletas_service.export_coleta("Bearer x", {"coleta": "x"})
    assert status == 401 and media == "application/json" and "error" in body


async def test_create_lists_and_reports_errors(store):
    coleta = await _create()
    assert coleta["id"] == "2026-10-22-turma-a" and coleta["abertaEm"]
    body, status = await coletas_service.coleta_action(AUTH, {"acao": "encerrar", "id": "nao-ha"})
    assert status == 404
    body, status = await coletas_service.coleta_action(AUTH, None)
    assert status == 400

    body, _ = await painel_service.list_sessions(AUTH, {})
    assert [(c["id"], c["status"]) for c in body["coletas"]] == [("2026-10-22-turma-a", "aberta")]


async def test_state_write_retries_after_concurrent_change(store):
    await _create("A", abrir=False)
    real_read = store.read_json_versioned
    calls = {"n": 0}

    async def racing_read(name):
        result = await real_read(name)
        calls["n"] += 1
        if calls["n"] == 1:  # outra aba grava entre a nossa leitura e a escrita
            store.versions[name] = store.versions.get(name, 0) + 1
        return result

    with patch.object(telemetry_store, "read_json_versioned", racing_read):
        _, status = await coletas_service.coleta_action(AUTH, {"acao": "criar", "nome": "B", "data": "2026-10-22"})
    assert status == 201 and calls["n"] == 2
    assert len(json.loads(store.blobs[painel_service.STATE_BLOB])["coletas"]) == 2


async def test_views_by_coleta_none_and_trash(store):
    # OTHER morreu às 08:00; a coleta abre às 09:00; SID está viva às 10:00.
    before = "2026-10-21T08:00:00.000Z"
    _put_session(
        store, OTHER, _line(1, "session_start", sid=OTHER, serverTs=before),
        modified=datetime(2026, 10, 21, 8, tzinfo=UTC),
    )
    coleta = await _create()
    _put_session(store, SID, _line(1, "session_start"))
    state = json.loads(store.blobs[painel_service.STATE_BLOB])
    state["coletas"][0]["abertaEm"] = "2026-10-21T09:00:00.000Z"
    store.blobs[painel_service.STATE_BLOB] = json.dumps(state)

    body, _ = await painel_service.list_sessions(AUTH, {"coleta": coleta["id"]})
    assert [s["sessionId"] for s in body["sessions"]] == [SID]
    assert body["sessions"][0]["coletaId"] == coleta["id"]
    assert body["sessions"][0]["coletaManual"] is False

    # Mover a sessão antiga para a coleta: entra mesmo com o lote fora da janela.
    _, status = await coletas_service.session_action(
        AUTH, {"acao": "mover", "sessionIds": [OTHER], "coletaId": coleta["id"]}
    )
    assert status == 200
    body, _ = await painel_service.list_sessions(AUTH, {"coleta": coleta["id"]})
    assert {s["sessionId"] for s in body["sessions"]} == {SID, OTHER}

    # Descartar: some da coleta e aparece na lixeira.
    body, status = await coletas_service.session_action(
        AUTH, {"acao": "descartar", "sessionIds": [SID], "motivo": "teste"}
    )
    assert status == 200 and body["trashCount"] == 1
    body, _ = await painel_service.list_sessions(AUTH, {"coleta": coleta["id"]})
    assert [s["sessionId"] for s in body["sessions"]] == [OTHER]
    body, _ = await painel_service.list_sessions(AUTH, {"coleta": "lixeira"})
    assert [s["sessionId"] for s in body["sessions"]] == [SID]
    assert body["sessions"][0]["descarte"]["motivo"] == "teste"

    # «Sem coleta»: só quem não caiu em nenhuma.
    await coletas_service.session_action(AUTH, {"acao": "mover", "sessionIds": [OTHER], "coletaId": None})
    body, _ = await painel_service.list_sessions(AUTH, {"coleta": "sem", "horas": "0"})
    assert [s["sessionId"] for s in body["sessions"]] == [OTHER]

    _, status = await painel_service.list_sessions(AUTH, {"coleta": "nao-ha"})
    assert status == 404


@pytest.mark.parametrize(
    "payload",
    [
        {"acao": "voar", "sessionIds": [SID]},
        {"acao": "descartar", "sessionIds": []},
        {"acao": "descartar", "sessionIds": ["../x"]},
        {"acao": "descartar"},
        [],
    ],
)
async def test_session_action_validation(store, payload):
    _, status = await coletas_service.session_action(AUTH, payload)
    assert status == 400


async def test_erase_requires_trash_then_removes_everything(store):
    session_blob = _put_session(store, SID, _line(1, "session_start"))
    other_blob = _put_session(store, OTHER, _line(1, "session_start", sid=OTHER))
    store.blobs[f"comandos/{SID}/1.json"] = "{}"
    store.blobs[f"notas/{SID}/1.json"] = "{}"
    store.blobs[f"interactions/{SID}/t-1.ndjson"] = "{}\n"
    await painel_service.list_sessions(AUTH, {})  # aquece o cache

    _, status = await coletas_service.session_action(AUTH, {"acao": "apagar", "sessionIds": [SID]})
    assert status == 409
    assert session_blob in store.blobs

    await coletas_service.session_action(AUTH, {"acao": "descartar", "sessionIds": [SID], "motivo": "desistiu"})
    body, status = await coletas_service.session_action(AUTH, {"acao": "apagar", "sessionIds": [SID]})
    assert status == 200 and body["blobs"] == {SID: 4}
    assert set(store.blobs) == {other_blob, painel_service.STATE_BLOB}

    state = json.loads(store.blobs[painel_service.STATE_BLOB])
    assert state["descartes"] == {}
    assert [(a["sessionId"], a["blobs"], a["motivo"]) for a in state["apagadas"]] == [(SID, 4, "desistiu")]

    body, _ = await painel_service.list_sessions(AUTH, {})
    assert [s["sessionId"] for s in body["sessions"]] == [OTHER]


async def test_export_formats(store):
    coleta = await _create()
    state = json.loads(store.blobs[painel_service.STATE_BLOB])
    state["coletas"][0]["abertaEm"] = "2026-10-21T09:00:00.000Z"
    store.blobs[painel_service.STATE_BLOB] = json.dumps(state)
    _put_session(store, SID, _line(1, "session_start"), _line(2, "task_start", task=0, timeboxMs=60_000))
    # Lote sobreposto (retentativa): o seq 2 não pode sair duas vezes.
    store.blobs[f"sessions/inst-1/{SID}/000000002-000000002.ndjson"] = _ndjson(
        _line(2, "task_start", task=0, timeboxMs=60_000)
    )
    store.blobs[f"interactions/{SID}/t-1.ndjson"] = json.dumps({"sessionId": SID, "turn": 1}) + "\n"

    body, status, media, filename = await coletas_service.export_coleta(
        AUTH, {"coleta": coleta["id"], "formato": "eventos"}
    )
    assert status == 200 and media.startswith("application/x-ndjson")
    assert filename == f"{coleta['id']}-eventos.ndjson"
    lines = [json.loads(line) for line in body.splitlines()]
    assert [(e["seq"], e["coletaId"]) for e in lines] == [(1, coleta["id"]), (2, coleta["id"])]

    body, status, _, _ = await coletas_service.export_coleta(
        AUTH, {"coleta": coleta["id"], "formato": "interacoes"}
    )
    assert [json.loads(line)["turn"] for line in body.splitlines()] == [1]

    body, status, media, filename = await coletas_service.export_coleta(
        AUTH, {"coleta": coleta["id"], "formato": "resumo"}
    )
    assert media.startswith("text/csv") and filename.endswith(".csv")
    rows = list(csv.DictReader(io.StringIO(body)))
    assert [(r["sessionId"], r["task"]) for r in rows] == [(SID, "0")]

    for query, expected in (
        ({"coleta": coleta["id"], "formato": "pdf"}, 400),
        ({"coleta": "nao-ha"}, 404),
    ):
        _, status, _, _ = await coletas_service.export_coleta(AUTH, query)
        assert status == expected
