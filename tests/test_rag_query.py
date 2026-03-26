"""Testes do módulo ``agents.rag.query`` (sem Azure real)."""

from unittest.mock import MagicMock

from agents.analyst import Diagnosis
from agents.rag.query import build_rag_query, retrieve_doc_chunks


def test_build_rag_query_joins_errors_diagnosis_and_last_user_message() -> None:
    diagnosis: Diagnosis = {
        "errorType": "syntax",
        "errorLine": 1,
        "affectedVariable": None,
        "errorDescription": "Falta ponto e vírgula",
        "hintAngle": "Onde termina a instrução?",
        "severity": "low",
    }
    history = [
        {"role": "assistant", "content": "Oi"},
        {"role": "user", "content": "Não entendi o erro"},
    ]
    q = build_rag_query(diagnosis, ["erro1", "erro2"], history)
    assert "Erros: erro1; erro2" in q
    assert "Falta ponto e vírgula" in q
    assert "Onde termina a instrução?" in q
    assert "Não entendi o erro" in q


def test_build_rag_query_skips_empty_history_roles() -> None:
    diagnosis: Diagnosis = {
        "errorType": "none",
        "errorLine": None,
        "affectedVariable": None,
        "errorDescription": "d",
        "hintAngle": "h",
        "severity": "low",
    }
    q = build_rag_query(diagnosis, [], [])
    assert "d" in q and "h" in q


def test_retrieve_doc_chunks_returns_empty_for_blank_query() -> None:
    assert retrieve_doc_chunks("") == []
    assert retrieve_doc_chunks("   ") == []


def test_retrieve_doc_chunks_uses_retriever() -> None:
    fake_doc = MagicMock()
    fake_doc.page_content = "fragmento da doc"
    retriever = MagicMock()
    retriever.invoke = MagicMock(return_value=[fake_doc])

    def fake_get_retriever(_k: int):
        return retriever

    out = retrieve_doc_chunks(
        "vetor em portugol",
        k=3,
        _get_retriever=fake_get_retriever,
    )

    retriever.invoke.assert_called_once_with("vetor em portugol")
    assert out == ["fragmento da doc"]
