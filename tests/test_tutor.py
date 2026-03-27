from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk

from agents.analyst import Diagnosis
from agents.tutor import (
    TOOL_ONLY_FALLBACK_CLEAR_PT,
    TOOL_ONLY_FALLBACK_MESSAGE_PT,
    TOOL_ONLY_FALLBACK_MIXED_CLEAR_AND_VISUAL_PT,
    run_tutor,
    run_tutor_stream,
)


def _patch_bound_chat(mock_cls: MagicMock) -> MagicMock:
    instance = mock_cls.return_value
    bound = MagicMock()
    instance.bind_tools = MagicMock(return_value=bound)
    return bound


@pytest.mark.asyncio
async def test_run_tutor_returns_model_message() -> None:
    diagnosis: Diagnosis = {
        "errorType": "none",
        "errorLine": None,
        "affectedVariable": None,
        "errorDescription": "",
        "hintAngle": "Como você testaria esse trecho?",
        "severity": "low",
    }
    with patch("agents.llm.ChatOpenAI") as mock_cls:
        bound = _patch_bound_chat(mock_cls)
        bound.ainvoke = AsyncMock(
            return_value=AIMessage(content="Ótimo esforço! O que você espera que aconteça aqui?")
        )
        out = await run_tutor(diagnosis, [], "")
    assert out == "Ótimo esforço! O que você espera que aconteça aqui?"


@pytest.mark.asyncio
async def test_run_tutor_tool_only_response_uses_fallback_message() -> None:
    diagnosis: Diagnosis = {
        "errorType": "none",
        "errorLine": None,
        "affectedVariable": None,
        "errorDescription": "",
        "hintAngle": "Como você testaria esse trecho?",
        "severity": "low",
    }
    with patch("agents.llm.ChatOpenAI") as mock_cls:
        bound = _patch_bound_chat(mock_cls)
        bound.ainvoke = AsyncMock(
            return_value=AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "highlight_line",
                        "args": {"line": 2, "color": "warning"},
                        "id": "c1",
                    }
                ],
            )
        )
        out = await run_tutor(diagnosis, [], "x")
    assert out == TOOL_ONLY_FALLBACK_MESSAGE_PT


@pytest.mark.asyncio
async def test_run_tutor_includes_documentation_context_in_system_message() -> None:
    diagnosis: Diagnosis = {
        "errorType": "none",
        "errorLine": None,
        "affectedVariable": None,
        "errorDescription": "",
        "hintAngle": "Ângulo",
        "severity": "low",
    }
    captured: list = []

    async def capture_ainvoke(messages):
        captured.append(messages)
        return AIMessage(content="ok")

    with patch("agents.llm.ChatOpenAI") as mock_cls:
        bound = _patch_bound_chat(mock_cls)
        bound.ainvoke = AsyncMock(side_effect=capture_ainvoke)
        await run_tutor(
            diagnosis,
            [],
            "escreva(1)",
            documentation_context=["referência sobre vetores"],
        )
    msgs = captured[0]
    system_text = msgs[0].content
    assert "Portugol documentation" in system_text
    assert "referência sobre vetores" in system_text


@pytest.mark.asyncio
async def test_run_tutor_stream_yields_chunks() -> None:
    diagnosis: Diagnosis = {
        "errorType": "none",
        "errorLine": None,
        "affectedVariable": None,
        "errorDescription": "",
        "hintAngle": "Como você testaria esse trecho?",
        "severity": "low",
    }

    async def fake_astream(_messages):
        yield AIMessageChunk(content="A")
        yield AIMessageChunk(content="B")

    with patch("agents.llm.ChatOpenAI") as mock_cls:
        bound = _patch_bound_chat(mock_cls)
        bound.astream = fake_astream
        parts = [p async for p in run_tutor_stream(diagnosis, [], "")]
    assert parts == ["A", "B"]


@pytest.mark.asyncio
async def test_run_tutor_stream_no_tool_calls_emits_no_actions() -> None:
    diagnosis: Diagnosis = {
        "errorType": "none",
        "errorLine": None,
        "affectedVariable": None,
        "errorDescription": "",
        "hintAngle": "Como você testaria esse trecho?",
        "severity": "low",
    }

    async def fake_astream(_messages):
        yield AIMessageChunk(content="A")
        yield AIMessageChunk(content="B")

    with patch("agents.llm.ChatOpenAI") as mock_cls:
        bound = _patch_bound_chat(mock_cls)
        bound.astream = fake_astream
        parts = [p async for p in run_tutor_stream(diagnosis, [], "")]
    assert parts == ["A", "B"]
    assert not any(isinstance(p, dict) for p in parts)


@pytest.mark.asyncio
async def test_run_tutor_stream_emits_highlight_line_action() -> None:
    diagnosis: Diagnosis = {
        "errorType": "none",
        "errorLine": None,
        "affectedVariable": None,
        "errorDescription": "",
        "hintAngle": "Como você testaria esse trecho?",
        "severity": "low",
    }

    async def fake_astream(_messages):
        yield AIMessageChunk(
            content="Olá",
            tool_calls=[
                {
                    "name": "highlight_line",
                    "args": {"line": 14, "color": "warning"},
                    "id": "call_1",
                }
            ],
        )

    with patch("agents.llm.ChatOpenAI") as mock_cls:
        bound = _patch_bound_chat(mock_cls)
        bound.astream = fake_astream
        parts = [p async for p in run_tutor_stream(diagnosis, [], "")]

    assert parts[0] == "Olá"
    assert parts[1] == {"type": "highlight_line", "payload": {"line": 14, "color": "warning"}}


@pytest.mark.asyncio
async def test_run_tutor_stream_emits_multiple_actions() -> None:
    diagnosis: Diagnosis = {
        "errorType": "none",
        "errorLine": None,
        "affectedVariable": None,
        "errorDescription": "",
        "hintAngle": "Como você testaria esse trecho?",
        "severity": "low",
    }

    async def fake_astream(_messages):
        yield AIMessageChunk(
            content="",
            tool_calls=[
                {
                    "name": "highlight_line",
                    "args": {"line": 1, "color": "info"},
                    "id": "a",
                },
                {
                    "name": "clear_highlights",
                    "args": {},
                    "id": "b",
                },
            ],
        )

    with patch("agents.llm.ChatOpenAI") as mock_cls:
        bound = _patch_bound_chat(mock_cls)
        bound.astream = fake_astream
        parts = [p async for p in run_tutor_stream(diagnosis, [], "")]

    assert parts == [
        TOOL_ONLY_FALLBACK_MIXED_CLEAR_AND_VISUAL_PT,
        {"type": "highlight_line", "payload": {"line": 1, "color": "info"}},
        {"type": "clear_highlights", "payload": {}},
    ]


@pytest.mark.asyncio
async def test_run_tutor_stream_clear_highlights_only_fallback_does_not_claim_visual_hint() -> None:
    diagnosis: Diagnosis = {
        "errorType": "none",
        "errorLine": None,
        "affectedVariable": None,
        "errorDescription": "",
        "hintAngle": "",
        "severity": "low",
    }

    async def fake_astream(_messages):
        yield AIMessageChunk(
            content="",
            tool_calls=[
                {
                    "name": "clear_highlights",
                    "args": {},
                    "id": "c",
                },
            ],
        )

    with patch("agents.llm.ChatOpenAI") as mock_cls:
        bound = _patch_bound_chat(mock_cls)
        bound.astream = fake_astream
        parts = [p async for p in run_tutor_stream(diagnosis, [], "")]

    assert parts[0] == TOOL_ONLY_FALLBACK_CLEAR_PT
    assert parts[1] == {"type": "clear_highlights", "payload": {}}


@pytest.mark.asyncio
async def test_run_tutor_clear_highlights_only_uses_clear_fallback() -> None:
    diagnosis: Diagnosis = {
        "errorType": "none",
        "errorLine": None,
        "affectedVariable": None,
        "errorDescription": "",
        "hintAngle": "",
        "severity": "low",
    }
    with patch("agents.llm.ChatOpenAI") as mock_cls:
        bound = _patch_bound_chat(mock_cls)
        bound.ainvoke = AsyncMock(
            return_value=AIMessage(
                content="",
                tool_calls=[{"name": "clear_highlights", "args": {}, "id": "x"}],
            )
        )
        out = await run_tutor(diagnosis, [], "")
    assert out == TOOL_ONLY_FALLBACK_CLEAR_PT
