"""``EVALUATION_MODE``: sem RAG em nenhuma intenção e sem ``suggest_documentation``."""

import pytest

from agents.config import evaluation_mode
from agents.graph import rag_retrieve_node
from agents.strategist import active_strategist_tools


def test_desligado_por_omissao(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVALUATION_MODE", raising=False)
    assert evaluation_mode() is False


@pytest.mark.parametrize("valor", ["1", "true", "on", "sim", "TRUE"])
def test_ligado_pelos_valores_aceites(monkeypatch: pytest.MonkeyPatch, valor: str) -> None:
    monkeypatch.setenv("EVALUATION_MODE", valor)
    assert evaluation_mode() is True


@pytest.mark.parametrize("intent", ["THEORY", "DEBUG", "CASUAL", "OUT_OF_SCOPE"])
@pytest.mark.asyncio
async def test_rag_nao_corre_em_nenhuma_intencao(
    monkeypatch: pytest.MonkeyPatch, intent: str
) -> None:
    monkeypatch.setenv("EVALUATION_MODE", "1")

    def _boom(*_args, **_kwargs):  # pragma: no cover - não deve ser chamado
        raise AssertionError("RAG não pode correr em EVALUATION_MODE")

    monkeypatch.setattr("agents.graph.retrieve_doc_chunks", _boom)
    state = {
        "intent": intent,
        "history": [{"role": "user", "content": "o que é um laço?"}],
        "code": "programa {}",
        "errors": [],
        "include_documentation": True,
        "diagnosis": {"errorType": "none"},
    }
    assert await rag_retrieve_node(state) == {"documentation_context": []}


@pytest.mark.asyncio
async def test_rag_teorico_corre_fora_do_modo_de_avaliacao(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EVALUATION_MODE", raising=False)
    monkeypatch.setattr("agents.graph.retrieve_doc_chunks", lambda _q: ["trecho"])
    state = {
        "intent": "THEORY",
        "history": [{"role": "user", "content": "o que é um laço?"}],
        "code": "programa {}",
        "errors": [],
        "include_documentation": False,
        "diagnosis": {},
    }
    assert await rag_retrieve_node(state) == {"documentation_context": ["trecho"]}


def test_ferramenta_de_documentacao_fora_do_modo_de_avaliacao(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EVALUATION_MODE", "1")
    names = {t.name for t in active_strategist_tools()}
    assert "suggest_documentation" not in names
    assert "highlight_line" in names

    monkeypatch.delenv("EVALUATION_MODE", raising=False)
    assert "suggest_documentation" in {t.name for t in active_strategist_tools()}
