"""Testes do roteador de intenção (LLM mockado)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.router import CASUAL_STRATEGIST_PLAN, IntentClassification, IntentLabel, run_router


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
        mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(return_value=classification)

        out = await run_router(
            {
                "history": [{"role": "user", "content": "O que é um vetor?"}],
                "code": "programa",
                "errors": [],
            }
        )

    assert out == {"intent": "THEORY"}
