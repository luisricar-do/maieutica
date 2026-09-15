#!/usr/bin/env python3
"""
Portão da correção da âncora: o dígito nu não é símbolo do programa.

``_ancorado_no_codigo`` já recusa identificadores de menos de três caracteres — tokens curtos não
discriminam, aparecem em qualquer programa. A mesma regra não vale para números: ``_SIMBOLO``
aceita ``\\d+``, portanto o ``0`` de "continua devolvendo 0" casa com qualquer ``0`` do código e a
fala conta como ancorada. A correção é o princípio que a função já aplica, estendido aos números:
um número ancora a partir de dois dígitos.

Mede-se pelo mesmo critério que reprovou o nó (``scripts/concordancia_movimento.py``): entra só
se a concordância exata **e** a concordância por faixa melhorarem, sem escalar a mais. Não precisa
de modelo nenhum — as duas versões são determinísticas.

Uso:
    .venv/bin/python -m scripts.gate_ancora
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import agents.movement as movement  # noqa: E402
from avaliacao.config import BANCO_DIR  # noqa: E402
from avaliacao.itens import carregar_banco, expandir_prefixos  # noqa: E402

LIMIAR = 4
ORIGINAL = movement._SIMBOLO
CORRIGIDO = re.compile(r"[a-z_]\w{2,}|\d{2,}")


def faixa(v: int) -> str:
    if v <= 0:
        return "0"
    return f"1-{LIMIAR - 1}" if v < LIMIAR else f">={LIMIAR}"


def pela_regra(p):
    mov = movement.classify_movement(
        code=p.code,
        history=p.history,
        errors=list(p.errors),
        previous_code=p.previous_code,
        previous_errors=list(p.previous_errors or []),
    )
    streak = movement.stagnation_streak(p.history, current_movement=mov["movement"])
    return mov["movement"], streak["streak"]


def medir(prefixos, simbolo):
    movement._SIMBOLO = simbolo
    try:
        return [pela_regra(p) for p in prefixos]
    finally:
        movement._SIMBOLO = ORIGINAL


def linha(rotulo, acum, acordos, faixas, total):
    c = Counter(faixa(v) for v in acum)
    return (
        f"{rotulo:<26}{c['0']:>6}{c[f'1-{LIMIAR - 1}']:>7}{c['>=' + str(LIMIAR)]:>7}"
        f"{acordos:>8}/{total} ({100.0 * acordos / total:4.1f}%)"
        f"{faixas:>8}/{total} ({100.0 * faixas / total:4.1f}%)"
    )


def main() -> int:
    itens = carregar_banco(BANCO_DIR)
    prefixos = [p for item in itens for p in expandir_prefixos(item)]
    total = len(prefixos)
    banco = [int(p.estagnacao_acumulada) for p in prefixos]

    base = medir(prefixos, ORIGINAL)
    corr = medir(prefixos, CORRIGIDO)
    acum_base = [s for _, s in base]
    acum_corr = [s for _, s in corr]

    ex = lambda a: sum(1 for x, y in zip(banco, a) if x == y)  # noqa: E731
    fx = lambda a: sum(1 for x, y in zip(banco, a) if faixa(x) == faixa(y))  # noqa: E731

    print()
    print(f"{itens and len(itens)} itens, {total} prefixos\n")
    print(f"{'':<26}{'0':>6}{f'1-{LIMIAR - 1}':>7}{'>=' + str(LIMIAR):>7}{'exata':>17}{'por faixa':>18}")
    print("-" * 82)
    print(linha("banco (regressor H1)", banco, total, total, total))
    print(linha("regra (actual)", acum_base, ex(acum_base), fx(acum_base), total))
    print(linha("regra + correcao", acum_corr, ex(acum_corr), fx(acum_corr), total))

    ouro = [i for i, p in enumerate(prefixos) if p.tipo == "ouro"]
    mb = sum(1 for i in ouro if prefixos[i].movimento_anterior == base[i][0])
    mc = sum(1 for i in ouro if prefixos[i].movimento_anterior == corr[i][0])
    print(
        f"\nmovimento do ultimo turno (so ouro, n={len(ouro)})   "
        f"regra: {mb}/{len(ouro)} ({100.0 * mb / len(ouro):.1f}%)   "
        f"corrigida: {mc}/{len(ouro)} ({100.0 * mc / len(ouro):.1f}%)"
    )

    mudou = [i for i in range(total) if base[i] != corr[i]]
    print(f"\nprefixos que mudaram: {len(mudou)}")
    melhor = sum(1 for i in mudou if acum_corr[i] == banco[i] and acum_base[i] != banco[i])
    pior = sum(1 for i in mudou if acum_base[i] == banco[i] and acum_corr[i] != banco[i])
    print(f"  aproximaram-se do banco: {melhor}   afastaram-se: {pior}")

    # Escalonamento: quantos o artefato manda escalar contra os que o banco manda.
    esc_banco = {i for i in range(total) if banco[i] >= LIMIAR}
    esc_base = {i for i in range(total) if acum_base[i] >= LIMIAR}
    esc_corr = {i for i in range(total) if acum_corr[i] >= LIMIAR}
    print(
        f"\nescala (>= {LIMIAR}):  banco {len(esc_banco)}   "
        f"regra {len(esc_base)} (dentro do banco: {len(esc_base & esc_banco)}, "
        f"fora: {len(esc_base - esc_banco)})   "
        f"corrigida {len(esc_corr)} (dentro: {len(esc_corr & esc_banco)}, "
        f"fora: {len(esc_corr - esc_banco)})"
    )
    for i in sorted(mudou)[:15]:
        print(
            f"    {prefixos[i].id:<44} banco {banco[i]}  "
            f"regra {acum_base[i]} ({base[i][0]})  ->  {acum_corr[i]} ({corr[i][0]})"
        )
    if len(mudou) > 15:
        print(f"    ... mais {len(mudou) - 15}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
