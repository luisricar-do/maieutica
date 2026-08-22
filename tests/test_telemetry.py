import json
from unittest.mock import AsyncMock, patch

import pytest

from services import telemetry_store
from services.telemetry import (
    MAX_EVENTS_PER_BATCH,
    blob_name_for,
    parse_telemetry_payload,
    process_telemetry_request,
    serialize_batch_ndjson,
)


def _payload(**overrides):
    base = {
        "installId": "inst-abc123",
        "sessionId": "sess-000111",
        "participantId": "P07",
        "condition": "experimental",
        "buildSha": "deadbeef",
        "events": [
            {"seq": 1, "ts": "2026-08-22T10:00:00.000Z", "type": "session_start"},
            {"seq": 2, "ts": "2026-08-22T10:00:05.000Z", "type": "code_edit"},
        ],
    }
    base.update(overrides)
    return base


def test_parse_rejects_non_dict() -> None:
    batch, body, status = parse_telemetry_payload([])
    assert batch is None
    assert status == 400
    assert "error" in body


@pytest.mark.parametrize(
    "install_id",
    ["", "   ", "../escape", "id/with/slash", "a" * 65, None, 42],
)
def test_parse_rejects_unsafe_install_id(install_id: object) -> None:
    batch, body, status = parse_telemetry_payload(_payload(installId=install_id))
    assert batch is None
    assert status == 400
    assert "installId" in body["error"]


def test_parse_rejects_unsafe_session_id() -> None:
    batch, body, status = parse_telemetry_payload(_payload(sessionId="a/b"))
    assert batch is None
    assert status == 400
    assert "sessionId" in body["error"]


def test_parse_rejects_empty_events() -> None:
    batch, body, status = parse_telemetry_payload(_payload(events=[]))
    assert batch is None
    assert status == 400


def test_parse_rejects_oversized_batch() -> None:
    events = [{"seq": i, "type": "code_edit"} for i in range(MAX_EVENTS_PER_BATCH + 1)]
    batch, body, status = parse_telemetry_payload(_payload(events=events))
    assert batch is None
    assert status == 413


def test_parse_drops_invalid_events_and_keeps_valid_ones() -> None:
    events = [
        {"seq": 1, "type": "session_start"},
        {"type": "sem_seq"},
        {"seq": -1, "type": "seq_negativo"},
        {"seq": True, "type": "seq_booleano"},
        {"seq": 2, "type": "   "},
        "não é objeto",
        {"seq": 3, "type": "task_start", "task": 2},
    ]
    batch, body, status = parse_telemetry_payload(_payload(events=events))
    assert status == 200
    assert body is None
    assert [e["seq"] for e in batch["events"]] == [1, 3]


def test_parse_rejects_batch_with_only_invalid_events() -> None:
    batch, body, status = parse_telemetry_payload(_payload(events=[{"type": "x"}]))
    assert batch is None
    assert status == 400


def test_parse_normalizes_condition_and_ignores_unknown_values() -> None:
    batch, _, _ = parse_telemetry_payload(_payload(condition="CONTROL"))
    assert batch["condition"] == "control"
    batch, _, _ = parse_telemetry_payload(_payload(condition="grupo-x"))
    assert batch["condition"] is None
    batch, _, _ = parse_telemetry_payload(_payload(condition=None))
    assert batch["condition"] is None


def test_parse_truncates_long_strings() -> None:
    events = [{"seq": 1, "type": "compile", "detail": "x" * 10_000}]
    batch, _, _ = parse_telemetry_payload(_payload(events=events))
    assert len(batch["events"][0]["detail"]) == 4096


def test_serialize_produces_one_json_line_per_event_with_identity() -> None:
    batch, _, _ = parse_telemetry_payload(_payload())
    content = serialize_batch_ndjson(batch, server_ts="2026-08-22T13:00:00Z")

    lines = content.strip().split("\n")
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["installId"] == "inst-abc123"
    assert first["sessionId"] == "sess-000111"
    assert first["participantId"] == "P07"
    assert first["condition"] == "experimental"
    assert first["buildSha"] == "deadbeef"
    assert first["serverTs"] == "2026-08-22T13:00:00Z"
    assert first["type"] == "session_start"
    assert content.endswith("\n")


def test_serialize_identity_from_envelope_overrides_event_fields() -> None:
    events = [{"seq": 1, "type": "compile", "installId": "forjado", "condition": "control"}]
    batch, _, _ = parse_telemetry_payload(_payload(events=events))
    line = json.loads(serialize_batch_ndjson(batch, server_ts="t").strip())
    assert line["installId"] == "inst-abc123"
    assert line["condition"] == "experimental"


def test_blob_name_is_deterministic_and_scoped_by_session() -> None:
    batch, _, _ = parse_telemetry_payload(_payload())
    assert (
        blob_name_for(batch)
        == "sessions/inst-abc123/sess-000111/000000001-000000002.ndjson"
    )


@pytest.mark.asyncio
async def test_process_returns_503_when_storage_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(telemetry_store.CONNECTION_STRING_ENV, raising=False)
    body, status = await process_telemetry_request(_payload())
    assert status == 503
    assert "error" in body


@pytest.mark.asyncio
async def test_process_writes_ndjson_to_blob(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(telemetry_store.CONNECTION_STRING_ENV, "UseDevelopmentStorage=true")
    put = AsyncMock()
    with patch("services.telemetry_store.put_ndjson", put):
        body, status = await process_telemetry_request(_payload())

    assert status == 200
    assert body["accepted"] == 2
    assert body["blob"] == "sessions/inst-abc123/sess-000111/000000001-000000002.ndjson"
    put.assert_awaited_once()
    blob_name, content = put.await_args.args
    assert blob_name == body["blob"]
    assert len(content.strip().split("\n")) == 2


@pytest.mark.asyncio
async def test_process_returns_500_when_blob_write_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(telemetry_store.CONNECTION_STRING_ENV, "UseDevelopmentStorage=true")
    put = AsyncMock(side_effect=RuntimeError("blob indisponível"))
    with patch("services.telemetry_store.put_ndjson", put):
        body, status = await process_telemetry_request(_payload())
    assert status == 500
    assert "error" in body
