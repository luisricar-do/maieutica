from unittest.mock import AsyncMock, patch

import pytest

from agents.graph import build_graph


def _base_state() -> dict:
    return {
        "code": "escreva(1)",
        "errors": ["erro"],
        "history": [],
        "active_tutor_decorations": 0,
        "include_documentation": False,
        "diagnosis": {},
        "documentation_context": [],
        "strategist_plan": "",
        "tutor_response": "",
        "actions": [],
        "intent": "",
    }


@pytest.mark.asyncio
async def test_graph_runs_analyst_strategist_then_communicator_in_sequence() -> None:
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

    async def strategist_impl(*_args, **_kwargs):
        call_order.append("strategist")
        return [{"type": "highlight_line", "payload": {"line": 1, "color": "info"}}], "plano interno"

    async def communicator_impl(*_args, **_kwargs):
        call_order.append("tutor")
        return "Resposta socrática de teste."

    with (
        patch("agents.graph.run_router", new_callable=AsyncMock) as mock_router,
        patch("agents.graph.run_analyst", new_callable=AsyncMock) as mock_analyst,
        patch("agents.graph.run_strategist", new_callable=AsyncMock) as mock_strategist,
        patch("agents.graph.run_communicator", new_callable=AsyncMock) as mock_communicator,
    ):
        mock_router.return_value = {"intent": "DEBUG"}
        mock_analyst.side_effect = analyst_impl
        mock_strategist.side_effect = strategist_impl
        mock_communicator.side_effect = communicator_impl

        graph = build_graph()
        final = await graph.ainvoke(_base_state())

        mock_analyst.assert_awaited_once()
        mock_strategist.assert_awaited_once()
        mock_communicator.assert_awaited_once()
        assert call_order == ["analyst", "strategist", "tutor"]
        assert final["diagnosis"] == diagnosis
        assert final["tutor_response"] == "Resposta socrática de teste."
        assert final["actions"] == [
            {"type": "highlight_line", "payload": {"line": 1, "color": "info"}},
        ]
        assert final["strategist_plan"] == "plano interno"


@pytest.mark.asyncio
async def test_graph_passes_retrieved_docs_to_strategist_when_include_documentation() -> None:
    diagnosis = {
        "errorType": "syntax",
        "errorLine": 1,
        "affectedVariable": None,
        "errorDescription": "teste",
        "hintAngle": "pergunta",
        "severity": "low",
    }

    async def analyst_impl(*_args, **_kwargs):
        return diagnosis

    async def strategist_impl(*_args, **_kwargs):
        return [], "p"

    async def communicator_impl(*_args, **_kwargs):
        return "Com doc"

    state = _base_state()
    state["include_documentation"] = True

    with (
        patch("agents.graph.run_router", new_callable=AsyncMock) as mock_router,
        patch("agents.graph.run_analyst", new_callable=AsyncMock) as mock_analyst,
        patch("agents.graph.run_strategist", new_callable=AsyncMock) as mock_strategist,
        patch("agents.graph.run_communicator", new_callable=AsyncMock) as mock_communicator,
        patch(
            "agents.graph.retrieve_doc_chunks",
            return_value=["trecho-a", "trecho-b"],
        ) as mock_retrieve,
    ):
        mock_router.return_value = {"intent": "DEBUG"}
        mock_analyst.side_effect = analyst_impl
        mock_strategist.side_effect = strategist_impl
        mock_communicator.side_effect = communicator_impl

        graph = build_graph()
        await graph.ainvoke(state)

    mock_retrieve.assert_called_once()
    mock_strategist.assert_awaited_once()
    _args, kwargs = mock_strategist.call_args
    assert kwargs.get("documentation_context") == ["trecho-a", "trecho-b"]


@pytest.mark.asyncio
async def test_graph_casual_skips_analyst_and_strategist() -> None:
    with (
        patch("agents.graph.run_router", new_callable=AsyncMock) as mock_router,
        patch("agents.graph.run_analyst", new_callable=AsyncMock) as mock_analyst,
        patch("agents.graph.run_strategist", new_callable=AsyncMock) as mock_strategist,
        patch("agents.graph.run_communicator", new_callable=AsyncMock) as mock_communicator,
    ):
        mock_router.return_value = {
            "intent": "CASUAL",
            "strategist_plan": "casual hint",
            "actions": [],
        }
        mock_communicator.return_value = "Obrigado por estudar!"

        graph = build_graph()
        final = await graph.ainvoke(_base_state())

        mock_analyst.assert_not_awaited()
        mock_strategist.assert_not_awaited()
        mock_communicator.assert_awaited_once()
        _args, kwargs = mock_communicator.call_args
        assert kwargs.get("intent") == "CASUAL"
        assert final["tutor_response"] == "Obrigado por estudar!"


@pytest.mark.asyncio
async def test_graph_theory_skips_analyst_strategist_uses_rag() -> None:
    with (
        patch("agents.graph.run_router", new_callable=AsyncMock) as mock_router,
        patch("agents.graph.run_analyst", new_callable=AsyncMock) as mock_analyst,
        patch("agents.graph.run_strategist", new_callable=AsyncMock) as mock_strategist,
        patch("agents.graph.run_communicator", new_callable=AsyncMock) as mock_communicator,
        patch(
            "agents.graph.retrieve_doc_chunks",
            return_value=["doc-theory"],
        ) as mock_retrieve,
    ):
        mock_router.return_value = {"intent": "THEORY"}
        mock_communicator.return_value = "Sobre vetores…"

        graph = build_graph()
        final = await graph.ainvoke(
            {
                **_base_state(),
                "history": [{"role": "user", "content": "O que é um vetor?"}],
            }
        )

        mock_analyst.assert_not_awaited()
        mock_strategist.assert_not_awaited()
        mock_retrieve.assert_called_once()
        mock_communicator.assert_awaited_once()
        _args, kwargs = mock_communicator.call_args
        assert kwargs.get("intent") == "THEORY"
        assert kwargs.get("documentation_context") == ["doc-theory"]
        assert final["documentation_context"] == ["doc-theory"]
