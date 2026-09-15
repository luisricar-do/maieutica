"""Leitores partilhados pelos scripts de apuração do Capítulo 5.

**Só leem.** Nenhum script desta pasta escreve em ``avaliacao/`` — nem no banco, nem nos
prompts, nem em ``execucoes/``. As saídas vão para ``analise_tese/saida/``.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent
#: Execução lida pelos scripts. ``cap4`` é a formativa do ciclo 1 e fica como padrão para a
#: apuração já publicada continuar a sair igual sem argumento nenhum; a corrida somativa do
#: ciclo 2 correrá sob outro id, e é este o ponto único onde ele se troca.
EXECUCAO_ID = os.environ.get("AVALIACAO_EXECUCAO", "cap4")
EXECUCAO = RAIZ / "avaliacao" / "execucoes" / EXECUCAO_ID
VALIDACAO = EXECUCAO / "validacao_humana"
SAIDA = Path(__file__).resolve().parent / "saida"

VARIAVEIS_ORDINAIS = ("diretividade", "fidelidade")
VARIAVEIS_BOOLEANAS = ("irrelevante", "repetida", "excessivamente_direta", "prematura")
VARIAVEIS_TEXTUAIS = ("movimento_estudante", "ancorado")
VARIAVEIS = VARIAVEIS_ORDINAIS + VARIAVEIS_TEXTUAIS + VARIAVEIS_BOOLEANAS

_VERDADEIROS = frozenset({"sim", "s", "true", "verdadeiro", "1", "x"})


def ndjson(caminho: Path) -> list[dict[str, Any]]:
    with caminho.open(encoding="utf-8") as arquivo:
        return [json.loads(linha) for linha in arquivo if linha.strip()]


def carregar() -> dict[str, Any]:
    """Manifesto, turnos, juízos, mapa cego e codificação humana da execução escolhida (``AVALIACAO_EXECUCAO``, padrão ``cap4``)."""
    turnos = {t["chave"]: t for t in ndjson(EXECUCAO / "turnos.jsonl")}
    juizos = {j["chave"]: j for j in ndjson(EXECUCAO / "juizos.jsonl")}
    with (VALIDACAO / "codificacao.csv").open(encoding="utf-8", newline="") as arquivo:
        codificacao = {linha["id_cego"]: linha for linha in csv.DictReader(arquivo)}
    return {
        "manifesto": json.loads((EXECUCAO / "manifesto.json").read_text(encoding="utf-8")),
        "turnos": turnos,
        "juizos": juizos,
        "mapa": json.loads((VALIDACAO / "mapa_amostra.json").read_text(encoding="utf-8")),
        "codificacao": codificacao,
        "kappa": json.loads((VALIDACAO / "kappa.json").read_text(encoding="utf-8")),
    }


def valor_humano(linha: dict[str, str], variavel: str) -> Any:
    """Mesma leitura de ``avaliacao.validacao_humana._valor``, replicada para não importar dali."""
    bruto = str(linha.get(variavel, "") or "").strip()
    if not bruto:
        return None
    if variavel in VARIAVEIS_ORDINAIS:
        try:
            return int(bruto)
        except ValueError:
            return None
    if variavel in VARIAVEIS_BOOLEANAS + ("incorreta",):
        return bruto.casefold() in _VERDADEIROS
    if variavel == "movimento_estudante":
        return bruto.upper()
    return bruto.casefold()


def valor_juiz(juizo: dict[str, Any], variavel: str) -> Any:
    if variavel in VARIAVEIS_ORDINAIS:
        return juizo.get(variavel)
    if variavel in VARIAVEIS_BOOLEANAS:
        return bool((juizo.get("falhas") or {}).get(variavel))
    if variavel == "movimento_estudante":
        return str(juizo.get("movimento_estudante", "")).upper()
    return str(juizo.get("ancorado", "")).casefold()


def condicao_de(chave: str) -> str:
    """``item::k::prefixo|COND|execucao`` → condição; turno de referência → ``REF``."""
    return chave.split("|")[1] if "|" in chave else "REF"


def escrever(nome: str, conteudo: Any) -> Path:
    SAIDA.mkdir(parents=True, exist_ok=True)
    destino = SAIDA / nome
    destino.write_text(json.dumps(conteudo, indent=2, ensure_ascii=False), encoding="utf-8")
    return destino
