"""Autenticação, comandos e listagem do painel — camada de blob mockada."""

import json
import re
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from services import painel_service, telemetry_store

TOKEN = "segredo-do-condutor"
AUTH = f"Bearer {TOKEN}"
SID = "sess-aaa111"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(painel_service.ADMIN_TOKEN_ENV, TOKEN)
    monkeypatch.setenv(telemetry_store.CONNECTION_STRING_ENV, "UseDevelopmentStorage=true")
    painel_service.reset_cache()
    yield
    painel_service.reset_cache()


class FakeStore:
    """Blob em memória com a mesma interface assíncrona de ``telemetry_store``."""

    def __init__(self, blobs: dict[str, str] | None = None, modified=None):
        self.blobs = dict(blobs or {})
        self.modified = modified or {}
        self.reads: list[str] = []
        self.listed: list[str] = []

    async def list_blobs(self, prefix):
        self.listed.append(prefix)
        now = datetime.now(UTC)
        return [
            (name, self.modified.get(name, now))
            for name in sorted(self.blobs)
            if name.startswith(prefix)
        ]

    async def read_text(self, name):
        self.reads.append(name)
        return self.blobs[name]

    async def put_json(self, name, obj):
        self.blobs[name] = json.dumps(obj)


@pytest.fixture
def store():
    fake = FakeStore()
    with (
        patch.object(telemetry_store, "list_blobs", fake.list_blobs),
        patch.object(telemetry_store, "read_text", fake.read_text),
        patch.object(telemetry_store, "put_json", fake.put_json),
    ):
        yield fake


# --- Autenticação ---------------------------------------------------------------------


def test_auth_503_without_token_configured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(painel_service.ADMIN_TOKEN_ENV)
    body, status = painel_service.check_conductor_auth(AUTH)
    assert status == 503
    assert "STUDY_ADMIN_TOKEN" in body["error"]


@pytest.mark.parametrize(
    "header", [None, "", "Bearer", "Bearer errado", f"Basic {TOKEN}", TOKEN]
)
def test_auth_401_on_wrong_or_missing_token(header):
    body, status = painel_service.check_conductor_auth(header)
    assert status == 401
    assert "error" in body


def test_auth_ok_with_bearer_token():
    assert painel_service.check_conductor_auth(AUTH) is None
    assert painel_service.check_conductor_auth(f"bearer  {TOKEN} ") is None


def test_auth_locks_client_after_repeated_failures():
    for _ in range(painel_service.MAX_AUTH_FAILURES):
        _, status = painel_service.check_conductor_auth("Bearer errado", "1.2.3.4", now=100.0)
        assert status == 401
    # Bloqueado mesmo com a senha certa; outro cliente segue livre.
    _, status = painel_service.check_conductor_auth(AUTH, "1.2.3.4", now=101.0)
    assert status == 429
    assert painel_service.check_conductor_auth(AUTH, "5.6.7.8", now=101.0) is None
    # Passado o bloqueio, a senha certa entra e zera a contagem.
    later = 100.0 + painel_service.AUTH_LOCKOUT_SECONDS
    assert painel_service.check_conductor_auth(AUTH, "1.2.3.4", now=later) is None
    _, status = painel_service.check_conductor_auth("Bearer errado", "1.2.3.4", now=later + 1)
    assert status == 401


def test_auth_success_resets_failures():
    for _ in range(painel_service.MAX_AUTH_FAILURES - 1):
        painel_service.check_conductor_auth("Bearer errado", "9.9.9.9", now=1.0)
    assert painel_service.check_conductor_auth(AUTH, "9.9.9.9", now=2.0) is None
    _, status = painel_service.check_conductor_auth("Bearer errado", "9.9.9.9", now=3.0)
    assert status == 401


async def test_routes_require_token(store):
    _, status = await painel_service.list_sessions("Bearer x", {})
    assert status == 401
    _, status = await painel_service.create_command(None, {"sessionId": SID, "kind": "skip"})
    assert status == 401
    assert store.blobs == {}


# --- POST /api/painel/comandos --------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {"kind": "skip"},
        {"sessionId": "a/b", "kind": "skip"},
        {"sessionId": SID, "kind": "reboot"},
        {"sessionId": SID, "kind": "extend", "minutes": 0},
        {"sessionId": SID, "kind": "extend", "minutes": 31},
        {"sessionId": SID, "kind": "extend", "minutes": "5"},
        {"sessionId": SID, "kind": "extend", "minutes": True},
        {"sessionId": SID, "kind": "skip", "minutes": 5},
        {"sessionId": SID, "kind": "accept", "text": "oi"},
        {"sessionId": SID, "kind": "note"},
        {"sessionId": SID, "kind": "note", "text": "   "},
        {"sessionId": SID, "kind": "note", "text": "x" * 501},
    ],
)
async def test_create_command_validation(store, payload):
    body, status = await painel_service.create_command(AUTH, payload)
    assert status == 400
    assert "error" in body
    assert store.blobs == {}


async def test_create_extend_defaults_to_five_minutes(store):
    body, status = await painel_service.create_command(
        AUTH, {"sessionId": SID, "kind": "extend"}
    )
    assert status == 201
    assert re.fullmatch(r"\d{13}-[0-9a-f]{6}", body["id"])
    assert body["minutes"] == 5
    assert body["sessionId"] == SID
    assert body["createdAt"].endswith("Z")
    name = f"comandos/{SID}/{body['id']}.json"
    assert json.loads(store.blobs[name]) == body


async def test_create_note_goes_to_notes_prefix(store):
    body, status = await painel_service.create_command(
        AUTH, {"sessionId": SID, "kind": "note", "text": "  máquina travou  "}
    )
    assert status == 201
    assert body["text"] == "máquina travou"
    assert list(store.blobs) == [f"notas/{SID}/{body['id']}.json"]


async def test_create_command_503_without_blob(store, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(telemetry_store.CONNECTION_STRING_ENV)
    _, status = await painel_service.create_command(AUTH, {"sessionId": SID, "kind": "skip"})
    assert status == 503


async def test_create_command_500_when_write_fails(store):
    with patch.object(telemetry_store, "put_json", AsyncMock(side_effect=RuntimeError)):
        body, status = await painel_service.create_command(
            AUTH, {"sessionId": SID, "kind": "accept"}
        )
    assert status == 500
    assert "error" in body


def test_command_ids_sort_by_time():
    first = painel_service.new_command_id(now_ms=1_700_000_000_000)
    second = painel_service.new_command_id(now_ms=1_700_000_000_001)
    assert first < second
    assert first.startswith("1700000000000-")


# --- GET /api/coleta/comandos ---------------------------------------------------------


def _command_blob(command_id: str, kind: str = "skip", **extra) -> tuple[str, str]:
    doc = {"id": command_id, "sessionId": SID, "kind": kind, "createdAt": "t", **extra}
    return f"comandos/{SID}/{command_id}.json", json.dumps(doc)


async def test_ide_commands_filter_after_and_sort(store):
    for blob in (
        _command_blob("0000000000003-cccccc", "end_session"),
        _command_blob("0000000000001-aaaaaa", "extend", minutes=5),
        _command_blob("0000000000002-bbbbbb", "accept"),
    ):
        store.blobs[blob[0]] = blob[1]
    store.blobs["comandos/sess-outra/0000000000009-ffffff.json"] = json.dumps(
        {"id": "0000000000009-ffffff", "kind": "skip"}
    )
    store.blobs[f"notas/{SID}/0000000000004-dddddd.json"] = json.dumps(
        {"id": "0000000000004-dddddd", "kind": "note", "text": "x"}
    )

    body, status = await painel_service.commands_for_ide({"sessionId": SID})
    assert status == 200
    assert [c["id"] for c in body["commands"]] == [
        "0000000000001-aaaaaa",
        "0000000000002-bbbbbb",
        "0000000000003-cccccc",
    ]
    assert body["commands"][0] == {
        "id": "0000000000001-aaaaaa",
        "kind": "extend",
        "minutes": 5,
        "createdAt": "t",
    }
    assert store.listed == [f"comandos/{SID}/"]

    store.reads.clear()
    body, status = await painel_service.commands_for_ide(
        {"sessionId": SID, "after": "0000000000001-aaaaaa"}
    )
    assert [c["id"] for c in body["commands"]] == [
        "0000000000002-bbbbbb",
        "0000000000003-cccccc",
    ]
    assert store.reads == []  # já em cache (blobs imutáveis)


async def test_ide_commands_does_not_read_old_blobs(store):
    name, doc = _command_blob("0000000000001-aaaaaa")
    store.blobs[name] = doc
    body, _ = await painel_service.commands_for_ide(
        {"sessionId": SID, "after": "0000000000001-aaaaaa"}
    )
    assert body == {"commands": []}
    assert store.reads == []


@pytest.mark.parametrize("query", [{}, {"sessionId": "../x"}, {"sessionId": SID, "after": "9" * 65}])
async def test_ide_commands_400(store, query):
    _, status = await painel_service.commands_for_ide(query)
    assert status == 400


async def test_ide_commands_503_without_blob(store, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(telemetry_store.CONNECTION_STRING_ENV)
    _, status = await painel_service.commands_for_ide({"sessionId": SID})
    assert status == 503


async def test_ide_commands_do_not_need_conductor_token(store, monkeypatch):
    monkeypatch.delenv(painel_service.ADMIN_TOKEN_ENV)
    _, status = await painel_service.commands_for_ide({"sessionId": SID})
    assert status == 200


# --- GET /api/painel/sessoes ----------------------------------------------------------


def _ndjson(*events) -> str:
    return "".join(json.dumps(e) + "\n" for e in events)


def _line(seq, type_, sid=SID, **fields):
    return {
        "seq": seq,
        "type": type_,
        "ts": f"2026-10-21T10:00:{seq:02d}.000Z",
        "serverTs": f"2026-10-21T10:00:{seq:02d}.500Z",
        "installId": "inst-1",
        "sessionId": sid,
        "participantId": "P1",
        **fields,
    }


async def test_list_sessions_summarizes_and_caches(store):
    store.blobs[f"sessions/inst-1/{SID}/000000001-000000002.ndjson"] = _ndjson(
        _line(1, "session_start"),
        _line(2, "task_start", task=1, timeboxMs=600_000),
    )
    # Retentativa sobreposta: seq 2 repetido.
    store.blobs[f"sessions/inst-1/{SID}/000000002-000000003.ndjson"] = _ndjson(
        _line(2, "task_start", task=1, timeboxMs=600_000),
        _line(3, "conductor_command_applied", commandId="0000000000001-aaaaaa", kind="extend",
              minutes=5),
    )
    store.blobs["sessions/inst-2/sess-bbb/000000001-000000001.ndjson"] = _ndjson(
        _line(1, "session_start", sid="sess-bbb")
    )
    name, doc = _command_blob("0000000000001-aaaaaa", "extend", minutes=5)
    store.blobs[name] = doc
    name, doc = _command_blob("0000000000002-bbbbbb", "skip")
    store.blobs[name] = doc
    store.blobs[f"notas/{SID}/0000000000003-cccccc.json"] = json.dumps(
        {"id": "0000000000003-cccccc", "kind": "note", "text": "obs", "createdAt": "t"}
    )

    body, status = await painel_service.list_sessions(AUTH, {})
    assert status == 200
    assert body["generatedAt"].endswith("Z")
    sessions = {s["sessionId"]: s for s in body["sessions"]}
    assert set(sessions) == {SID, "sess-bbb"}
    assert body["sessions"][0]["sessionId"] == SID  # último evento mais recente primeiro

    mine = sessions[SID]
    assert len(mine["tasks"]) == 1
    assert mine["currentTask"]["extraMs"] == 5 * 60_000
    assert [(c["id"], c["applied"]) for c in mine["commands"]] == [
        ("0000000000001-aaaaaa", True),
        ("0000000000002-bbbbbb", False),
    ]
    assert mine["notes"][0]["text"] == "obs"

    reads_before = len(store.reads)
    await painel_service.list_sessions(AUTH, {})
    assert len(store.reads) == reads_before  # nada novo: tudo do cache


async def test_list_sessions_window_skips_old_sessions(store):
    old = "sessions/inst-1/sess-velha/000000001-000000001.ndjson"
    new = f"sessions/inst-1/{SID}/000000001-000000001.ndjson"
    store.blobs[old] = _ndjson(_line(1, "session_start", sid="sess-velha"))
    store.blobs[new] = _ndjson(_line(1, "session_start"))
    store.modified[old] = datetime.now(UTC) - timedelta(hours=48)

    body, _ = await painel_service.list_sessions(AUTH, {})
    assert [s["sessionId"] for s in body["sessions"]] == [SID]
    assert old not in store.reads

    body, _ = await painel_service.list_sessions(AUTH, {"horas": "0"})
    assert {s["sessionId"] for s in body["sessions"]} == {SID, "sess-velha"}


@pytest.mark.parametrize("horas", ["-1", "abc", "999999"])
async def test_list_sessions_rejects_bad_window(store, horas):
    _, status = await painel_service.list_sessions(AUTH, {"horas": horas})
    assert status == 400


async def test_list_sessions_503_without_blob(store, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(telemetry_store.CONNECTION_STRING_ENV)
    _, status = await painel_service.list_sessions(AUTH, {})
    assert status == 503


def test_painel_html_is_self_contained():
    html = painel_service.painel_html()
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert "painel/sessoes" in html and "painel/comandos" in html
    assert "<script src" not in html and "<link" not in html
