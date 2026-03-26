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
        instance.ainvoke = AsyncMock(return_value=AIMessage(content=json.dumps(payload)))
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
        instance.ainvoke = AsyncMock(return_value=AIMessage(content=json.dumps(payload)))
        result = await run_analyst("inteiro x\nescreva((1+2", ["erro de sintaxe"])
    assert result["errorType"] == "syntax"


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
        instance.ainvoke = AsyncMock(return_value=AIMessage(content=json.dumps(payload)))
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
