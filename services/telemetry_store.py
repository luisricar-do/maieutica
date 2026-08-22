"""
Persistência da telemetria em Azure Blob Storage.

Um blob de bloco por lote (ver ``services.telemetry.blob_name_for``): o lote é
imutável, logo a retentativa é idempotente e não há corrida de criação como
haveria num append blob compartilhado.

Configuração (``local.settings.json`` / App Settings):
  ``TELEMETRY_BLOB_CONNECTION_STRING`` — connection string da conta de armazenamento
  ``TELEMETRY_BLOB_CONTAINER``         — contentor (default: ``telemetria``)
"""

import asyncio
import logging
import os
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
