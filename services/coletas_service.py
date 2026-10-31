"""
Coletas, lixeira e exportação do painel do condutor (rotas em ``function_app.py``).

- ``POST /api/painel/coletas``        — criar, abrir, encerrar, editar ou excluir uma coleta;
- ``POST /api/painel/sessoes/acoes``  — mover sessões de coleta, descartar, restaurar ou
  apagar de vez;
- ``GET  /api/painel/exportar``       — eventos, interações ou resumo de uma coleta;
- ``GET  /api/painel/conversa``       — turnos do tutor de uma sessão, para ler no painel.

Tudo exige o token do condutor. As regras (pertença, transições) são as funções puras de
``services.coletas``; aqui fica só o I/O.

**Apagar de vez** só aceita sessões que já estão na lixeira, e remove os lotes de
telemetria (``sessions/*/{sid}/``), comandos, notas e o registro por turno do tutor
(``interactions/{sid}/``). Fica no estado uma linha em ``apagadas`` com quando e quantos
blobs, sem conteúdo: o registro de que houve exclusão (desistência do participante,
sessão de teste) sobrevive aos dados.
"""

import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from services import telemetry_store
from services.coletas import (
    SESSION_ACTIONS,
    StateError,
    apply_coleta_action,
    apply_session_action,
    find_coleta,
    public_coletas,
    summary_csv,
)
from services.painel import dedupe_events
from services.painel_service import (
    COMMANDS_PREFIX,
    DOWNLOAD_CONCURRENCY,
    NOTES_PREFIX,
    SESSIONS_PREFIX,
    _error,
    _events_cache,
    _events_of,
    _gather_limited,
    _json_cache,
    _session_of,
    _utc_iso,
    check_conductor_auth,
    load_state,
    mutate_state,
    sessions_of_view,
)
from services.telemetry import _parse_safe_id

logger = logging.getLogger(__name__)

INTERACTIONS_PREFIX = "interactions/"

#: Sessões por pedido de ação (seleção em massa no painel).
MAX_SESSIONS_PER_ACTION = 200

EXPORT_FORMATS = {
    "eventos": ("application/x-ndjson; charset=utf-8", "ndjson"),
    "interacoes": ("application/x-ndjson; charset=utf-8", "ndjson"),
    "resumo": ("text/csv; charset=utf-8", "csv"),
}


def _now() -> str:
    return _utc_iso(datetime.now(UTC))


# --- POST /api/painel/coletas -----------------------------------------------------------


async def coleta_action(
    authorization: str | None, payload: Any, client: str = ""
) -> tuple[dict[str, Any], int]:
    """Aplica a ação e devolve ``{"coleta", "coletas"}`` (``coleta`` nulo em ``excluir``)."""
    denied = check_conductor_auth(authorization, client)
    if denied is not None:
        return denied
    if not telemetry_store.is_configured():
        return _error("Armazenamento de telemetria não configurado.", 503)
    now = _now()
    try:
        state, coleta = await mutate_state(lambda s: apply_coleta_action(s, payload, now))
    except StateError as exc:
        return _error(str(exc), exc.status)
    except telemetry_store.VersionConflict:
        return _error("O estado do painel mudou em outra aba; tente de novo.", 409)
    status = 201 if isinstance(payload, dict) and payload.get("acao") == "criar" else 200
    return {"coleta": coleta, "coletas": public_coletas(state)}, status


# --- POST /api/painel/sessoes/acoes -----------------------------------------------------


def _parse_session_ids(raw: Any) -> list[str] | None:
    if not isinstance(raw, list) or not 0 < len(raw) <= MAX_SESSIONS_PER_ACTION:
        return None
    ids = [_parse_safe_id(item) for item in raw]
    if any(sid is None for sid in ids):
        return None
    return list(dict.fromkeys(sid for sid in ids if sid))


async def _session_blob_names(session_id: str) -> list[str]:
    """Todos os blobs da sessão: lotes, comandos, notas e registro por turno."""
    names = [
        name
        for name, _ in await telemetry_store.list_blobs(SESSIONS_PREFIX)
        if _session_of(name, SESSIONS_PREFIX) == session_id
    ]
    for prefix in (COMMANDS_PREFIX, NOTES_PREFIX, INTERACTIONS_PREFIX):
        names += [name for name, _ in await telemetry_store.list_blobs(f"{prefix}{session_id}/")]
    return names


async def _erase_sessions(session_ids: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for sid in session_ids:
        names = await _session_blob_names(sid)
        await _gather_limited(names, telemetry_store.delete_blob, DOWNLOAD_CONCURRENCY)
        for name in names:
            _events_cache.pop(name, None)
            _json_cache.pop(name, None)
        counts[sid] = len(names)
    return counts


def _record_erased(state: dict[str, Any], counts: dict[str, int], now: str) -> None:
    for sid, blobs in counts.items():
        discarded = state["descartes"].pop(sid, None) or {}
        state["atribuicoes"].pop(sid, None)
        state["apagadas"].append(
            {"sessionId": sid, "em": now, "blobs": blobs, "motivo": discarded.get("motivo")}
        )


async def session_action(
    authorization: str | None, payload: Any, client: str = ""
) -> tuple[dict[str, Any], int]:
    """
    ``{"acao", "sessionIds": [...], "coletaId"?, "motivo"?}``.

    ``mover`` com ``coletaId: null`` tira a sessão de qualquer coleta. ``apagar`` exige
    que todas as sessões estejam na lixeira (409 caso contrário) e não tem volta.
    """
    denied = check_conductor_auth(authorization, client)
    if denied is not None:
        return denied
    if not isinstance(payload, dict):
        return _error("O corpo JSON deve ser um objeto.", 400)
    action = payload.get("acao")
    if action not in SESSION_ACTIONS:
        return _error(f"'acao' deve ser um de: {', '.join(SESSION_ACTIONS)}.", 400)
    session_ids = _parse_session_ids(payload.get("sessionIds"))
    if session_ids is None:
        return _error(
            f"'sessionIds' deve ser uma lista de 1 a {MAX_SESSIONS_PER_ACTION} ids "
            "(até 64 caracteres em [A-Za-z0-9_-]).",
            400,
        )
    if not telemetry_store.is_configured():
        return _error("Armazenamento de telemetria não configurado.", 503)

    now = _now()
    try:
        if action == "apagar":
            state = await load_state()
            outside = [sid for sid in session_ids if sid not in state["descartes"]]
            if outside:
                return _error("Só se apaga de vez o que já está na lixeira.", 409)
            counts = await _erase_sessions(session_ids)
            logger.warning("Sessões apagadas pelo condutor: %s", counts)
            state, _ = await mutate_state(lambda s: _record_erased(s, counts, now))
            return {"acao": action, "sessionIds": session_ids, "blobs": counts}, 200
        state, _ = await mutate_state(
            lambda s: apply_session_action(s, action, session_ids, payload, now)
        )
    except StateError as exc:
        return _error(str(exc), exc.status)
    except telemetry_store.VersionConflict:
        return _error("O estado do painel mudou em outra aba; tente de novo.", 409)
    return {"acao": action, "sessionIds": session_ids, "trashCount": len(state["descartes"])}, 200


# --- GET /api/painel/exportar -----------------------------------------------------------


def _ndjson(lines: list[dict[str, Any]]) -> str:
    return "".join(
        json.dumps(line, ensure_ascii=False, separators=(",", ":")) + "\n" for line in lines
    )


async def _session_events(session_ids: set[str]) -> dict[str, list[dict[str, Any]]]:
    names = [
        name
        for name, _ in await telemetry_store.list_blobs(SESSIONS_PREFIX)
        if name.endswith(".ndjson") and _session_of(name, SESSIONS_PREFIX) in session_ids
    ]
    batches = await _gather_limited(names, _events_of, DOWNLOAD_CONCURRENCY)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for name, batch in zip(names, batches, strict=True):
        grouped.setdefault(_session_of(name, SESSIONS_PREFIX) or "", []).extend(batch)
    return grouped


async def _session_interactions(session_ids: list[str]) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for sid in session_ids:
        names = sorted(
            name
            for name, _ in await telemetry_store.list_blobs(f"{INTERACTIONS_PREFIX}{sid}/")
            if name.endswith(".ndjson")
        )
        for batch in await _gather_limited(names, _events_of, DOWNLOAD_CONCURRENCY):
            lines.extend(batch)
    return lines


async def export_coleta(
    authorization: str | None, query: Mapping[str, str], client: str = ""
) -> tuple[str | dict[str, Any], int, str, str | None]:
    """
    ``(corpo, status, media_type, nome_do_arquivo)``; em erro o corpo é o ``dict`` JSON.

    ``formato``: ``eventos`` (telemetria deduplicada por ``(sessionId, seq)``, uma linha
    por evento com ``coletaId``), ``interacoes`` (registro por turno do tutor) ou
    ``resumo`` (CSV, uma linha por tarefa). Sessões na lixeira ficam de fora.
    """
    json_type = "application/json"
    denied = check_conductor_auth(authorization, client)
    if denied is not None:
        return denied[0], denied[1], json_type, None
    fmt = (query.get("formato") or "eventos").strip()
    if fmt not in EXPORT_FORMATS:
        body, status = _error(f"'formato' deve ser um de: {', '.join(EXPORT_FORMATS)}.", 400)
        return body, status, json_type, None
    if not telemetry_store.is_configured():
        body, status = _error("Armazenamento de telemetria não configurado.", 503)
        return body, status, json_type, None
    state = await load_state()
    coleta_id = (query.get("coleta") or "").strip()
    if find_coleta(state, coleta_id) is None:
        body, status = _error("Coleta não encontrada.", 404)
        return body, status, json_type, None

    sessions = await sessions_of_view(state, coleta_id, 0, datetime.now(UTC))
    sessions.sort(key=lambda s: (s["firstEventAt"] or "", s["sessionId"] or ""))
    session_ids = [s["sessionId"] for s in sessions if s["sessionId"]]
    media_type, extension = EXPORT_FORMATS[fmt]
    filename = f"{coleta_id}-{fmt}.{extension}"

    if fmt == "resumo":
        return summary_csv(coleta_id, sessions), 200, media_type, filename
    if fmt == "interacoes":
        lines = await _session_interactions(session_ids)
        return _ndjson([{**line, "coletaId": coleta_id} for line in lines]), 200, media_type, filename
    events = await _session_events(set(session_ids))
    lines = [
        {**event, "coletaId": coleta_id}
        for sid in session_ids
        for event in dedupe_events(events.get(sid, []))
    ]
    return _ndjson(lines), 200, media_type, filename


# --- GET /api/painel/conversa -----------------------------------------------------------

#: Teto por fala na conversa do painel; o turno inteiro sai na exportação ``interacoes``.
MAX_TURN_TEXT = 6000

#: A IDE grava os turnos do treino sob ``treino-{sessionId}`` (fora das trajetórias e da
#: exportação), mas o condutor lê a conversa inteira da sessão.
PRACTICE_PREFIX = "treino-"


def _clip(value: Any) -> str:
    text = value if isinstance(value, str) else ""
    return text if len(text) <= MAX_TURN_TEXT else text[:MAX_TURN_TEXT] + "…"


def _student_text(request: Any) -> str:
    """Fala do estudante neste turno: o último item do ``history``, se for dele.

    Turno sem fala nova (pedido de ajuda pelo botão) termina no ``assistant``; aí não há
    fala, e repetir o ``user`` anterior duplicaria a mensagem na conversa.
    """
    history = request.get("history") if isinstance(request, dict) else None
    last = history[-1] if isinstance(history, list) and history else None
    if isinstance(last, dict) and last.get("role") == "user":
        return _clip(last.get("content"))
    return ""


def conversation_turn(record: dict[str, Any]) -> dict[str, Any]:
    """Um turno do registro (``services.interaction_log``) no formato enxuto do painel."""
    response = record.get("response") if isinstance(record.get("response"), dict) else {}
    request = record.get("request") if isinstance(record.get("request"), dict) else {}
    errors = request.get("errors")
    return {
        "ts": record.get("ts"),
        "practice": str(record.get("sessionId") or "").startswith(PRACTICE_PREFIX),
        "endpoint": record.get("endpoint"),
        "student": _student_text(request),
        "tutor": _clip(response.get("message")),
        "intent": record.get("intent") or "",
        "movement": record.get("studentMovement") or "",
        "stagnationStreak": record.get("stagnationStreak"),
        "compilerErrors": len(errors) if isinstance(errors, list) else 0,
        "latencyMs": record.get("latencyMs"),
        "error": record.get("error"),
    }


async def session_conversation(
    authorization: str | None, query: Mapping[str, str], client: str = ""
) -> tuple[dict[str, Any], int]:
    """Turnos do tutor de uma sessão (``?sessao=<sessionId>``), treino incluído, em ordem."""
    denied = check_conductor_auth(authorization, client)
    if denied is not None:
        return denied
    session_id = _parse_safe_id(query.get("sessao"))
    if session_id is None:
        return _error("'sessao' inválida.", 400)
    if not telemetry_store.is_configured():
        return _error("Armazenamento de telemetria não configurado.", 503)
    records = await _session_interactions([f"{PRACTICE_PREFIX}{session_id}", session_id])
    turns = sorted(
        (conversation_turn(r) for r in records), key=lambda t: str(t["ts"] or "")
    )
    return {"sessionId": session_id, "turns": turns}, 200
