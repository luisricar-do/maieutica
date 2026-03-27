from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from agents.analyst import Diagnosis
from agents.strategist import STRATEGIST_TOOLS, TUTOR_TOOLS, run_strategist


def test_strategist_tools_includes_compare_and_documentation() -> None:
    names = {t.name for t in STRATEGIST_TOOLS}
    assert "compare_lines" in names
    assert "suggest_documentation" in names
    assert STRATEGIST_TOOLS is TUTOR_TOOLS


def _patch_bound_chat(mock_cls: MagicMock) -> MagicMock:
    instance = mock_cls.return_value
    bound = MagicMock()
    instance.bind_tools = MagicMock(return_value=bound)
    return bound


@pytest.mark.asyncio
async def test_run_strategist_returns_actions_and_plan() -> None:
    diagnosis: Diagnosis = {
        "errorType": "none",
        "errorLine": None,
        "affectedVariable": None,
        "errorDescription": "",
        "hintAngle": "Ângulo",
        "severity": "low",
    }
    with patch("agents.llm.ChatOpenAI") as mock_cls:
        bound = _patch_bound_chat(mock_cls)
        bound.ainvoke = AsyncMock(
            return_value=AIMessage(
                content="Compare lines 1 and 3; ask about delimiters.",
                tool_calls=[
                    {
                        "name": "compare_lines",
                        "args": {"line1": 1, "line2": 3},
                        "id": "c1",
                    }
                ],
            )
        )
        actions, plan = await run_strategist(diagnosis, [], "x")
    assert plan == "Compare lines 1 and 3; ask about delimiters."
    assert actions == [{"type": "compare_lines", "payload": {"line1": 1, "line2": 3}}]


@pytest.mark.asyncio
async def test_run_strategist_tool_only_uses_fallback_plan() -> None:
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
                tool_calls=[
                    {
                        "name": "highlight_line",
                        "args": {"line": 2, "color": "warning"},
                        "id": "c1",
                    }
                ],
            )
        )
        actions, plan = await run_strategist(diagnosis, [], "x")
    assert actions == [{"type": "highlight_line", "payload": {"line": 2, "color": "warning"}}]
    assert "Diretriz:" in plan


@pytest.mark.asyncio
async def test_run_strategist_includes_documentation_in_system_when_provided() -> None:
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
        await run_strategist(
            diagnosis,
            [],
            "escreva(1)",
            documentation_context=["referência sobre vetores"],
        )
    msgs = captured[0]
    system_text = msgs[0].content
    assert "documentation_reference" in system_text
    assert "referência sobre vetores" in system_text
