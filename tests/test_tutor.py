from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk

from agents.analyst import Diagnosis
from agents.tutor import run_tutor, run_tutor_stream


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
        instance = mock_cls.return_value
        instance.ainvoke = AsyncMock(
            return_value=AIMessage(content="Ótimo esforço! O que você espera que aconteça aqui?")
        )
        out = await run_tutor(diagnosis, [])
    assert out == "Ótimo esforço! O que você espera que aconteça aqui?"


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
        instance = mock_cls.return_value
        instance.astream = fake_astream
        parts = [p async for p in run_tutor_stream(diagnosis, [])]
    assert parts == ["A", "B"]
