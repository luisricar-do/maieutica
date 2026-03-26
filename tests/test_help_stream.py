import json
from unittest.mock import AsyncMock, patch

import pytest

from services.tutor_help_stream import format_sse, iter_help_sse


def test_format_sse_includes_event_and_json() -> None:
    raw = format_sse("token", {"text": "x"})
    text = raw.decode("utf-8")
    assert "event: token" in text
    assert 'data: {"text": "x"}' in text
    assert text.endswith("\n\n")


@pytest.mark.asyncio
async def test_iter_help_sse_validation_error() -> None:
    chunks = [c async for c in iter_help_sse([])]
    assert len(chunks) == 1
    text = chunks[0].decode("utf-8")
    assert "event: error" in text
    data_line = next(line for line in text.split("\n") if line.startswith("data: "))
    body = json.loads(data_line.removeprefix("data: "))
    assert "error" in body


@pytest.mark.asyncio
async def test_iter_help_sse_happy_path() -> None:
    def fake_tutor_stream(_d, _h, _code, _active=0, **_kwargs):
        async def gen():
            yield "Oi"
            yield "!"

        return gen()

    with (
        patch("services.tutor_help_stream.run_analyst", new_callable=AsyncMock) as ma,
        patch("services.tutor_help_stream.run_tutor_stream", fake_tutor_stream),
    ):
        ma.return_value = {"errorType": "none", "severity": "low"}

        chunks = [
            c
            async for c in iter_help_sse(
                {"code": "x", "errors": [], "history": []}
            )
        ]
    decoded = [c.decode("utf-8") for c in chunks]
    assert any("diagnosis" in d for d in decoded)
    assert sum(1 for d in decoded if "token" in d) == 2
    assert any("done" in d for d in decoded)


@pytest.mark.asyncio
async def test_iter_help_sse_calls_retrieve_when_include_documentation() -> None:
    def fake_tutor_stream(_d, _h, _code, _active=0, **_kwargs):
        async def gen():
            yield "x"

        return gen()

    with (
        patch("services.tutor_help_stream.run_analyst", new_callable=AsyncMock) as ma,
        patch(
            "services.tutor_help_stream.retrieve_doc_chunks",
            return_value=["doc-chunk"],
        ) as mock_retrieve,
        patch("services.tutor_help_stream.run_tutor_stream", fake_tutor_stream),
    ):
        ma.return_value = {
            "errorType": "none",
            "severity": "low",
            "errorDescription": "d",
            "hintAngle": "h",
        }
        chunks = [
            c
            async for c in iter_help_sse(
                {
                    "code": "x",
                    "errors": ["e1"],
                    "history": [],
                    "includeDocumentation": True,
                }
            )
        ]
    mock_retrieve.assert_called_once()
    decoded = [c.decode("utf-8") for c in chunks]
    assert any("diagnosis" in d for d in decoded)
    assert any("token" in d for d in decoded)


@pytest.mark.asyncio
async def test_iter_help_sse_skips_retrieve_when_include_documentation_false() -> None:
    def fake_tutor_stream(_d, _h, _code, _active=0, **_kwargs):
        async def gen():
            yield "y"

        return gen()

    with (
        patch("services.tutor_help_stream.run_analyst", new_callable=AsyncMock) as ma,
        patch(
            "services.tutor_help_stream.retrieve_doc_chunks",
        ) as mock_retrieve,
        patch("services.tutor_help_stream.run_tutor_stream", fake_tutor_stream),
    ):
        ma.return_value = {"errorType": "none", "severity": "low"}
        _chunks = [
            c
            async for c in iter_help_sse(
                {"code": "x", "errors": [], "history": [], "includeDocumentation": False}
            )
        ]
    mock_retrieve.assert_not_called()
