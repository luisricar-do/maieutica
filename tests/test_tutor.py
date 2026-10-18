from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk

from agents.tutor import (
    OUT_OF_SCOPE_RESPONSE,
    error_nature_text,
    run_communicator,
    run_communicator_stream,
)


def _patch_chat_client(mock_cls: MagicMock) -> MagicMock:
    instance = mock_cls.return_value
    # Comunicador não usa bind_tools
    instance.bind_tools = MagicMock(
        side_effect=AssertionError("communicator must not bind_tools")
    )
    return instance


@pytest.mark.asyncio
async def test_run_communicator_returns_model_message() -> None:
    with patch("agents.llm.ChatOpenAI") as mock_cls:
        instance = _patch_chat_client(mock_cls)
        instance.ainvoke = AsyncMock(
            return_value=AIMessage(
                content="Ótimo esforço! O que você espera que aconteça aqui?"
            )
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
        await run_communicator(
            "Destaquei linhas 2 e 4 para comparar.", [], intent="DEBUG"
        )
    msgs = captured[0]
    system_text = msgs[0].content
    assert "<strategist_plan>" in system_text
    assert "Destaquei linhas 2 e 4 para comparar." in system_text
    assert "latest student message shows frustration" in system_text
    assert "Avoid generic visual templates" in system_text
    assert "Never mention \"aberturas\"" in system_text
    assert "literal compiler excerpt" in system_text


@pytest.mark.asyncio
async def test_run_communicator_injects_documentation_hint_when_topic_suggested() -> None:
    captured: list = []

    async def capture_ainvoke(messages):
        captured.append(messages)
        return AIMessage(content="ok")

    with patch("agents.llm.ChatOpenAI") as mock_cls:
        instance = _patch_chat_client(mock_cls)
        instance.ainvoke = AsyncMock(side_effect=capture_ainvoke)
        await run_communicator(
            "Aluno não conhece a sintaxe de vetor.",
            [],
            intent="DEBUG",
            suggested_doc_topics=["vetores"],
        )
    system_text = captured[0][0].content
    assert "DOCUMENTATION AID" in system_text
    assert "vetores" in system_text


@pytest.mark.asyncio
async def test_run_communicator_omits_documentation_hint_by_default() -> None:
    captured: list = []

    async def capture_ainvoke(messages):
        captured.append(messages)
        return AIMessage(content="ok")

    with patch("agents.llm.ChatOpenAI") as mock_cls:
        instance = _patch_chat_client(mock_cls)
        instance.ainvoke = AsyncMock(side_effect=capture_ainvoke)
        await run_communicator("Plano qualquer.", [], intent="DEBUG")
    assert "DOCUMENTATION AID" not in captured[0][0].content


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
    assert "You are ADA" in system_text
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
    assert "Never provide a complete functional program" in system_text
    assert "Do not use fenced code blocks for examples" in system_text


@pytest.mark.asyncio
async def test_run_communicator_out_of_scope_returns_fixed_redirect() -> None:
    with patch("agents.llm.ChatOpenAI") as mock_cls:
        out = await run_communicator(
            "não responder biografia",
            [{"role": "user", "content": "Quem foi Einstein?"}],
            intent="OUT_OF_SCOPE",
        )
    assert out == OUT_OF_SCOPE_RESPONSE
    mock_cls.assert_not_called()


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


@pytest.mark.asyncio
async def test_run_communicator_stream_out_of_scope_yields_fixed_redirect() -> None:
    with patch("agents.llm.ChatOpenAI") as mock_cls:
        parts = [
            p
            async for p in run_communicator_stream(
                "não responder biografia",
                [{"role": "user", "content": "Quem foi Einstein?"}],
                intent="OUT_OF_SCOPE",
            )
        ]
    assert parts == [OUT_OF_SCOPE_RESPONSE]
    mock_cls.assert_not_called()


@pytest.mark.asyncio
async def test_run_communicator_recebe_o_nivel_alvo_do_estrategista() -> None:
    captured: list = []

    async def capture_ainvoke(messages):
        captured.append(messages)
        return AIMessage(content="ok")

    with patch("agents.llm.ChatOpenAI") as mock_cls:
        instance = _patch_chat_client(mock_cls)
        instance.ainvoke = AsyncMock(side_effect=capture_ainvoke)
        await run_communicator(
            "Nomeie a incompatibilidade de tipo.", [], intent="DEBUG", concreteness_level=2
        )
    system_text = captured[0][0].content
    assert "TARGET CONCRETENESS LEVEL FOR THIS TURN: 2" in system_text
    assert "level 2 `conceptual`" in system_text
    assert "do not copy their concreteness" in system_text


@pytest.mark.asyncio
async def test_run_communicator_sem_nivel_nao_injeta_alvo() -> None:
    captured: list = []

    async def capture_ainvoke(messages):
        captured.append(messages)
        return AIMessage(content="ok")

    with patch("agents.llm.ChatOpenAI") as mock_cls:
        instance = _patch_chat_client(mock_cls)
        instance.ainvoke = AsyncMock(side_effect=capture_ainvoke)
        await run_communicator("Plano.", [], intent="DEBUG")
    assert "TARGET CONCRETENESS LEVEL" not in captured[0][0].content


@pytest.mark.asyncio
async def test_run_communicator_stream_recebe_o_nivel_alvo() -> None:
    captured: list = []

    async def capture_astream(messages):
        captured.append(messages)
        yield AIMessageChunk(content="ok")

    with patch("agents.llm.ChatOpenAI") as mock_cls:
        instance = _patch_chat_client(mock_cls)
        instance.astream = capture_astream
        out = [
            d
            async for d in run_communicator_stream(
                "Plano.", [], intent="DEBUG", concreteness_level=1
            )
        ]
    assert out == ["ok"]
    assert "TARGET CONCRETENESS LEVEL FOR THIS TURN: 1" in captured[0][0].content


async def _system_do_comunicador(**kwargs) -> str:
    captured: list = []

    async def capture_ainvoke(messages):
        captured.append(messages)
        return AIMessage(content="ok")

    with patch("agents.llm.ChatOpenAI") as mock_cls:
        instance = _patch_chat_client(mock_cls)
        instance.ainvoke = AsyncMock(side_effect=capture_ainvoke)
        await run_communicator("Aponte o laço da linha 4.", [], intent="DEBUG", **kwargs)
    return captured[0][0].content


@pytest.mark.asyncio
async def test_nivel_2_pede_frase_afirmativa_e_leva_a_natureza_do_erro() -> None:
    natureza = "Error type: logic. Analyst description: a mensagem é decidida dentro do laço."
    system_text = await _system_do_comunicador(concreteness_level=2, error_nature=natureza)
    assert "one AFFIRMATIVE sentence that states what is wrong" in system_text
    assert f"<error_nature>\n{natureza}\n</error_nature>" in system_text
    # O nível vem depois do plano, no fim do prompt.
    assert system_text.index("</strategist_plan>") < system_text.index("TARGET CONCRETENESS LEVEL")


@pytest.mark.asyncio
async def test_nivel_1_nao_recebe_a_natureza_do_erro() -> None:
    system_text = await _system_do_comunicador(concreteness_level=1, error_nature="Error type: logic.")
    assert "Shape for level 1" in system_text
    assert "<error_nature>" not in system_text


@pytest.mark.asyncio
async def test_comunicador_proibe_sugerir_a_edicao_em_forma_de_pergunta() -> None:
    system_text = await _system_do_comunicador(concreteness_level=1)
    assert "Never suggest the edit itself, not even as a question" in system_text


def test_error_nature_text_vem_do_diagnostico() -> None:
    assert error_nature_text({"errorType": "none"}) == ""
    assert error_nature_text(None) == ""
    texto = error_nature_text(
        {"errorType": "logic", "errorDescription": "conta fora do se", "hintAngle": "fluxo"}
    )
    assert texto == "Error type: logic. Analyst description: conta fora do se Concept angle: fluxo"
