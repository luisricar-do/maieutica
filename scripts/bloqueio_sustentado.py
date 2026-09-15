#!/usr/bin/env python3
"""
Um item mostra bloqueio sustentado sob a regra de conteúdo? — portão por item, antes de contar.

O ciclo 1 do corpus falhou porque a verificação veio depois: vinte itens foram escritos com a
intenção de conter bloqueio e nenhum continha, e isso só apareceu quando o banco inteiro já
estava pronto. "Não edita o código" e "está encravado" são coisas diferentes, e ao escrever um
estudante a conversar com um tutor socrático o que sai naturalmente é um estudante que responde
bem. Este script fecha o ciclo: corre-se **item a item, à medida que se escreve**, e o item que
não passa não conta.

O que mede é só o que a anotação do próprio item implica — não julga as falas, não chama modelo
nenhum. A regra é a da dissertação: soma em ESTAGNACAO e REGRESSAO, zera em PROGRESSO, e
PEDIDO_EXPLICITO transporta.

Uso:
    .venv/bin/python -m scripts.bloqueio_sustentado                     # o banco todo
    .venv/bin/python -m scripts.bloqueio_sustentado avaliacao/banco/x.json
    .venv/bin/python -m scripts.bloqueio_sustentado --profundidade 6    # exigência do poder
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from avaliacao.config import BANCO_DIR  # noqa: E402

BLOQUEIO = ("ESTAGNACAO", "REGRESSAO")

#: Limiar de escalonamento da política. Um item só alimenta a metade do escalonamento de H1 se
#: algum prefixo seu chegar aqui.
LIMIAR = 4


def perfil(item: dict) -> list[int]:
    """Estagnação acumulada após cada turno do estudante, na ordem do diálogo."""
    acumulada, serie = 0, []
    for turno in item.get("dialogo", []):
        if turno.get("papel") != "estudante":
            continue
        movimento = turno.get("movimento", "NENHUM")
        if movimento in BLOQUEIO:
            acumulada += 1
        elif movimento == "PROGRESSO":
            acumulada = 0
        serie.append(acumulada)
    return serie


def avaliar(item: dict, exigencia: int) -> dict:
    serie = perfil(item)
    profundidade = max(serie, default=0)
    return {
        "id": item.get("id", "<sem id>"),
        "serie": serie,
        "profundidade": profundidade,
        "na_faixa": sum(1 for v in serie if v >= LIMIAR),
        "passa": profundidade >= exigencia,
    }


def principal(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ficheiros", nargs="*", help="itens a verificar (padrão: o banco todo)")
    parser.add_argument(
        "--profundidade",
        type=int,
        default=LIMIAR,
        help=f"acumulado máximo exigido para o item contar (padrão {LIMIAR}; "
        "o dimensionamento de 80%% de poder pede 6)",
    )
    args = parser.parse_args(argv)

    caminhos = [Path(f) for f in args.ficheiros] or sorted(BANCO_DIR.glob("*.json"))
    linhas = [avaliar(json.loads(c.read_text(encoding="utf-8")), args.profundidade) for c in caminhos]

    print(f"exigência: acumulado máximo >= {args.profundidade}\n")
    print(f"{'item':<34}{'prof':>5}{'na faixa':>10}  {'':<6}série")
    for r in sorted(linhas, key=lambda r: (-r["profundidade"], r["id"])):
        marca = "passa " if r["passa"] else "  --  "
        print(f"{r['id'][:33]:<34}{r['profundidade']:>5}{r['na_faixa']:>10}  {marca}{r['serie']}")

    passam = [r for r in linhas if r["passa"]]
    print(
        f"\n{len(passam)} de {len(linhas)} itens mostram bloqueio sustentado; "
        f"{sum(r['na_faixa'] for r in linhas)} prefixos na faixa >= {LIMIAR}."
    )
    return 0 if passam or not args.ficheiros else 1


if __name__ == "__main__":
    raise SystemExit(principal(sys.argv[1:]))
