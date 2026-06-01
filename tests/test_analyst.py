import json
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage

from agents.analyst import run_analyst


@pytest.mark.asyncio
async def test_infinite_loop_diagnosis() -> None:
    payload = {
        "errorType": "infinite_loop",
        "errorLine": 5,
        "affectedVariable": "i",
        "errorDescription": "Laço sem incremento da variável de controle.",
        "hintAngle": "O que deveria mudar a cada volta do laço?",
        "severity": "high",
    }
    with patch("agents.llm.ChatOpenAI") as mock_cls:
        instance = mock_cls.return_value
        instance.ainvoke = AsyncMock(
            return_value=AIMessage(content=json.dumps(payload))
        )
        result = await run_analyst(
            "programa teste\nenquanto (i < 10) {\n  escreva(i)\n}",
            ["possível loop infinito"],
        )
    assert result["errorType"] == "infinite_loop"


@pytest.mark.asyncio
async def test_syntax_error_diagnosis() -> None:
    payload = {
        "errorType": "syntax",
        "errorLine": 2,
        "affectedVariable": None,
        "errorDescription": "Parêntese não fechado.",
        "hintAngle": "Quantos parênteses você abriu e fechou?",
        "severity": "medium",
    }
    with patch("agents.llm.ChatOpenAI") as mock_cls:
        instance = mock_cls.return_value
        instance.ainvoke = AsyncMock(
            return_value=AIMessage(content=json.dumps(payload))
        )
        result = await run_analyst("inteiro x\nescreva((1+2", ["erro de sintaxe"])
    assert result["errorType"] == "syntax"


@pytest.mark.asyncio
async def test_syntax_diagnosis_includes_literal_compiler_excerpt() -> None:
    payload = {
        "errorType": "syntax",
        "errorLine": 2,
        "affectedVariable": None,
        "errorDescription": "Parêntese não fechado.",
        "hintAngle": "Compare a mensagem com a estrutura da linha.",
        "severity": "medium",
    }
    compiler_msg = "Linha 2, coluna 12: SYNTAX_BRACKET esperava ')'"
    with patch("agents.llm.ChatOpenAI") as mock_cls:
        instance = mock_cls.return_value
        instance.ainvoke = AsyncMock(
            return_value=AIMessage(content=json.dumps(payload))
        )
        result = await run_analyst("inteiro x\nescreva((1+2", [compiler_msg])
    assert result["errorType"] == "syntax"
    assert 'Trecho literal do compilador: "Linha 2, coluna 12: SYNTAX_BRACKET esperava' in result[
        "errorDescription"
    ]


@pytest.mark.asyncio
async def test_type_mismatch_diagnosis_is_preserved() -> None:
    payload = {
        "errorType": "type_mismatch",
        "errorLine": 4,
        "affectedVariable": "x",
        "errorDescription": "A variável x é inteira, mas recebe uma cadeia.",
        "hintAngle": "Que tipo foi declarado para x e que tipo de valor aparece na atribuição?",
        "severity": "medium",
    }
    with patch("agents.llm.ChatOpenAI") as mock_cls:
        instance = mock_cls.return_value
        instance.ainvoke = AsyncMock(
            return_value=AIMessage(content=json.dumps(payload))
        )
        result = await run_analyst(
            'inteiro x\nx = "hello"',
            ["Tipos incompatíveis! Não é possível atribuir cadeia a inteiro"],
            compiler_error_lines=[2],
        )
    assert result["errorType"] == "type_mismatch"
    assert result["affectedVariable"] == "x"


@pytest.mark.asyncio
async def test_analyst_includes_numbered_code_and_editor_context() -> None:
    payload = {
        "errorType": "syntax",
        "errorLine": None,
        "affectedVariable": None,
        "errorDescription": "",
        "hintAngle": "",
        "severity": "low",
    }
    captured: list = []

    async def capture_ainvoke(messages):
        captured.append(messages)
        return AIMessage(content=json.dumps(payload))

    with patch("agents.llm.ChatOpenAI") as mock_cls:
        instance = mock_cls.return_value
        instance.ainvoke = AsyncMock(side_effect=capture_ainvoke)
        result = await run_analyst(
            'programa teste\nescreva("oi")',
            ["erro de sintaxe na linha 2"],
            compiler_error_lines=[2],
            cursor_line=2,
            cursor_column=8,
            ast_summary="chamada escreva",
            data_flow_context="sem fluxo",
        )

    human_text = captured[0][1].content
    assert "1 | programa teste" in human_text
    assert "2 | escreva" in human_text
    assert "Compiler error lines:\n2" in human_text
    assert "line 2 column 8" in human_text
    assert result["errorType"] == "syntax"
    assert result["errorLine"] == 2
    assert result["errorDescription"]
    assert result["hintAngle"]


@pytest.mark.asyncio
async def test_no_error_diagnosis() -> None:
    payload = {
        "errorType": "none",
        "errorLine": None,
        "affectedVariable": None,
        "errorDescription": "Sem erros reportados.",
        "hintAngle": "",
        "severity": "low",
    }
    with patch("agents.llm.ChatOpenAI") as mock_cls:
        instance = mock_cls.return_value
        instance.ainvoke = AsyncMock(
            return_value=AIMessage(content=json.dumps(payload))
        )
        result = await run_analyst("escreva(1)", [])
    assert result["errorType"] == "none"


@pytest.mark.asyncio
async def test_malformed_llm_response_returns_default() -> None:
    with patch("agents.llm.ChatOpenAI") as mock_cls:
        instance = mock_cls.return_value
        instance.ainvoke = AsyncMock(
            return_value=AIMessage(content="isto não é um json válido {{{")
        )
        result = await run_analyst("qualquer", [])
    assert result["errorType"] == "none"
    assert result["errorLine"] is None
    assert result["affectedVariable"] is None
    assert result["errorDescription"] == ""
    assert result["hintAngle"] == ""
    assert result["severity"] == "low"


@pytest.mark.asyncio
async def test_malformed_llm_response_with_errors_returns_fallback() -> None:
    with patch("agents.llm.ChatOpenAI") as mock_cls:
        instance = mock_cls.return_value
        instance.ainvoke = AsyncMock(
            return_value=AIMessage(content="isto não é um json válido {{{")
        )
        result = await run_analyst(
            'programa teste\nescreva("oi"',
            ["erro de sintaxe"],
            compiler_error_lines=[2],
        )
    assert result["errorType"] == "syntax"
    assert result["errorLine"] == 2
    assert result["errorDescription"]
    assert result["hintAngle"]
    assert result["severity"] == "medium"


@pytest.mark.asyncio
async def test_fallback_classifies_type_mismatch_errors() -> None:
    with patch("agents.llm.ChatOpenAI") as mock_cls:
        instance = mock_cls.return_value
        instance.ainvoke = AsyncMock(
            return_value=AIMessage(content="isto não é um json válido {{{")
        )
        result = await run_analyst(
            'inteiro x\nx = "hello"',
            ["Tipos incompatíveis! Não é possível atribuir cadeia a inteiro"],
            compiler_error_lines=[2],
        )
    assert result["errorType"] == "type_mismatch"
    assert result["errorLine"] == 2
    assert "tipo" in result["hintAngle"].lower()
    assert "fech" not in result["hintAngle"].lower()


@pytest.mark.asyncio
async def test_fallback_classifies_technical_clone_error_as_undeclared_identifier() -> None:
    with patch("agents.llm.ChatOpenAI") as mock_cls:
        instance = mock_cls.return_value
        instance.ainvoke = AsyncMock(
            return_value=AIMessage(content="isto não é um json válido {{{")
        )
        result = await run_analyst(
            "resultado = contador + 5",
            ["Cannot read properties of undefined (reading 'clone')"],
            compiler_error_lines=[1],
        )
    assert result["errorType"] == "undeclared_identifier"
    assert result["errorLine"] == 1
    assert "declar" in result["hintAngle"].lower()
