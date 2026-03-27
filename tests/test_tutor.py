from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk

from agents.tutor import run_communicator, run_communicator_stream


def _patch_chat_client(mock_cls: MagicMock) -> MagicMock:
    instance = mock_cls.return_value
    # Comunicador não usa bind_tools
    instance.bind_tools = MagicMock(side_effect=AssertionError("communicator must not bind_tools"))
    return instance


@pytest.mark.asyncio
async def test_run_communicator_returns_model_message() -> None:
    with patch("agents.llm.ChatOpenAI") as mock_cls:
        instance = _patch_chat_client(mock_cls)
        instance.ainvoke = AsyncMock(
            return_value=AIMessage(content="Ótimo esforço! O que você espera que aconteça aqui?")
        )
        out = await run_communicator("Plano: perguntar sobre o loop.", [])
    assert out == "Ótimo esforço! O que você espera que aconteça aqui?"


@pytest.mark.asyncio
async def test_run_communicator_includes_strategist_plan_in_system_message() -> None:
    captured: list = []

    async def capture_ainvoke(messages):
        captured.append(messages)
        return AIMessage(content="ok")

    with patch("agents.llm.ChatOpenAI") as mock_cls:
        instance = _patch_chat_client(mock_cls)
        instance.ainvoke = AsyncMock(side_effect=capture_ainvoke)
        await run_communicator("Destaquei linhas 2 e 4 para comparar.", [], intent="DEBUG")
    msgs = captured[0]
    system_text = msgs[0].content
    assert "<strategist_plan>" in system_text
    assert "Destaquei linhas 2 e 4 para comparar." in system_text


@pytest.mark.asyncio
async def test_run_communicator_casual_uses_casual_template() -> None:
    captured: list = []

    async def capture_ainvoke(messages):
        captured.append(messages)
        return AIMessage(content="ok")

    with patch("agents.llm.ChatOpenAI") as mock_cls:
        instance = _patch_chat_client(mock_cls)
        instance.ainvoke = AsyncMock(side_effect=capture_ainvoke)
        await run_communicator("hint casual", [], intent="CASUAL")
    system_text = captured[0][0].content
    assert "You are ARIA" in system_text
    assert "<internal_hint>" in system_text


@pytest.mark.asyncio
async def test_run_communicator_theory_includes_documentation() -> None:
    captured: list = []

    async def capture_ainvoke(messages):
        captured.append(messages)
        return AIMessage(content="ok")

    with patch("agents.llm.ChatOpenAI") as mock_cls:
        instance = _patch_chat_client(mock_cls)
        instance.ainvoke = AsyncMock(side_effect=capture_ainvoke)
        await run_communicator(
            "",
            [{"role": "user", "content": "O que é vetor?"}],
            intent="THEORY",
            documentation_context=["trecho doc"],
        )
    system_text = captured[0][0].content
    assert "<documentation>" in system_text
    assert "trecho doc" in system_text
    assert "Socratic" in system_text


@pytest.mark.asyncio
async def test_run_communicator_stream_yields_chunks() -> None:
    async def fake_astream(_messages):
        yield AIMessageChunk(content="A")
        yield AIMessageChunk(content="B")

    with patch("agents.llm.ChatOpenAI") as mock_cls:
        instance = _patch_chat_client(mock_cls)
        instance.astream = fake_astream
        parts = [p async for p in run_communicator_stream("plano interno", [])]
    assert parts == ["A", "B"]
