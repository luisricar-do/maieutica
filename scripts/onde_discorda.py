#!/usr/bin/env python3
"""
Onde vive a discordância entre a regra textual e o banco — e qual é o tecto de a corrigir.

Não propõe correção nenhuma. Responde a duas perguntas, para que a decisão de mexer (ou não) na
regra textual se tome sobre o tamanho do que está em jogo, e não sobre a impressão de um exemplo:

1. **Por degrau.** ``_classify_by_text`` é uma escada de sete degraus. Para cada turno que o texto
   decide, qual degrau disparou, o que o banco anotou, e quantos acertam.
2. **O tecto.** Substituindo o veredito de um degrau pelo do banco (oráculo), até onde sobe a
   concordância do acumulado? Com o oráculo em *todos* os degraus tem-se o limite superior de
   qualquer classificador textual — nenhuma regra, por melhor que seja, passa dali.

Uso:
    python3 -m scripts.onde_discorda
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import agents.movement as mv  # noqa: E402
from avaliacao.config import BANCO_DIR  # noqa: E402
from avaliacao.itens import carregar_banco, expandir_prefixos  # noqa: E402

LIMIAR = 4


def faixa(v: int) -> str:
    if v <= 0:
        return "0"
    return f"1-{LIMIAR - 1}" if v < LIMIAR else f">={LIMIAR}"


def degrau(user_turns: list[str], code: str) -> tuple[str, str]:
    """Qual degrau de _classify_by_text decide, e com que rótulo. Espelha a escada do módulo."""
    last = user_turns[-1]
    n = mv._normalize(last)
    if not n:
        return "vazio", "ESTAGNACAO"
    if any(p.search(n) for p in mv._STALL_PATTERNS):
        return "stall", "ESTAGNACAO"
    if mv._repete(n, user_turns[:-1]):
        return "repeticao", "ESTAGNACAO"
    if len(n) < mv._MIN_SUBSTANTIVE_CHARS:
        return "curto", "ESTAGNACAO"
    if any(p.search(n) for p in mv._HYPOTHESIS_PATTERNS):
        return "hipotese", "PROGRESSO"
    if mv._ancorado_no_codigo(n, code):
        return "ancora", "PROGRESSO"
    return "fora_do_foco", "ESTAGNACAO"


def movimentos_do_banco(item: dict) -> list[str]:
    return [t.get("movimento", "NENHUM") for t in item.get("dialogo", []) if t.get("papel") == "estudante"]


def main() -> int:
    itens = carregar_banco(BANCO_DIR)
    alvos_turno = {it["id"]: movimentos_do_banco(it) for it in itens}

    # ---- 1. por degrau, ao nível do turno ----
    # Os prefixos do mesmo item partilham turnos: o turno 0 aparece em todos eles. Contar por
    # prefixo multiplicaria cada turno pelo numero de prefixos que o contem e enviesaria a
    # contagem para os turnos iniciais. A unidade e o par (item, turno).
    tabela: dict[str, Counter] = defaultdict(Counter)
    vistos_unicos: dict[tuple[str, int], tuple[str, str]] = {}
    for item in itens:
        alvo = movimentos_do_banco(item)
        for p in expandir_prefixos(item):
            if p.tipo != "ouro":
                continue

            def _sonda(user_turns: list[str], code: str, _it=item["id"]) -> str:
                d, rot = degrau(user_turns, code)
                vistos_unicos.setdefault((_it, len(user_turns) - 1), (d, rot))
                return rot

            mv.stagnation_streak(p.history, current_movement="NENHUM", classificador_textual=_sonda)
    for (item_id, idx), (d, rot) in vistos_unicos.items():
        alvo = alvos_turno[item_id]
        if idx >= len(alvo):
            continue
        tabela[d][(alvo[idx], rot)] += 1

    print("\n=== 1. Turnos unicos (item, turno) que o texto decide, por degrau ===\n")
    print(f"{'degrau':<16}{'n':>7}{'acerta':>9}{'%':>7}   principal discordancia")
    print("-" * 78)
    ordem = ["vazio", "stall", "repeticao", "curto", "hipotese", "ancora", "fora_do_foco"]
    tot_n = tot_ok = 0
    for d in ordem:
        c = tabela.get(d)
        if not c:
            continue
        n = sum(c.values())
        ok = sum(v for (banco, rot), v in c.items() if banco == rot)
        erros = Counter({f"{b}->{r}": v for (b, r), v in c.items() if b != r})
        pior = ", ".join(f"{k} {v}" for k, v in erros.most_common(2)) or "—"
        tot_n, tot_ok = tot_n + n, tot_ok + ok
        print(f"{d:<16}{n:>7}{ok:>9}{100.0 * ok / n:>6.1f}%   {pior}")
    print("-" * 78)
    print(f"{'total':<16}{tot_n:>7}{tot_ok:>9}{100.0 * tot_ok / tot_n:>6.1f}%")

    # ---- 2. tecto: oraculo por degrau, ao nivel do prefixo ----
    prefixos = [p for item in itens for p in expandir_prefixos(item)]
    alvos = {item["id"]: movimentos_do_banco(item) for item in itens}
    banco = [int(p.estagnacao_acumulada) for p in prefixos]

    def acumulado(oraculo: set[str] | None) -> list[int]:
        out = []
        for p in prefixos:
            alvo = alvos[p.item_id]

            def _sonda(user_turns: list[str], code: str, _a=alvo) -> str:
                d, rot = degrau(user_turns, code)
                idx = len(user_turns) - 1
                if oraculo is not None and d in oraculo and idx < len(_a):
                    real = _a[idx]
                    if real in ("PROGRESSO", "ESTAGNACAO", "REGRESSAO"):
                        return real
                return rot

            mov = mv.classify_movement(
                code=p.code, history=p.history, errors=list(p.errors),
                previous_code=p.previous_code, previous_errors=list(p.previous_errors or []),
            )
            out.append(mv.stagnation_streak(
                p.history, current_movement=mov["movement"], classificador_textual=_sonda
            )["streak"])
        return out

    total = len(prefixos)
    ex = lambda a: sum(1 for x, y in zip(banco, a) if x == y)  # noqa: E731
    fx = lambda a: sum(1 for x, y in zip(banco, a) if faixa(x) == faixa(y))  # noqa: E731

    print("\n\n=== 2. Tecto: oraculo em cada degrau (acumulado, n=480) ===\n")
    print(f"{'oraculo em':<26}{'0':>6}{'1-3':>6}{'>=4':>6}{'exata':>16}{'por faixa':>17}")
    print("-" * 78)
    c = Counter(faixa(v) for v in banco)
    print(f"{'banco':<26}{c['0']:>6}{c['1-3']:>6}{c['>=4']:>6}{'—':>16}{'—':>17}")
    cenarios = [
        ("nenhum (regra actual)", None),
        ("so ancora", {"ancora"}),
        ("so hipotese", {"hipotese"}),
        ("hipotese + ancora", {"hipotese", "ancora"}),
        ("todos (limite superior)", set(ordem)),
    ]
    for rotulo, orac in cenarios:
        a = acumulado(orac)
        c = Counter(faixa(v) for v in a)
        print(
            f"{rotulo:<26}{c['0']:>6}{c['1-3']:>6}{c['>=4']:>6}"
            f"{ex(a):>9}/{total} ({100.0 * ex(a) / total:4.1f}%)"
            f"{fx(a):>9}/{total} ({100.0 * fx(a) / total:4.1f}%)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
