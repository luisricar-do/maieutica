"""
Painel do condutor da coleta e canal de comandos remotos para a IDE.

Casos de uso por trás das rotas (ver ``function_app.py``):

- ``GET  /api/painel``              — página HTML (``services/painel.html``), anônima;
- ``GET  /api/painel/sessoes``      — resumo das sessões, exige o token do condutor;
- ``POST /api/painel/comandos``     — grava um comando (ou nota), exige o token;
- ``GET  /api/coleta/comandos``     — a IDE do aluno busca os comandos da sua sessão.

Armazenamento no mesmo contentor da telemetria (``services.telemetry_store``):
``comandos/{sessionId}/{id}.json`` e ``notas/{sessionId}/{id}.json``. Lotes de
telemetria, comandos e notas são imutáveis, logo o conteúdo já lido fica em cache
em memória pelo nome do blob.

O prefixo é ``painel`` e não ``admin``: no Azure Functions as rotas ``admin/...``
pertencem ao host.
"""

import asyncio
import hmac
import json
import logging
import os
import secrets
import time
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, TypeVar

from services import telemetry_store
from services.painel import (
    COMMAND_KINDS,
    group_by_session,
    summarize_session,
)
from services.telemetry import _parse_safe_id

logger = logging.getLogger(__name__)

ADMIN_TOKEN_ENV = "STUDY_ADMIN_TOKEN"

SESSIONS_PREFIX = "sessions/"
COMMANDS_PREFIX = "comandos/"
NOTES_PREFIX = "notas/"

DEFAULT_EXTEND_MINUTES = 5
MIN_EXTEND_MINUTES = 1
MAX_EXTEND_MINUTES = 30
MAX_NOTE_LENGTH = 500
MAX_AFTER_LENGTH = 64

#: Janela padrão de ``/api/painel/sessoes``: sessões cujo último lote chegou há menos de
#: tantas horas. ``horas=0`` desliga o filtro (baixa a coleta inteira na primeira vez).
DEFAULT_WINDOW_HOURS = 24
MAX_WINDOW_HOURS = 24 * 120

#: Downloads simultâneos de blobs (cada um numa thread do SDK síncrono).
DOWNLOAD_CONCURRENCY = 16

PAINEL_HTML_PATH = Path(__file__).with_name("painel.html")

#: Senhas erradas seguidas, por cliente, antes de bloquear: a senha do condutor pode ser
#: curta (um PIN), e sem isso cairia por força bruta em minutos.
MAX_AUTH_FAILURES = 5
AUTH_LOCKOUT_SECONDS = 15 * 60

#: ``cliente -> (falhas seguidas, instante da última)``; um por réplica, como o cache.
_auth_failures: dict[str, tuple[int, float]] = {}

_events_cache: dict[str, list[dict[str, Any]]] = {}
_json_cache: dict[str, dict[str, Any]] = {}

T = TypeVar("T")


def reset_cache() -> None:
    """Esvazia o cache de blobs lidos (testes)."""
    _events_cache.clear()
    _json_cache.clear()
    _auth_failures.clear()


def _utc_iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _error(message: str, status: int) -> tuple[dict[str, Any], int]:
    return {"error": message}, status


# --- Autenticação ---------------------------------------------------------------------


def admin_token() -> str:
    return (os.getenv(ADMIN_TOKEN_ENV) or "").strip()


def check_conductor_auth(
    authorization: str | None, client: str = "", *, now: float | None = None
) -> tuple[dict[str, Any], int] | None:
    """
    ``None`` se o pedido traz ``Authorization: Bearer <STUDY_ADMIN_TOKEN>``.

    Sem a variável configurada o painel fica desligado (503), para não haver token
    vazio que aceite qualquer pedido; token ausente ou errado dá 401. Depois de
    ``MAX_AUTH_FAILURES`` erros seguidos o mesmo cliente recebe 429 por
    ``AUTH_LOCKOUT_SECONDS``, mesmo com a senha certa; acertar zera a contagem.
    """
    expected = admin_token()
    if not expected:
        return _error(f"Painel desativado: {ADMIN_TOKEN_ENV} não configurado.", 503)
    moment = time.monotonic() if now is None else now
    failures, last = _auth_failures.get(client, (0, 0.0))
    if failures and moment - last >= AUTH_LOCKOUT_SECONDS:
        failures = 0
    if failures >= MAX_AUTH_FAILURES:
        return _error("Muitas tentativas erradas. Tente de novo em 15 minutos.", 429)
    scheme, _, token = (authorization or "").strip().partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(
        token.strip().encode("utf-8"), expected.encode("utf-8")
    ):
        _auth_failures[client] = (failures + 1, moment)
        return _error("Token do condutor ausente ou inválido.", 401)
    _auth_failures.pop(client, None)
    return None


# --- Página ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def painel_html() -> str:
    """HTML autocontido do painel (sem dados: tudo chega por ``/api/painel/sessoes``)."""
    return PAINEL_HTML_PATH.read_text(encoding="utf-8")


# --- Leitura com cache ----------------------------------------------------------------


async def _gather_limited(
    items: list[str], fetch: Callable[[str], Awaitable[T]], limit: int
) -> list[T]:
    semaphore = asyncio.Semaphore(limit)

    async def run(item: str) -> T:
        async with semaphore:
            return await fetch(item)

    return await asyncio.gather(*(run(item) for item in items))


def _parse_ndjson(text: str) -> list[dict[str, Any]]:
    events = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            events.append(parsed)
    return events


async def _events_of(blob_name: str) -> list[dict[str, Any]]:
    cached = _events_cache.get(blob_name)
    if cached is None:
        cached = _parse_ndjson(await telemetry_store.read_text(blob_name))
        _events_cache[blob_name] = cached
    return cached


async def _json_of(blob_name: str) -> dict[str, Any]:
    cached = _json_cache.get(blob_name)
    if cached is None:
        try:
            parsed = json.loads(await telemetry_store.read_text(blob_name))
        except json.JSONDecodeError:
            parsed = {}
        cached = parsed if isinstance(parsed, dict) else {}
        _json_cache[blob_name] = cached
    return cached


def _session_of(blob_name: str, prefix: str) -> str | None:
    """``sessionId`` a partir do caminho do blob."""
    parts = blob_name[len(prefix):].split("/")
    if prefix == SESSIONS_PREFIX:
        return parts[1] if len(parts) >= 3 else None  # sessions/{inst}/{sid}/{faixa}
    return parts[0] if len(parts) >= 2 else None  # comandos|notas/{sid}/{id}.json


async def _jsons_by_session(
    prefix: str, wanted: set[str]
) -> dict[str, list[dict[str, Any]]]:
    names = [
        name
        for name, _ in await telemetry_store.list_blobs(prefix)
        if name.endswith(".json") and _session_of(name, prefix) in wanted
    ]
    docs = await _gather_limited(names, _json_of, DOWNLOAD_CONCURRENCY)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for name, doc in zip(names, docs, strict=True):
        grouped.setdefault(_session_of(name, prefix) or "", []).append(doc)
    return grouped


# --- GET /api/painel/sessoes ----------------------------------------------------------


def _parse_window_hours(raw: str | None) -> int | None:
    if raw is None or raw.strip() == "":
        return DEFAULT_WINDOW_HOURS
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if 0 <= value <= MAX_WINDOW_HOURS else None


def _recent_session_blobs(
    listing: list[tuple[str, datetime | None]], window_hours: int, now: datetime
) -> dict[str, list[str]]:
    """Blobs por sessão, só das sessões com algum lote dentro da janela."""
    by_session: dict[str, list[str]] = {}
    newest: dict[str, datetime | None] = {}
    for name, modified in listing:
        session_id = _session_of(name, SESSIONS_PREFIX)
        if session_id is None or not name.endswith(".ndjson"):
            continue
        by_session.setdefault(session_id, []).append(name)
        current = newest.get(session_id)
        if modified is not None and (current is None or modified > current):
            newest[session_id] = modified
    if window_hours == 0:
        return by_session
    cutoff = now - timedelta(hours=window_hours)
    return {
        sid: names
        for sid, names in by_session.items()
        # Sem ``last_modified`` (não deveria acontecer) a sessão entra: melhor sobrar.
        if newest.get(sid) is None or newest[sid] >= cutoff
    }


async def list_sessions(
    authorization: str | None, query: Mapping[str, str], client: str = ""
) -> tuple[dict[str, Any], int]:
    """Resumo de cada sessão recente, ordenado pelo último evento (mais recente primeiro)."""
    denied = check_conductor_auth(authorization, client)
    if denied is not None:
        return denied
    window_hours = _parse_window_hours(query.get("horas"))
    if window_hours is None:
        return _error(f"'horas' deve ser um inteiro entre 0 e {MAX_WINDOW_HOURS}.", 400)
    if not telemetry_store.is_configured():
        return _error("Armazenamento de telemetria não configurado.", 503)

    now = datetime.now(UTC)
    blobs = _recent_session_blobs(
        await telemetry_store.list_blobs(SESSIONS_PREFIX), window_hours, now
    )
    names = [name for session_names in blobs.values() for name in session_names]
    batches = await _gather_limited(names, _events_of, DOWNLOAD_CONCURRENCY)
    events = [event for batch in batches for event in batch]

    wanted = set(blobs)
    commands = await _jsons_by_session(COMMANDS_PREFIX, wanted)
    notes = await _jsons_by_session(NOTES_PREFIX, wanted)

    sessions = [
        summarize_session(session_events, commands.get(sid, ()), notes.get(sid, ()))
        for sid, session_events in group_by_session(events).items()
    ]
    sessions.sort(key=lambda s: s["lastEventAt"] or "", reverse=True)
    return {"generatedAt": _utc_iso(now), "sessions": sessions}, 200


# --- POST /api/painel/comandos --------------------------------------------------------


def new_command_id(now_ms: int | None = None) -> str:
    """``{epoch_ms:013d}-{6 hex}``: ordenável como string e sem colisão prática."""
    epoch_ms = int(time.time() * 1000) if now_ms is None else now_ms
    return f"{epoch_ms:013d}-{secrets.token_hex(3)}"


def _parse_minutes(raw: Any) -> int | None:
    if raw is None:
        return DEFAULT_EXTEND_MINUTES
    if isinstance(raw, bool) or not isinstance(raw, int):
        return None
    return raw if MIN_EXTEND_MINUTES <= raw <= MAX_EXTEND_MINUTES else None


def parse_command(payload: Any) -> tuple[dict[str, Any] | None, tuple[dict[str, Any], int] | None]:
    """
    Valida o corpo do ``POST``. Devolve ``(campos, None)`` ou ``(None, (erro, status))``.

    ``minutes`` só vale para ``extend`` e ``text`` só para ``note``: mandá-los noutro
    comando é erro, não silêncio.
    """
    if not isinstance(payload, dict):
        return None, _error("O corpo JSON deve ser um objeto.", 400)
    session_id = _parse_safe_id(payload.get("sessionId"))
    if session_id is None:
        return None, _error(
            "O campo 'sessionId' é obrigatório (até 64 caracteres em [A-Za-z0-9_-]).", 400
        )
    kind = payload.get("kind")
    if kind not in COMMAND_KINDS:
        return None, _error(f"O campo 'kind' deve ser um de: {', '.join(COMMAND_KINDS)}.", 400)

    fields: dict[str, Any] = {"sessionId": session_id, "kind": kind}
    minutes, text = payload.get("minutes"), payload.get("text")
    if minutes is not None and kind != "extend":
        return None, _error("'minutes' só se aplica a 'extend'.", 400)
    if text is not None and kind != "note":
        return None, _error("'text' só se aplica a 'note'.", 400)

    if kind == "extend":
        parsed = _parse_minutes(minutes)
        if parsed is None:
            return None, _error(
                f"'minutes' deve ser inteiro entre {MIN_EXTEND_MINUTES} e "
                f"{MAX_EXTEND_MINUTES}.",
                400,
            )
        fields["minutes"] = parsed
    if kind == "note":
        clean = text.strip() if isinstance(text, str) else ""
        if not clean or len(clean) > MAX_NOTE_LENGTH:
            return None, _error(
                f"'text' é obrigatório em 'note' (1 a {MAX_NOTE_LENGTH} caracteres).", 400
            )
        fields["text"] = clean
    return fields, None


async def create_command(
    authorization: str | None, payload: Any, client: str = ""
) -> tuple[dict[str, Any], int]:
    """Grava o comando em ``comandos/`` (ou a nota em ``notas/``) e devolve-o com 201."""
    denied = check_conductor_auth(authorization, client)
    if denied is not None:
        return denied
    fields, error = parse_command(payload)
    if error is not None:
        return error
    assert fields is not None
    if not telemetry_store.is_configured():
        return _error("Armazenamento de telemetria não configurado.", 503)

    command_id = new_command_id()
    command = {
        "id": command_id,
        **fields,
        "createdAt": _utc_iso(datetime.now(UTC)),
    }
    prefix = NOTES_PREFIX if fields["kind"] == "note" else COMMANDS_PREFIX
    blob_name = f"{prefix}{fields['sessionId']}/{command_id}.json"
    try:
        await telemetry_store.put_json(blob_name, command)
    except Exception:
        logger.exception("Falha ao gravar comando do condutor em %s", blob_name)
        return _error("Falha ao gravar o comando.", 500)
    _json_cache[blob_name] = command
    return command, 201


# --- GET /api/coleta/comandos ---------------------------------------------------------


def _command_for_ide(command: dict[str, Any]) -> dict[str, Any]:
    item: dict[str, Any] = {"id": command.get("id"), "kind": command.get("kind")}
    if command.get("minutes") is not None:
        item["minutes"] = command["minutes"]
    item["createdAt"] = command.get("createdAt")
    return item


async def commands_for_ide(query: Mapping[str, str]) -> tuple[dict[str, Any], int]:
    """
    Comandos de ``comandos/{sessionId}/`` com ``id > after``, por ordem de ``id``.

    Lista só o prefixo da sessão e lê só os blobs novos (o ``id`` está no nome), para o
    polling de cada máquina custar uma listagem pequena.
    """
    session_id = _parse_safe_id(query.get("sessionId"))
    if session_id is None:
        return _error(
            "O parâmetro 'sessionId' é obrigatório (até 64 caracteres em [A-Za-z0-9_-]).",
            400,
        )
    after = (query.get("after") or "").strip()
    if len(after) > MAX_AFTER_LENGTH:
        return _error(f"'after' excede {MAX_AFTER_LENGTH} caracteres.", 400)
    if not telemetry_store.is_configured():
        return _error("Armazenamento de telemetria não configurado.", 503)

    prefix = f"{COMMANDS_PREFIX}{session_id}/"
    names = sorted(
        name
        for name, _ in await telemetry_store.list_blobs(prefix)
        if name.endswith(".json") and name[len(prefix):-len(".json")] > after
    )
    docs = await _gather_limited(names, _json_of, DOWNLOAD_CONCURRENCY)
    commands = [_command_for_ide(doc) for doc in docs if doc.get("id")]
    commands.sort(key=lambda c: c["id"])
    return {"commands": commands}, 200
