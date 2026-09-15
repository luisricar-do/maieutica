"""`analisar` não pode fabricar tabelas de uma corrida com um banco que não é o dela.

O defeito que isto apanha não dá erro: `analisar` lê o banco vivo, cruza-o com os vereditos
gravados e produz tabelas coerentes — e falsas. `cap4` regenerado com o banco de 45 itens diria
«Itens & 45» sobre 2 020 vereditos de 25. O manifesto grava `itens` no arranque do `rodar`, e é
contra essa lista que o comando confere o banco lido, como `congelar` confere os hashes.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from avaliacao import analise, cli, registro
from avaliacao.config import Config
from avaliacao.registro import escrever_json
from tests.test_avaliacao_banco import item_minimo


def _corrida(tmp_path, monkeypatch, manifesto: dict):
    monkeypatch.setattr(registro, "EXECUCOES_DIR", tmp_path)
    diretorio = tmp_path / "corrida"
    diretorio.mkdir()
    escrever_json(diretorio / "manifesto.json", {"id_execucao": "corrida", **manifesto})
    return diretorio


def _analise_falsa(monkeypatch):
    chamadas = []

    def falsa(diretorio, itens, *, juiz_modelo=""):
        chamadas.append([item["id"] for item in itens])
        (diretorio / "analise").mkdir(exist_ok=True)
        (diretorio / "analise" / "resumo.md").write_text("resumo", encoding="utf-8")
        return {"ok": True}

    monkeypatch.setattr(analise, "analisar", falsa)
    return chamadas


def _args():
    return SimpleNamespace(execucao="corrida", juiz_modelo="")


def _outro_item():
    return {**item_minimo(), "id": "teste_02"}


def test_recusa_banco_que_nao_e_o_da_corrida(tmp_path, monkeypatch):
    _corrida(tmp_path, monkeypatch, {"itens": ["teste_01"]})
    chamadas = _analise_falsa(monkeypatch)
    with pytest.raises(SystemExit) as erro:
        cli._cmd_analisar(_args(), Config(), [item_minimo(), _outro_item()])
    assert "teste_02" in str(erro.value) and "a mais" in str(erro.value)
    assert not chamadas, "a análise não pode correr sobre um banco divergente"


def test_recusa_tambem_quando_falta_item_da_corrida(tmp_path, monkeypatch):
    _corrida(tmp_path, monkeypatch, {"itens": ["teste_01", "teste_02"]})
    chamadas = _analise_falsa(monkeypatch)
    with pytest.raises(SystemExit) as erro:
        cli._cmd_analisar(_args(), Config(), [item_minimo()])
    assert "em falta: teste_02" in str(erro.value)
    assert not chamadas


def test_segue_quando_o_banco_e_o_da_corrida(tmp_path, monkeypatch):
    # A ordem não conta: o manifesto grava a ordem de leitura, o banco pode ser lido noutra.
    _corrida(tmp_path, monkeypatch, {"itens": ["teste_02", "teste_01"]})
    chamadas = _analise_falsa(monkeypatch)
    assert cli._cmd_analisar(_args(), Config(), [item_minimo(), _outro_item()]) == 0
    assert chamadas == [["teste_01", "teste_02"]]


def test_manifesto_sem_itens_avisa_e_segue(tmp_path, monkeypatch, capsys):
    # Corridas anteriores ao campo não têm como ser conferidas; o aviso fica no terminal.
    _corrida(tmp_path, monkeypatch, {})
    chamadas = _analise_falsa(monkeypatch)
    assert cli._cmd_analisar(_args(), Config(), [item_minimo()]) == 0
    assert chamadas and "AVISO" in capsys.readouterr().out
