from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.tutor_help import process_help_request


@pytest.mark.asyncio
async def test_process_help_rejects_empty_code() -> None:
    body, status = await process_help_request(
        {"code": "   ", "errors": [], "history": []}
    )
    assert status == 400
    assert "code" in body.get("error", "").lower()


@pytest.mark.asyncio
async def test_process_help_rejects_non_dict_payload() -> None:
    body, status = await process_help_request([])
    assert status == 400
    assert "error" in body


@pytest.mark.asyncio
async def test_process_help_success() -> None:
    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(
        return_value={
            "tutor_response": "Pergunta?",
            "diagnosis": {"errorType": "none"},
            "actions": [],
        }
    )
    with patch("services.tutor_help.tutor_graph", mock_graph):
        body, status = await process_help_request(
            {"code": "escreva(1)", "errors": [], "history": []}
        )
    assert status == 200
    assert body["message"] == "Pergunta?"
    assert body["diagnosis"]["errorType"] == "none"
    assert body["actions"] == []
    assert body["tutorMeta"]["suggestedConversationEnd"] is False
    assert body["tutorMeta"]["endReason"] == "none"
    mock_graph.ainvoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_help_passes_include_documentation_to_graph() -> None:
    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(
        return_value={
            "tutor_response": "ok",
            "diagnosis": {"errorType": "none"},
            "actions": [],
        }
    )
    with patch("services.tutor_help.tutor_graph", mock_graph):
        await process_help_request(
            {
                "code": "escreva(1)",
                "errors": [],
                "history": [],
                "includeDocumentation": True,
                "compilerErrorLines": [3, "2", 0, True, "x", 3],
            }
        )
    call_args = mock_graph.ainvoke.await_args
    state = call_args[0][0]
    assert state["include_documentation"] is True
    assert state["documentation_context"] == []
    assert state["strategist_plan"] == ""
    assert state["intent"] == ""
    assert state["hint_level"] == 1
    assert state["student_name"] == ""
    assert state["compiler_error_lines"] == [2, 3]


@pytest.mark.asyncio
async def test_process_help_includes_tutor_meta_bug_resolved() -> None:
    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(
        return_value={
            "tutor_response": "Parabéns!",
            "diagnosis": {"errorType": "none"},
            "actions": [{"type": "mark_bug_resolved", "payload": {}}],
        }
    )
    with patch("services.tutor_help.tutor_graph", mock_graph):
        body, status = await process_help_request(
            {"code": "escreva(1)", "errors": [], "history": []}
        )
    assert status == 200
    assert body["tutorMeta"]["suggestedConversationEnd"] is True
    assert body["tutorMeta"]["endReason"] == "bug_resolved"
    assert len(body["actions"]) == 1


@pytest.mark.asyncio
async def test_tutor_meta_soma_os_tokens_das_chamadas_do_grafo() -> None:
    """O custo do turno em A é a soma do roteador, analista, estrategista e comunicador."""
    from langchain_core.outputs import ChatGeneration, LLMResult
    from langchain_core.messages import AIMessage

    from services.tutor_help import build_tutor_meta_from_actions

    def _resultado(prompt: int, completion: int) -> LLMResult:
        return LLMResult(
            generations=[[ChatGeneration(message=AIMessage(content="x"))]],
            llm_output={
                "token_usage": {
                    "prompt_tokens": prompt,
                    "completion_tokens": completion,
                    "total_tokens": prompt + completion,
                }
            },
        )

    async def ainvoke(state, config=None):
        for coletor in (config or {}).get("callbacks", []):
            coletor.on_llm_end(_resultado(100, 10))
            coletor.on_llm_end(_resultado(400, 40))
            coletor.on_llm_end(_resultado(250, 25))
        return {"tutor_response": "E depois?", "diagnosis": {}, "actions": [], "intent": "DEBUG"}

    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(side_effect=ainvoke)
    with patch("services.tutor_help.tutor_graph", mock_graph):
        body, status = await process_help_request(
            {"code": "escreva(1)", "errors": [], "history": []}
        )

    assert status == 200
    assert body["tutorMeta"]["usage"] == {
        "promptTokens": 750,
        "completionTokens": 75,
        "totalTokens": 825,
        "calls": 3,
    }
    # Sem medição não se inventa zero: o campo simplesmente não vem (caso do SSE).
    assert "usage" not in build_tutor_meta_from_actions([], intent="DEBUG")


def test_tutor_meta_registra_o_nivel_de_dica_em_vigor() -> None:
    """O nível de dica sai no turno, e não só na configuração de quem correu a bancada.

    Ele modula o ritmo da escada de concretude e não o teto — o nível 3 é proibido em
    qualquer valor —, de modo que ler a diretividade de um turno sem saber que ritmo
    estava em vigor é ler metade do dado. Na corrida `cap4` o valor teve de ser ido buscar
    à configuração, porque o campo não existia.
    """
    from services.tutor_help import build_tutor_meta_from_actions

    meta = build_tutor_meta_from_actions([], intent="DEBUG", hint_level=2)
    assert meta["hintLevel"] == 2

    # Fora da faixa, satura: o contrato da rota já o faz, e o meta não contradiz o contrato.
    assert build_tutor_meta_from_actions([], hint_level=9)["hintLevel"] == 3
    assert build_tutor_meta_from_actions([], hint_level=-1)["hintLevel"] == 1

    # Sem valor, o campo não vem: zero não é "nível zero", é ausência de medição.
    assert "hintLevel" not in build_tutor_meta_from_actions([], intent="DEBUG")
