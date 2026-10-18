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
        "hint_level": 1,
        "student_name": "",
        "cursor_line": None,
        "cursor_column": None,
        "compiler_error_lines": [],
        "ast_summary": "",
        "data_flow_context": "",
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
        return [
            {"type": "highlight_line", "payload": {"line": 1, "color": "info"}}
        ], "plano interno"

    async def communicator_impl(*_args, **_kwargs):
        call_order.append("tutor")
        return "Resposta socrática de teste."

    with (
        patch("agents.graph.run_router", new_callable=AsyncMock) as mock_router,
        patch("agents.graph.run_analyst", new_callable=AsyncMock) as mock_analyst,
        patch("agents.graph.run_strategist", new_callable=AsyncMock) as mock_strategist,
        patch(
            "agents.graph.run_communicator", new_callable=AsyncMock
        ) as mock_communicator,
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
async def test_graph_passes_retrieved_docs_to_strategist_when_include_documentation() -> (
    None
):
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
        patch(
            "agents.graph.run_communicator", new_callable=AsyncMock
        ) as mock_communicator,
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
        patch(
            "agents.graph.run_communicator", new_callable=AsyncMock
        ) as mock_communicator,
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
        patch(
            "agents.graph.run_communicator", new_callable=AsyncMock
        ) as mock_communicator,
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


@pytest.mark.asyncio
async def test_graph_out_of_scope_skips_analyst_strategist_and_rag() -> None:
    with (
        patch("agents.graph.run_router", new_callable=AsyncMock) as mock_router,
        patch("agents.graph.run_analyst", new_callable=AsyncMock) as mock_analyst,
        patch("agents.graph.run_strategist", new_callable=AsyncMock) as mock_strategist,
        patch(
            "agents.graph.run_communicator", new_callable=AsyncMock
        ) as mock_communicator,
        patch("agents.graph.retrieve_doc_chunks") as mock_retrieve,
    ):
        mock_router.return_value = {
            "intent": "OUT_OF_SCOPE",
            "strategist_plan": "redirect",
            "actions": [],
        }
        mock_communicator.return_value = "Posso ajudar com Portugol."

        graph = build_graph()
        final = await graph.ainvoke(
            {
                **_base_state(),
                "history": [{"role": "user", "content": "Quem foi Einstein?"}],
            }
        )

        mock_analyst.assert_not_awaited()
        mock_strategist.assert_not_awaited()
        mock_retrieve.assert_not_called()
        mock_communicator.assert_awaited_once()
        _args, kwargs = mock_communicator.call_args
        assert kwargs.get("intent") == "OUT_OF_SCOPE"
        assert final["tutor_response"] == "Posso ajudar com Portugol."


@pytest.mark.asyncio
async def test_graph_leva_o_nivel_do_estrategista_ao_comunicador() -> None:
    diagnosis = {
        "errorType": "type_mismatch",
        "errorLine": 2,
        "affectedVariable": "x",
        "errorDescription": "teste",
        "hintAngle": "tipos",
        "severity": "low",
    }

    async def analyst_impl(*_args, **_kwargs):
        return diagnosis

    async def strategist_impl(*_args, **_kwargs):
        return [], "LEVEL: 2\nNomeie a incompatibilidade de tipo."

    estado = {
        **_base_state(),
        "history": [
            {"role": "assistant", "content": "Olhe a linha 2.", "concretenessLevel": 1},
            {"role": "user", "content": "não sei"},
        ],
        "student_movement": "ESTAGNACAO",
        "stagnation_streak": 4,
    }

    with (
        patch("agents.graph.run_router", new_callable=AsyncMock) as mock_router,
        patch("agents.graph.run_analyst", new_callable=AsyncMock) as mock_analyst,
        patch("agents.graph.run_strategist", new_callable=AsyncMock) as mock_strategist,
        patch("agents.graph.run_communicator", new_callable=AsyncMock) as mock_communicator,
    ):
        mock_router.return_value = {"intent": "DEBUG"}
        mock_analyst.side_effect = analyst_impl
        mock_strategist.side_effect = strategist_impl
        mock_communicator.return_value = "ok"

        final = await build_graph().ainvoke(estado)

    args, kwargs = mock_communicator.call_args
    assert args[0] == "Nomeie a incompatibilidade de tipo."
    assert kwargs["concreteness_level"] == 2
    assert final["concreteness_level"] == 2


async def _grafo_com_estrategista(plano_e_acoes, **estado_extra):
    diagnosis = {
        "errorType": "logic",
        "errorLine": 4,
        "affectedVariable": "",
        "errorDescription": "teste",
        "hintAngle": "fluxo",
        "severity": "low",
    }

    async def strategist_impl(*_args, **_kwargs):
        return plano_e_acoes

    with (
        patch("agents.graph.run_router", new_callable=AsyncMock) as mock_router,
        patch("agents.graph.run_analyst", new_callable=AsyncMock) as mock_analyst,
        patch("agents.graph.run_strategist", new_callable=AsyncMock) as mock_strategist,
        patch("agents.graph.run_communicator", new_callable=AsyncMock) as mock_communicator,
    ):
        mock_router.return_value = {"intent": "DEBUG"}
        mock_analyst.return_value = diagnosis
        mock_strategist.side_effect = strategist_impl
        mock_communicator.return_value = "ok"
        final = await build_graph().ainvoke({**_base_state(), **estado_extra})
    return final, mock_communicator.call_args


@pytest.mark.asyncio
async def test_graph_le_o_nivel_da_tool_e_nao_a_repassa_a_ide() -> None:
    acoes = [
        {"type": "set_concreteness_level", "payload": {"level": 1}},
        {"type": "highlight_line", "payload": {"line": 4, "color": "yellow"}},
    ]
    final, (args, kwargs) = await _grafo_com_estrategista(
        (acoes, "Aponte o laço da linha 4."),
        history=[
            {"role": "assistant", "content": "O que o programa mostra?", "concretenessLevel": 1},
            {"role": "user", "content": "não sei"},
        ],
        student_movement="ESTAGNACAO",
        stagnation_streak=2,
    )
    assert kwargs["concreteness_level"] == 1
    assert final["declared_concreteness_level"] == 1
    assert [a["type"] for a in final["actions"]] == ["highlight_line"]
    assert args[0] == "Aponte o laço da linha 4."


@pytest.mark.asyncio
async def test_graph_escala_mesmo_quando_o_modelo_nao_declara_nivel() -> None:
    """O caso que a versão anterior deixou passar: o modelo real omitia o nível e o mock o dava."""
    final, (_args, kwargs) = await _grafo_com_estrategista(
        ([{"type": "highlight_line", "payload": {"line": 4}}], "Pergunte sobre o laço."),
        history=[
            {"role": "assistant", "content": "Olhe a linha 4.", "concretenessLevel": 1},
            {"role": "user", "content": "to travado"},
        ],
        student_movement="ESTAGNACAO",
        stagnation_streak=4,
    )
    assert final["declared_concreteness_level"] is None
    assert kwargs["concreteness_level"] == 2
    assert final["concreteness_level"] == 2
