from unittest.mock import MagicMock, patch

import pytest
from azure.core.exceptions import ResourceExistsError

from services import telemetry_store


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    telemetry_store.reset_client_cache()
    yield
    telemetry_store.reset_client_cache()


def test_is_configured_follows_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(telemetry_store.CONNECTION_STRING_ENV, raising=False)
    assert telemetry_store.is_configured() is False
    monkeypatch.setenv(telemetry_store.CONNECTION_STRING_ENV, "  ")
    assert telemetry_store.is_configured() is False
    monkeypatch.setenv(telemetry_store.CONNECTION_STRING_ENV, "UseDevelopmentStorage=true")
    assert telemetry_store.is_configured() is True


def test_container_name_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(telemetry_store.CONTAINER_ENV, raising=False)
    assert telemetry_store.container_name() == telemetry_store.DEFAULT_CONTAINER
    monkeypatch.setenv(telemetry_store.CONTAINER_ENV, "outro")
    assert telemetry_store.container_name() == "outro"


@pytest.mark.asyncio
async def test_put_ndjson_uploads_without_overwrite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(telemetry_store.CONNECTION_STRING_ENV, "UseDevelopmentStorage=true")
    monkeypatch.setenv(telemetry_store.CONTAINER_ENV, "telemetria")
    blob = MagicMock()
    service = MagicMock()
    service.get_blob_client.return_value = blob

    with patch("services.telemetry_store._get_service_client", return_value=service):
        await telemetry_store.put_ndjson("sessions/a/b/1.ndjson", '{"seq":1}\n')

    service.create_container.assert_called_once_with("telemetria")
    service.get_blob_client.assert_called_once_with(
        container="telemetria", blob="sessions/a/b/1.ndjson"
    )
    args, kwargs = blob.upload_blob.call_args
    assert args[0] == b'{"seq":1}\n'
    assert kwargs["overwrite"] is False


@pytest.mark.asyncio
async def test_put_ndjson_is_idempotent_on_existing_blob(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(telemetry_store.CONNECTION_STRING_ENV, "UseDevelopmentStorage=true")
    blob = MagicMock()
    blob.upload_blob.side_effect = ResourceExistsError("já existe")
    service = MagicMock()
    service.get_blob_client.return_value = blob

    with patch("services.telemetry_store._get_service_client", return_value=service):
        await telemetry_store.put_ndjson("sessions/a/b/1.ndjson", "{}\n")


@pytest.mark.asyncio
async def test_container_is_created_once_per_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(telemetry_store.CONNECTION_STRING_ENV, "UseDevelopmentStorage=true")
    service = MagicMock()
    service.get_blob_client.return_value = MagicMock()

    with patch("services.telemetry_store._get_service_client", return_value=service):
        await telemetry_store.put_ndjson("sessions/a/b/1.ndjson", "{}\n")
        await telemetry_store.put_ndjson("sessions/a/b/2.ndjson", "{}\n")

    assert service.create_container.call_count == 1


@pytest.mark.asyncio
async def test_existing_container_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(telemetry_store.CONNECTION_STRING_ENV, "UseDevelopmentStorage=true")
    service = MagicMock()
    service.create_container.side_effect = ResourceExistsError("existe")
    service.get_blob_client.return_value = MagicMock()

    with patch("services.telemetry_store._get_service_client", return_value=service):
        await telemetry_store.put_ndjson("sessions/a/b/1.ndjson", "{}\n")
