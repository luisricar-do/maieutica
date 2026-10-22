"""
Coletas, atribuição de sessões e lixeira do painel do condutor — funções puras, sem I/O.

O estado vive num único JSON (``painel/estado.json``, ver ``services.coletas_service``)::

    {
      "coletas":     [{"id", "nome", "data", "criadaEm", "abertaEm", "encerradaEm"}],
      "atribuicoes": {sessionId: coletaId | None},   # escolha manual do condutor
      "descartes":   {sessionId: {"em", "motivo"}},  # lixeira (reversível)
      "apagadas":    [{"sessionId", "em", "blobs"}]  # registro do que foi apagado de vez
    }

Uma sessão pertence a uma coleta por uma de duas vias:

1. **Manual**: o condutor moveu-a (``atribuicoes``). ``None`` quer dizer «sem coleta» e
   também vence a regra automática.
2. **Janela**: a coleta foi aberta e a sessão esteve viva dentro da janela
   ``[abertaEm, encerradaEm)`` — último sinal depois da abertura e primeiro antes do
   encerramento. Se duas janelas servem, fica a aberta mais recentemente.

A janela usa ``firstEventAt``/``lastEventAt`` do resumo, que vêm do ``serverTs``: o
relógio do aluno não decide a coleta. A telemetria não é alterada: a coleta é um rótulo
do painel, aplicado na leitura e na exportação.
"""

import csv
import io
import re
import unicodedata
from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

MAX_NAME_LENGTH = 80
MAX_REASON_LENGTH = 200
MAX_ID_LENGTH = 64

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


class StateError(Exception):
    """Pedido inválido sobre o estado; ``status`` é o código HTTP a devolver."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def empty_state() -> dict[str, Any]:
    return {"coletas": [], "atribuicoes": {}, "descartes": {}, "apagadas": []}


def normalize_state(raw: Any) -> dict[str, Any]:
    """Estado lido do blob, com as chaves que faltarem (blob novo ou de versão antiga)."""
    state = empty_state()
    if not isinstance(raw, dict):
        return state
    if isinstance(raw.get("coletas"), list):
        state["coletas"] = [c for c in raw["coletas"] if isinstance(c, dict) and c.get("id")]
    for key in ("atribuicoes", "descartes"):
        if isinstance(raw.get(key), dict):
            state[key] = dict(raw[key])
    if isinstance(raw.get("apagadas"), list):
        state["apagadas"] = list(raw["apagadas"])
    return state


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def find_coleta(state: dict[str, Any], coleta_id: Any) -> dict[str, Any] | None:
    for coleta in state["coletas"]:
        if coleta["id"] == coleta_id:
            return coleta
    return None


def _require_coleta(state: dict[str, Any], coleta_id: Any) -> dict[str, Any]:
    coleta = find_coleta(state, coleta_id)
    if coleta is None:
        raise StateError("Coleta não encontrada.", 404)
    return coleta


def coleta_status(coleta: dict[str, Any]) -> str:
    if coleta.get("encerradaEm"):
        return "encerrada"
    if coleta.get("abertaEm"):
        return "aberta"
    return "planejada"


# --- Pertença de uma sessão -------------------------------------------------------------


def coleta_of_session(
    session_id: str, first_at: str | None, last_at: str | None, state: dict[str, Any]
) -> str | None:
    """``id`` da coleta da sessão, ou ``None`` (sem coleta)."""
    assignments = state["atribuicoes"]
    if session_id in assignments:
        chosen = assignments[session_id]
        return chosen if find_coleta(state, chosen) is not None else None
    first, last = _parse_iso(first_at), _parse_iso(last_at)
    if first is None or last is None:
        return None
    best: tuple[datetime, str] | None = None
    for coleta in state["coletas"]:
        opened = _parse_iso(coleta.get("abertaEm"))
        if opened is None or last < opened:
            continue
        closed = _parse_iso(coleta.get("encerradaEm"))
        if closed is not None and first >= closed:
            continue
        if best is None or opened > best[0]:
            best = (opened, coleta["id"])
    return best[1] if best else None


# --- Coletas ----------------------------------------------------------------------------


def _clean_name(raw: Any) -> str:
    name = raw.strip() if isinstance(raw, str) else ""
    if not name or len(name) > MAX_NAME_LENGTH:
        raise StateError(f"'nome' é obrigatório (1 a {MAX_NAME_LENGTH} caracteres).")
    return name


def _clean_date(raw: Any) -> str:
    if isinstance(raw, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw.strip()):
        try:
            return date.fromisoformat(raw.strip()).isoformat()
        except ValueError:
            pass
    raise StateError("'data' deve estar no formato AAAA-MM-DD.")


def slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return _SLUG_STRIP.sub("-", ascii_text.lower()).strip("-")


def new_coleta_id(state: dict[str, Any], name: str, day: str) -> str:
    """``{data}-{slug do nome}``, legível no nome do arquivo exportado; único no estado."""
    base = f"{day}-{slugify(name)}".strip("-")[: MAX_ID_LENGTH - 4].strip("-")
    candidate, suffix = base, 2
    while find_coleta(state, candidate) is not None:
        candidate, suffix = f"{base}-{suffix}", suffix + 1
    return candidate


def _open(state: dict[str, Any], coleta: dict[str, Any], now: str) -> None:
    """Abre (ou reabre) ``coleta`` e encerra a que estiver aberta: uma janela de cada vez."""
    for other in state["coletas"]:
        if other is not coleta and coleta_status(other) == "aberta":
            other["encerradaEm"] = now
    if coleta.get("abertaEm") is None:
        coleta["abertaEm"] = now
    coleta["encerradaEm"] = None


def apply_coleta_action(
    state: dict[str, Any], payload: Any, now: str
) -> dict[str, Any] | None:
    """
    Aplica ``{"acao": criar|abrir|encerrar|editar|excluir, ...}`` ao estado (in place).

    Devolve a coleta afetada (``None`` em ``excluir``). Reabrir uma encerrada mantém o
    ``abertaEm`` original: a janela volta a valer desde o início.
    """
    if not isinstance(payload, dict):
        raise StateError("O corpo JSON deve ser um objeto.")
    action = payload.get("acao")

    if action == "criar":
        name, day = _clean_name(payload.get("nome")), _clean_date(payload.get("data"))
        coleta = {
            "id": new_coleta_id(state, name, day),
            "nome": name,
            "data": day,
            "criadaEm": now,
            "abertaEm": None,
            "encerradaEm": None,
        }
        state["coletas"].append(coleta)
        if payload.get("abrir") is True:
            _open(state, coleta, now)
        return coleta

    coleta = _require_coleta(state, payload.get("id"))
    if action == "abrir":
        _open(state, coleta, now)
    elif action == "encerrar":
        if coleta_status(coleta) != "aberta":
            raise StateError("Só uma coleta aberta pode ser encerrada.", 409)
        coleta["encerradaEm"] = now
    elif action == "editar":
        if payload.get("nome") is not None:
            coleta["nome"] = _clean_name(payload["nome"])
        if payload.get("data") is not None:
            coleta["data"] = _clean_date(payload["data"])
    elif action == "excluir":
        state["coletas"].remove(coleta)
        state["atribuicoes"] = {
            sid: cid for sid, cid in state["atribuicoes"].items() if cid != coleta["id"]
        }
        return None
    else:
        raise StateError("'acao' deve ser um de: criar, abrir, encerrar, editar, excluir.")
    return coleta


# --- Sessões: mover, lixeira ------------------------------------------------------------

SESSION_ACTIONS = ("mover", "descartar", "restaurar", "apagar")


def apply_session_action(
    state: dict[str, Any], action: str, session_ids: list[str], payload: dict[str, Any], now: str
) -> None:
    """``mover``, ``descartar`` e ``restaurar`` (in place). ``apagar`` tem I/O: ver serviço."""
    if action == "mover":
        target = payload.get("coletaId")
        if target is not None:
            _require_coleta(state, target)
        for sid in session_ids:
            state["atribuicoes"][sid] = target
    elif action == "descartar":
        raw_reason = payload.get("motivo")
        reason = raw_reason.strip()[:MAX_REASON_LENGTH] if isinstance(raw_reason, str) else ""
        for sid in session_ids:
            state["descartes"].setdefault(sid, {"em": now, "motivo": reason or None})
    elif action == "restaurar":
        for sid in session_ids:
            state["descartes"].pop(sid, None)
    else:
        raise StateError(f"'acao' deve ser um de: {', '.join(SESSION_ACTIONS)}.")


def public_coletas(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Coletas para o painel: abertas primeiro, depois por data e criação (recentes antes)."""
    items = [{**c, "status": coleta_status(c)} for c in state["coletas"]]
    items.sort(key=lambda c: (c["data"] or "", c.get("criadaEm") or ""), reverse=True)
    items.sort(key=lambda c: c["status"] != "aberta")
    return items


# --- Exportação -------------------------------------------------------------------------

SUMMARY_COLUMNS = (
    "coletaId",
    "sessionId",
    "participantId",
    "installId",
    "buildSha",
    "isTest",
    "sessionEnded",
    "chatTurns",
    "tutorErrors",
    "ordem",
    "task",
    "label",
    "practice",
    "startedAt",
    "endedAt",
    "outcome",
    "endedBy",
    "elapsedMs",
    "timeboxMs",
    "studentTurns",
    "checks",
    "failedChecks",
)


def summary_csv(coleta_id: str, sessions: Iterable[dict[str, Any]]) -> str:
    """Uma linha por tarefa de cada sessão (sessão sem tarefa: uma linha com a tarefa vazia)."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=SUMMARY_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for session in sessions:
        base = {key: session.get(key) for key in SUMMARY_COLUMNS[1:9]}
        base["coletaId"] = coleta_id
        tasks = session.get("tasks") or [{}]
        for order, task in enumerate(tasks, start=1):
            writer.writerow({**base, **task, "ordem": order if task else None})
    return buffer.getvalue()
