"""Testes do roteador de intenção (LLM mockado)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.router import (
    CASUAL_STRATEGIST_PLAN,
    OUT_OF_SCOPE_STRATEGIST_PLAN,
    IntentClassification,
    IntentLabel,
    run_router,
)


@pytest.mark.asyncio
async def test_run_router_returns_casual_extras() -> None:
    classification = IntentClassification(intent=IntentLabel.CASUAL)

    with patch("agents.router._create_router_llm") as mock_factory:
        mock_llm = MagicMock()
        mock_structured = MagicMock()
        mock_factory.return_value = mock_llm
        mock_llm.with_structured_output.return_value = mock_structured
        mock_structured.ainvoke = AsyncMock(return_value=classification)

        out = await run_router(
            {
                "history": [{"role": "user", "content": "obrigado!"}],
                "code": "x",
                "errors": [],
            }
        )

    assert out["intent"] == "CASUAL"
    assert out["strategist_plan"] == CASUAL_STRATEGIST_PLAN
    assert out["actions"] == []


@pytest.mark.asyncio
async def test_run_router_theory_no_extras() -> None:
    classification = IntentClassification(intent=IntentLabel.THEORY)

    with patch("agents.router._create_router_llm") as mock_factory:
        mock_llm = MagicMock()
        mock_factory.return_value = mock_llm
        mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=classification
        )

        out = await run_router(
            {
                "history": [{"role": "user", "content": "O que é um vetor?"}],
                "code": "programa",
                "errors": [],
            }
        )

    assert out == {"intent": "THEORY"}


@pytest.mark.asyncio
async def test_run_router_out_of_scope_returns_redirect_plan() -> None:
    classification = IntentClassification(intent=IntentLabel.OUT_OF_SCOPE)

    with patch("agents.router._create_router_llm") as mock_factory:
        mock_llm = MagicMock()
        mock_factory.return_value = mock_llm
        mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=classification
        )

        out = await run_router(
            {
                "history": [{"role": "user", "content": "Quem foi Einstein?"}],
                "code": "programa teste",
                "errors": [],
            }
        )

    assert out["intent"] == "OUT_OF_SCOPE"
    assert out["strategist_plan"] == OUT_OF_SCOPE_STRATEGIST_PLAN
    assert out["actions"] == []


@pytest.mark.asyncio
async def test_run_router_blocks_obvious_out_of_scope_without_llm() -> None:
    with patch("agents.router._create_router_llm") as mock_factory:
        out = await run_router(
            {
                "history": [{"role": "user", "content": "Me conta uma piada"}],
                "code": "programa teste",
                "errors": [],
            }
        )

    mock_factory.assert_not_called()
    assert out["intent"] == "OUT_OF_SCOPE"
    assert out["strategist_plan"] == OUT_OF_SCOPE_STRATEGIST_PLAN
    assert out["actions"] == []


@pytest.mark.asyncio
async def test_run_router_keeps_programming_examples_in_theory() -> None:
    classification = IntentClassification(intent=IntentLabel.THEORY)

    with patch("agents.router._create_router_llm") as mock_factory:
        mock_llm = MagicMock()
        mock_factory.return_value = mock_llm
        mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=classification
        )

        out = await run_router(
            {
                "history": [{"role": "user", "content": "Me dá só um exemplo de loop"}],
                "code": "programa teste",
                "errors": [],
            }
        )

    assert out == {"intent": "THEORY"}
