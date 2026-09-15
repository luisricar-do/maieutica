#!/usr/bin/env python3
"""
Calibração interna do limiar de H2 sobre os turnos de referência humanos.

O pré-registo declara a calibração para **as duas** taxas — contingência e revelação: "as duas
taxas são calculadas também sobre os turnos de referência humanos do banco, anotados na tradução
antes de rodar o artefato, e reportadas lado a lado". A da contingência está feita; esta é a
outra.

Unidade: o turno de tutor de referência cujo movimento anterior é ``PEDIDO_EXPLICITO``. Veredito
pelo detector objetivo (``avaliacao/detector.py``), o mesmo que decide a revelação em código na
corrida — logo não depende do juiz nem de κ.

Só referência de autoria ``autor``: um turno redigido com assistência de modelo não é padrão
humano. Reporta quantos foram excluídos por isso.

Uso:
    python3 -m scripts.calibracao_h2
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from agents.movement import is_explicit_request  # noqa: E402
from avaliacao.config import BANCO_DIR  # noqa: E402
from avaliacao.detector import detectar  # noqa: E402
from avaliacao.itens import carregar_banco, turnos_de_referencia  # noqa: E402


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / d
    meia = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (max(0.0, centro - meia), min(1.0, centro + meia))


def ultimo_turno_estudante(history: list[dict]) -> str:
    for item in reversed(history or []):
        if isinstance(item, dict) and item.get("role") == "user":
            return str(item.get("content", ""))
    return ""


def main() -> int:
    itens = carregar_banco(BANCO_DIR)
    anotado: list[dict] = []
    por_regra: list[dict] = []
    excluidos = Counter()

    for item in itens:
        padroes = item.get("fix_patterns") or item.get("fix_pattern") or []
        if isinstance(padroes, str):
            padroes = [padroes]
        for ref in turnos_de_referencia(item):
            autoria = ref.get("referencia_autoria", "")
            pedido_anotado = ref.get("movimento_anterior") == "PEDIDO_EXPLICITO"
            pedido_regra = is_explicit_request(ultimo_turno_estudante(ref.get("history") or []))
            if not (pedido_anotado or pedido_regra):
                continue
            if autoria != "autor":
                excluidos[autoria] += 1
                continue
            d = detectar(ref["texto"], padroes, codigo_vigente=ref.get("code", ""))
            registo = {"id": ref["id"], "revela": d.revelacao_codigo, "autoria": autoria}
            if pedido_anotado:
                anotado.append(registo)
            if pedido_regra:
                por_regra.append(registo)

    print()
    print("Calibracao interna do limiar de H2 — turnos de referencia humanos")
    print("Veredito: detector objetivo de revelacao em codigo (nao depende do juiz)\n")
    print(f"{'populacao':<38}{'revela/n':>12}{'taxa':>9}   IC 95% Wilson")
    print("-" * 82)
    for rotulo, grupo in (
        ("pedido explicito ANOTADO no banco", anotado),
        ("pedido explicito pela REGRA do artefato", por_regra),
    ):
        n = len(grupo)
        k = sum(1 for g in grupo if g["revela"])
        if n == 0:
            print(f"{rotulo:<38}{'0/0':>12}{'—':>9}   nao calculavel: nenhum turno nesta populacao")
            continue
        lo, hi = wilson(k, n)
        print(f"{rotulo:<38}{f'{k}/{n}':>12}{k / n:>9.4f}   [{lo:.4f}; {hi:.4f}]")
    print("-" * 82)
    if excluidos:
        print("excluidos por autoria nao-humana: " + ", ".join(
            f"{a or '<vazio>'}={v}" for a, v in sorted(excluidos.items())
        ))
    else:
        print("nenhum turno excluido por autoria")

    if anotado:
        reveladores = [g["id"] for g in anotado if g["revela"]]
        if reveladores:
            print("\nturnos de referencia que revelam:")
            for i in reveladores:
                print(f"  {i}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
