from unittest.mock import AsyncMock, patch

import pytest

from agents.graph import build_graph


@pytest.mark.asyncio
async def test_graph_runs_analyst_then_tutor_in_sequence() -> None:
    diagnosis = {
        "errorType": "syntax",
        "errorLine": 1,
        "affectedVariable": None,
        "errorDescription": "teste",
        "hintAngle": "pergunta",
        "severity": "low",
    }

    call_order: list[str] = []

    async def analyst_impl(*_args, **_kwargs):
        call_order.append("analyst")
        return diagnosis

    async def tutor_impl(*_args, **_kwargs):
        call_order.append("tutor")
        return "Resposta socrática de teste."

    with (
        patch("agents.graph.run_analyst", new_callable=AsyncMock) as mock_analyst,
        patch("agents.graph.run_tutor", new_callable=AsyncMock) as mock_tutor,
    ):
        mock_analyst.side_effect = analyst_impl
        mock_tutor.side_effect = tutor_impl

        graph = build_graph()
        final = await graph.ainvoke(
            {
                "code": "escreva(1)",
                "errors": ["erro"],
                "history": [],
                "diagnosis": {},
                "tutor_response": "",
                "actions": [],
            }
        )

        mock_analyst.assert_awaited_once()
        mock_tutor.assert_awaited_once()
        assert call_order == ["analyst", "tutor"]
        assert final["diagnosis"] == diagnosis
        assert final["tutor_response"] == "Resposta socrática de teste."
        assert final["actions"] == []
