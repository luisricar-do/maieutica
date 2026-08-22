"""
Ingestão da telemetria da IDE (dissertação): valida o lote de eventos, enriquece
com marca temporal do servidor e persiste como NDJSON no Azure Blob Storage.

Cada lote vira um blob imutável cujo nome deriva da faixa de ``seq``, de modo que
uma retentativa do mesmo lote não duplica dados. Sobreposições residuais (cliente
que reagrupa eventos entre tentativas) são removidas na análise por
``(sessionId, seq)``.
"""

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any, TypedDict

from services import telemetry_store

logger = logging.getLogger(__name__)

MAX_EVENTS_PER_BATCH = 500
MAX_EVENT_KEYS = 40
MAX_SERIALIZED_BATCH_BYTES = 1_048_576  # 1 MiB
MAX_TYPE_LENGTH = 64
MAX_STRING_VALUE_LENGTH = 4096

#: ``installId`` e ``sessionId`` entram no caminho do blob: só caracteres seguros.
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

_CONDITIONS = frozenset({"control", "experimental"})


class TelemetryBatch(TypedDict):
    install_id: str
    session_id: str
    participant_id: str | None
    condition: str | None
    build_sha: str | None
    prompt_hash: str | None
    events: list[dict[str, Any]]


def _parse_safe_id(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    return value if _SAFE_ID.match(value) else None


def _parse_optional_label(raw: object, *, max_length: int = 64) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        return None
    value = raw.strip()[:max_length]
    return value or None


def _parse_condition(raw: object) -> str | None:
    value = _parse_optional_label(raw)
    if value is None:
        return None
    normalized = value.lower()
    return normalized if normalized in _CONDITIONS else None


def _truncate_value(value: Any) -> Any:
    """Limita strings longas; mantém escalares e coleções pequenas como estão."""
    if isinstance(value, str):
        return value[:MAX_STRING_VALUE_LENGTH]
    if isinstance(value, list):
        return [_truncate_value(item) for item in value[:MAX_EVENT_KEYS]]
    if isinstance(value, dict):
        return {
            str(k): _truncate_value(v)
            for k, v in list(value.items())[:MAX_EVENT_KEYS]
        }
    return value


def _parse_event(raw: object) -> dict[str, Any] | None:
    """Aceita o evento apenas com ``type`` (string) e ``seq`` (inteiro >= 0)."""
    if not isinstance(raw, dict):
        return None

    event_type = raw.get("type")
    if not isinstance(event_type, str) or not event_type.strip():
        return None

    seq = raw.get("seq")
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0:
        return None

    event: dict[str, Any] = {}
    for key, value in list(raw.items())[:MAX_EVENT_KEYS]:
        event[str(key)] = _truncate_value(value)
    event["type"] = event_type.strip()[:MAX_TYPE_LENGTH]
    event["seq"] = seq
    return event


def parse_telemetry_payload(
    payload: Any,
) -> tuple[TelemetryBatch | None, dict[str, Any] | None, int]:
    """
    Valida o body JSON já desserializado.

    Em caso de sucesso devolve ``(batch, None, 200)``; caso contrário
    ``(None, {error: ...}, código_http)``.
    """
    if not isinstance(payload, dict):
        return None, {"error": "O corpo JSON deve ser um objeto."}, 400

    install_id = _parse_safe_id(payload.get("installId"))
    if install_id is None:
        return (
            None,
            {
                "error": (
                    "O campo 'installId' é obrigatório "
                    "(até 64 caracteres em [A-Za-z0-9_-])."
                )
            },
            400,
        )

    session_id = _parse_safe_id(payload.get("sessionId"))
    if session_id is None:
        return (
            None,
            {
                "error": (
                    "O campo 'sessionId' é obrigatório "
                    "(até 64 caracteres em [A-Za-z0-9_-])."
                )
            },
            400,
        )

    raw_events = payload.get("events")
    if not isinstance(raw_events, list) or not raw_events:
        return (
            None,
            {"error": "O campo 'events' deve ser uma lista não vazia."},
            400,
        )
    if len(raw_events) > MAX_EVENTS_PER_BATCH:
        return (
            None,
            {
                "error": (
                    f"Lote excede {MAX_EVENTS_PER_BATCH} eventos; "
                    "divida em múltiplos pedidos."
                )
            },
            413,
        )

    events = [parsed for raw in raw_events if (parsed := _parse_event(raw))]
    if not events:
        return (
            None,
            {"error": "Nenhum evento válido: exige 'type' (string) e 'seq' (int >= 0)."},
            400,
        )

    batch: TelemetryBatch = {
        "install_id": install_id,
        "session_id": session_id,
        "participant_id": _parse_optional_label(payload.get("participantId")),
        "condition": _parse_condition(payload.get("condition")),
        "build_sha": _parse_optional_label(payload.get("buildSha")),
        "prompt_hash": _parse_optional_label(payload.get("promptHash")),
        "events": events,
    }
    return batch, None, 200


def serialize_batch_ndjson(batch: TelemetryBatch, *, server_ts: str) -> str:
    """
    Uma linha JSON por evento. A identidade vem sempre do envelope, nunca do
    evento, para que o dataset não misture pseudónimos numa mesma sessão.
    """
    identity = {
        "installId": batch["install_id"],
        "sessionId": batch["session_id"],
        "participantId": batch["participant_id"],
        "condition": batch["condition"],
        "buildSha": batch["build_sha"],
        "promptHash": batch["prompt_hash"],
    }
    lines = []
    for event in batch["events"]:
        line = {**event, **identity, "serverTs": server_ts}
        lines.append(json.dumps(line, ensure_ascii=False, separators=(",", ":")))
    return "\n".join(lines) + "\n"


def blob_name_for(batch: TelemetryBatch) -> str:
    """
    ``sessions/{installId}/{sessionId}/{primeiroSeq}-{ultimoSeq}.ndjson``.

    O nome é determinístico: a mesma retentativa reescreve o mesmo blob em vez de
    acrescentar uma cópia.
    """
    seqs = [event["seq"] for event in batch["events"]]
    first, last = min(seqs), max(seqs)
    return (
        f"sessions/{batch['install_id']}/{batch['session_id']}/"
        f"{first:09d}-{last:09d}.ndjson"
    )


async def process_telemetry_request(payload: Any) -> tuple[dict[str, Any], int]:
    """
    Processa o body JSON já desserializado.

    Devolve ``(corpo_dict, status_http)``. Em 503/500 o cliente deve **manter** os
    eventos localmente e repetir o lote mais tarde.
    """
    batch, err_body, status = parse_telemetry_payload(payload)
    if batch is None:
        assert err_body is not None
        return err_body, status

    if not telemetry_store.is_configured():
        logger.warning("Telemetria recebida sem armazenamento configurado; descartada.")
        return {"error": "Armazenamento de telemetria não configurado."}, 503

    server_ts = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    content = serialize_batch_ndjson(batch, server_ts=server_ts)
    if len(content.encode("utf-8")) > MAX_SERIALIZED_BATCH_BYTES:
        return {"error": "Lote serializado excede 1 MiB."}, 413

    blob_name = blob_name_for(batch)
    try:
        await telemetry_store.put_ndjson(blob_name, content)
    except Exception:
        logger.exception("Falha ao gravar telemetria no blob %s", blob_name)
        return {"error": "Falha ao persistir a telemetria."}, 500

    return {"accepted": len(batch["events"]), "blob": blob_name}, 200
