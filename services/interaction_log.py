"""
Registro estruturado de cada chamada ao tutor (trajetórias de uso real e bancada).

Uma linha NDJSON por turno do tutor, com o corpo recebido, a resposta devolvida e os
metadados de reprodutibilidade. É desse registro que se derivam as trajetórias da avaliação:
para cada turno, o estado do código, os erros, a fala do estudante, o movimento classificado
e a fala do tutor.

Destino, por ordem: ``INTERACTION_LOG_DIR`` (ficheiro local, útil em bancada e
desenvolvimento) e/ou Azure Blob Storage, quando ``TELEMETRY_BLOB_CONNECTION_STRING`` está
configurado. Sem nenhum dos dois, o registro é desligado e a chamada segue normalmente.

Privacidade: ``studentName`` nunca é gravado; a identidade do turno é o ``sessionId`` gerado
pela IDE, associado ao pseudónimo do participante fora do sistema (planilha do pesquisador).
"""

import json
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agents.config import classificador_de_movimento
from services import telemetry_store

logger = logging.getLogger(__name__)

LOG_DIR_ENV = "INTERACTION_LOG_DIR"
BLOB_ENABLED_ENV = "INTERACTION_LOG_TO_BLOB"

#: Campos do pedido que entram no registro (``studentName`` fica fora por desenho).
_REQUEST_FIELDS = (
    "code",
    "errors",
    "compilerErrorLines",
    "history",
    "hintLevel",
    "includeDocumentation",
    "previousCode",
    "previousErrors",
    "activeTutorDecorations",
    "cursorLine",
    "cursorColumn",
    "astSummary",
    "dataFlowContext",
)

_TRUTHY = frozenset({"1", "true", "yes", "on", "sim"})


def log_dir() -> str:
    return (os.getenv(LOG_DIR_ENV) or "").strip()


def _blob_enabled() -> bool:
    raw = (os.getenv(BLOB_ENABLED_ENV) or "").strip().casefold()
    if raw:
        return raw in _TRUTHY
    return telemetry_store.is_configured()


def is_enabled() -> bool:
    return bool(log_dir()) or _blob_enabled()


def _sanitized_request(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    return {key: payload[key] for key in _REQUEST_FIELDS if key in payload}


def build_record(
    payload: Any,
    *,
    endpoint: str,
    session_id: str,
    response: dict[str, Any],
    intent: str = "",
    student_movement: str = "",
    movement_source: str = "",
    stagnation_streak: int = 0,
    stagnation_source: str = "",
    model: str = "",
    latency_ms: int | None = None,
    error: str | None = None,
    prompt_variant: str = "",
    prompt_sha256: str = "",
    context_sha256: str = "",
    finish_reason: str = "",
) -> dict[str, Any]:
    """Uma linha do registro: pedido (sem ``studentName``), resposta e metadados.

    ``prompt_variant``, ``prompt_sha256``, ``context_sha256`` e ``finish_reason`` só aparecem na
    rota de chamada única (``/api/help/single``): identificam a condição da bancada, o prompt e o
    molde exatos da corrida, e se o turno foi cortado no limite de tokens.
    """
    record: dict[str, Any] = {
        "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "sessionId": session_id or "sem-sessao",
        "endpoint": endpoint,
        "request": _sanitized_request(payload),
        "response": response,
        "intent": intent,
        "studentMovement": student_movement,
        "movementSource": movement_source,
        "stagnationStreak": max(0, int(stagnation_streak)),
        "stagnationSource": stagnation_source,
        # Quem classificou o movimento nesta corrida. Vai em cada linha, e não num cabeçalho de
        # sessão, porque o registro é uma linha por turno e os turnos de uma sessão podem
        # atravessar um redeploy do serviço.
        "classificadorDeMovimento": classificador_de_movimento(),
        "model": model,
    }
    if prompt_variant:
        record["promptVariant"] = prompt_variant
    if prompt_sha256:
        record["promptSha256"] = prompt_sha256
    if context_sha256:
        record["contextSha256"] = context_sha256
    if finish_reason:
        record["finishReason"] = finish_reason
    if latency_ms is not None:
        record["latencyMs"] = latency_ms
    if error:
        record["error"] = error
    return record


def _write_local(record: dict[str, Any]) -> None:
    directory = Path(log_dir())
    directory.mkdir(parents=True, exist_ok=True)
    day = record["ts"][:10]
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    with (directory / f"interactions-{day}.ndjson").open("a", encoding="utf-8") as fh:
        fh.write(line)


def blob_name_for(record: dict[str, Any]) -> str:
    """``interactions/{sessionId}/{ts}-{sufixo}.ndjson`` — um blob imutável por turno."""
    safe_ts = record["ts"].replace(":", "").replace("-", "")
    return f"interactions/{record['sessionId']}/{safe_ts}-{uuid.uuid4().hex[:8]}.ndjson"


async def log_interaction(record: dict[str, Any]) -> None:
    """
    Persiste um turno. Nunca propaga exceção: falha de registro não pode derrubar a resposta
    ao estudante — é registrada no log da aplicação e a análise reporta a perda.
    """
    if not is_enabled():
        return
    try:
        if log_dir():
            _write_local(record)
        if _blob_enabled() and telemetry_store.is_configured():
            content = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            await telemetry_store.put_ndjson(blob_name_for(record), content)
    except Exception:
        logger.exception("Falha ao registrar a interação (sessão %s)", record.get("sessionId"))
