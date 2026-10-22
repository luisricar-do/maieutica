"""
Persistência da telemetria em Azure Blob Storage.

Um blob de bloco por lote (ver ``services.telemetry.blob_name_for``): o lote é
imutável, logo a retentativa é idempotente e não há corrida de criação como
haveria num append blob compartilhado.

O painel do condutor reaproveita o mesmo cliente para listar e ler os lotes e para
gravar comandos e notas em JSON (ver ``services.painel_service``).

Configuração (``local.settings.json`` / App Settings):
  ``TELEMETRY_BLOB_CONNECTION_STRING`` — connection string da conta de armazenamento
  ``TELEMETRY_BLOB_CONTAINER``         — contentor (default: ``telemetria``)
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

CONNECTION_STRING_ENV = "TELEMETRY_BLOB_CONNECTION_STRING"
CONTAINER_ENV = "TELEMETRY_BLOB_CONTAINER"
DEFAULT_CONTAINER = "telemetria"

_service_client: Any | None = None
_container_ready = False


def connection_string() -> str:
    return (os.getenv(CONNECTION_STRING_ENV) or "").strip()


def container_name() -> str:
    return (os.getenv(CONTAINER_ENV) or "").strip() or DEFAULT_CONTAINER


def is_configured() -> bool:
    return bool(connection_string())


def reset_client_cache() -> None:
    """Descarta o cliente memorizado (usado nos testes e ao trocar de configuração)."""
    global _service_client, _container_ready
    _service_client = None
    _container_ready = False


def _get_service_client() -> Any:
    global _service_client
    if _service_client is None:
        from azure.storage.blob import BlobServiceClient

        _service_client = BlobServiceClient.from_connection_string(connection_string())
    return _service_client


def _ensure_container(service: Any) -> None:
    global _container_ready
    if _container_ready:
        return
    from azure.core.exceptions import ResourceExistsError

    try:
        service.create_container(container_name())
    except ResourceExistsError:
        pass
    _container_ready = True


def _put_ndjson_sync(blob_name: str, content: str) -> None:
    from azure.core.exceptions import ResourceExistsError

    service = _get_service_client()
    _ensure_container(service)
    blob = service.get_blob_client(container=container_name(), blob=blob_name)
    try:
        blob.upload_blob(
            content.encode("utf-8"),
            overwrite=False,
            content_type="application/x-ndjson; charset=utf-8",
        )
    except ResourceExistsError:
        # Lote já persistido (retentativa do cliente): nada a fazer.
        logger.info("Lote de telemetria já existente, ignorado: %s", blob_name)


async def put_ndjson(blob_name: str, content: str) -> None:
    """Grava o lote sem bloquear o loop (SDK síncrono em thread separada)."""
    await asyncio.to_thread(_put_ndjson_sync, blob_name, content)


# --- Leitura e JSON avulso (painel do condutor e canal de comandos) ----------------------
#
# Mesmo cliente e mesmo contentor da telemetria: comandos (``comandos/``) e notas
# (``notas/``) do condutor ficam ao lado dos lotes (``sessions/``), também imutáveis.


def _list_blobs_sync(prefix: str) -> list[tuple[str, datetime | None]]:
    from azure.core.exceptions import ResourceNotFoundError

    service = _get_service_client()
    container = service.get_container_client(container_name())
    try:
        return [
            (props.name, getattr(props, "last_modified", None))
            for props in container.list_blobs(name_starts_with=prefix)
        ]
    except ResourceNotFoundError:
        # Contentor ainda não criado: nenhum lote chegou.
        return []


async def list_blobs(prefix: str) -> list[tuple[str, datetime | None]]:
    """``(nome, last_modified)`` de cada blob sob ``prefix``, em thread separada."""
    return await asyncio.to_thread(_list_blobs_sync, prefix)


def _read_text_sync(blob_name: str) -> str:
    service = _get_service_client()
    blob = service.get_blob_client(container=container_name(), blob=blob_name)
    return blob.download_blob().readall().decode("utf-8")


async def read_text(blob_name: str) -> str:
    """Conteúdo do blob como texto UTF-8, sem bloquear o loop."""
    return await asyncio.to_thread(_read_text_sync, blob_name)


def _put_json_sync(blob_name: str, obj: dict[str, Any]) -> None:
    service = _get_service_client()
    _ensure_container(service)
    blob = service.get_blob_client(container=container_name(), blob=blob_name)
    blob.upload_blob(
        json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        overwrite=False,
        content_type="application/json; charset=utf-8",
    )


async def put_json(blob_name: str, obj: dict[str, Any]) -> None:
    """Grava um JSON imutável (``overwrite=False``): o nome já é único por construção."""
    await asyncio.to_thread(_put_json_sync, blob_name, obj)
