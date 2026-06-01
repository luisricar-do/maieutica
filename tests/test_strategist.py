from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from agents.analyst import Diagnosis
from agents.strategist import STRATEGIST_TOOLS, TUTOR_TOOLS, run_strategist


def test_strategist_tools_includes_compare_and_documentation() -> None:
    names = {t.name for t in STRATEGIST_TOOLS}
    assert "compare_lines" in names
    assert "suggest_documentation" in names
    assert "scroll_to" in names
    assert "spotlight_block" in names
    assert "draw_data_flow" in names
    assert "activate_focus_mode" in names
    assert "pause_at_iteration" in names
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
async def test_run_strategist_type_mismatch_fallback_avoids_delimiter_language() -> None:
    diagnosis: Diagnosis = {
        "errorType": "type_mismatch",
        "errorLine": 4,
        "affectedVariable": "x",
        "errorDescription": "A variável x é inteira, mas recebe cadeia.",
        "hintAngle": "Compare o tipo declarado com o valor atribuído.",
        "severity": "medium",
    }
    with patch("agents.llm.ChatOpenAI") as mock_cls:
        bound = _patch_bound_chat(mock_cls)
        bound.ainvoke = AsyncMock(
            return_value=AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "highlight_line",
                        "args": {"line": 4, "color": "warning"},
                        "id": "c1",
                    }
                ],
            )
        )
        actions, plan = await run_strategist(diagnosis, [], 'inteiro x\nx = "hello"')
    assert actions == [{"type": "highlight_line", "payload": {"line": 4, "color": "warning"}}]
    assert "tipo declarado" in plan
    assert "fechamentos" not in plan
    assert "delimitadores" not in plan


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
    assert "`type_mismatch`: focus on the assignment line" in system_text
    assert "Never mention \"aberturas\"" in system_text


@pytest.mark.asyncio
async def test_run_strategist_includes_minimal_hint_escalation_pace() -> None:
    diagnosis: Diagnosis = {
        "errorType": "logic",
        "errorLine": 5,
        "affectedVariable": None,
        "errorDescription": "Resultado incorreto.",
        "hintAngle": "Compare a intenção com o resultado observado.",
        "severity": "medium",
    }
    history = [
        {"role": "user", "content": "Não entendi."},
        {"role": "assistant", "content": "Observe a linha destacada."},
        {"role": "user", "content": "Ainda não sei."},
        {"role": "assistant", "content": "Compare os valores."},
        {"role": "user", "content": "Qual é a ideia?"},
    ]
    captured: list = []

    async def capture_ainvoke(messages):
        captured.append(messages)
        return AIMessage(content="ok")

    with patch("agents.llm.ChatOpenAI") as mock_cls:
        bound = _patch_bound_chat(mock_cls)
        bound.ainvoke = AsyncMock(side_effect=capture_ainvoke)
        await run_strategist(
            diagnosis,
            history,
            "escreva(1)",
            hint_level=1,
        )
    system_text = captured[0][0].content
    assert "hint_level 1 (`Mínimo`)" in system_text
    assert "turns 4-5" in system_text
    assert "Learner debugging turns in current session: 3" in system_text
