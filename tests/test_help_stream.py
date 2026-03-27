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
async def test_iter_help_sse_happy_path_actions_before_tokens() -> None:
    async def fake_communicator_stream(*_a, **_k):
        yield "Oi"
        yield "!"

    async def fake_analyst_node(*_a, **_k):
        return {"diagnosis": {"errorType": "none", "severity": "low"}}

    async def fake_strategist_node(*_a, **_k):
        return {
            "actions": [{"type": "highlight_line", "payload": {"line": 1, "color": "info"}}],
            "strategist_plan": "p",
        }

    with (
        patch("services.tutor_help_stream.run_router", new_callable=AsyncMock) as mr,
        patch("services.tutor_help_stream.analyst_node", new_callable=AsyncMock) as ma,
        patch("services.tutor_help_stream.strategist_node", new_callable=AsyncMock) as ms,
        patch("services.tutor_help_stream.run_communicator_stream", fake_communicator_stream),
    ):
        mr.return_value = {"intent": "DEBUG"}
        ma.side_effect = fake_analyst_node
        ms.side_effect = fake_strategist_node

        chunks = [
            c
            async for c in iter_help_sse(
                {"code": "x", "errors": [], "history": []}
            )
        ]
    decoded = [c.decode("utf-8") for c in chunks]
    assert any("diagnosis" in d for d in decoded)
    action_idx = next(i for i, d in enumerate(decoded) if "event: action" in d)
    token_indices = [i for i, d in enumerate(decoded) if "event: token" in d]
    assert token_indices
    assert action_idx < min(token_indices)
    assert sum(1 for d in decoded if "event: token" in d) == 2
    assert any("done" in d for d in decoded)


@pytest.mark.asyncio
async def test_iter_help_sse_calls_retrieve_when_include_documentation() -> None:
    async def fake_communicator_stream(*_a, **_k):
        yield "x"

    async def fake_analyst_node(*_a, **_k):
        return {
            "diagnosis": {
                "errorType": "none",
                "severity": "low",
                "errorDescription": "d",
                "hintAngle": "h",
            }
        }

    async def fake_strategist_node(*_a, **_k):
        return {"actions": [], "strategist_plan": "plan"}

    with (
        patch("services.tutor_help_stream.run_router", new_callable=AsyncMock) as mr,
        patch("services.tutor_help_stream.analyst_node", new_callable=AsyncMock) as ma,
        patch("services.tutor_help_stream.strategist_node", new_callable=AsyncMock) as ms,
        patch(
            "agents.graph.retrieve_doc_chunks",
            return_value=["doc-chunk"],
        ) as mock_retrieve,
        patch("services.tutor_help_stream.run_communicator_stream", fake_communicator_stream),
    ):
        mr.return_value = {"intent": "DEBUG"}
        ma.side_effect = fake_analyst_node
        ms.side_effect = fake_strategist_node

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
    async def fake_communicator_stream(*_a, **_k):
        yield "y"

    async def fake_analyst_node(*_a, **_k):
        return {"diagnosis": {"errorType": "none", "severity": "low"}}

    async def fake_strategist_node(*_a, **_k):
        return {"actions": [], "strategist_plan": "plan"}

    with (
        patch("services.tutor_help_stream.run_router", new_callable=AsyncMock) as mr,
        patch("services.tutor_help_stream.analyst_node", new_callable=AsyncMock) as ma,
        patch("services.tutor_help_stream.strategist_node", new_callable=AsyncMock) as ms,
        patch(
            "agents.graph.retrieve_doc_chunks",
        ) as mock_retrieve,
        patch("services.tutor_help_stream.run_communicator_stream", fake_communicator_stream),
    ):
        mr.return_value = {"intent": "DEBUG"}
        ma.side_effect = fake_analyst_node
        ms.side_effect = fake_strategist_node
        _chunks = [
            c
            async for c in iter_help_sse(
                {"code": "x", "errors": [], "history": [], "includeDocumentation": False}
            )
        ]
    mock_retrieve.assert_not_called()
