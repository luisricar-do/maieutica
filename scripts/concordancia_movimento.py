#!/usr/bin/env python3
"""
Concordância entre o movimento que o artefato deriva e a anotação do banco — sem juiz.

O regressor de H1 é a ``estagnacao_acumulada`` anotada à mão no banco; a política escala com o
contador que o serviço deriva do histórico. São duas variáveis, e o ciclo 1 mostrou o que
acontece quando divergem: o coeficiente mede uma variável que a política nunca consumiu. Este
script mede a distância entre as duas antes de se gastar a corrida, e a faixa que interessa é a
do escalonamento (``>= 4``), porque é lá que a política age.

Mede as duas versões do artefato na mesma passagem:

* **regra** — o classificador determinístico de ``agents.movement``, sozinho;
* **modelo** — o nó ``agents.classifier``, que substitui o degrau do texto pelo estimador.

Corre o analista de verdade para obter o diagnóstico, porque é com ele que o nó decide se a
hipótese do estudante aponta para o defeito — medir sem ele mediria outra coisa. Diagnósticos e
estimativas são memorizados por conteúdo: os prefixos de um item partilham turnos, e o mesmo
turno não se paga duas vezes.

Uso:
    .venv/bin/python -m scripts.concordancia_movimento
    .venv/bin/python -m scripts.concordancia_movimento --itens tese_07_soma_multiplos --saida x.json
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import agents.classifier as classifier  # noqa: E402
from agents.analyst import run_analyst  # noqa: E402
from agents.movement import classify_movement, stagnation_streak  # noqa: E402
from avaliacao.config import BANCO_DIR  # noqa: E402
from avaliacao.itens import Prefixo, carregar_banco, expandir_prefixos  # noqa: E402

#: Limiar de escalonamento da política (``agents/strategist.py``). Não se mexe.
LIMIAR = 4


def carregar_local_settings() -> None:
    """Preenche as variáveis em falta a partir de ``local.settings.json``, como o host faz.

    Só preenche o que ainda não existe no ambiente: o que já estiver exportado manda. Sem isto
    o script exigiria repetir à mão a configuração que o serviço já tem.
    """
    caminho = RAIZ / "local.settings.json"
    if not caminho.is_file():
        return
    try:
        valores = json.loads(caminho.read_text(encoding="utf-8")).get("Values", {})
    except (OSError, ValueError):
        return
    for chave, valor in valores.items():
        if isinstance(valor, str) and chave not in os.environ:
            os.environ[chave] = valor


def faixa(valor: int) -> str:
    if valor <= 0:
        return "0"
    if valor < LIMIAR:
        return f"1-{LIMIAR - 1}"
    return f">={LIMIAR}"


def _chave(*partes: Any) -> str:
    bruto = json.dumps(partes, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


class Memoria:
    """Memoriza diagnóstico e estimativa por conteúdo, com uma trava por chave.

    Sem a trava, os prefixos do mesmo item — que correm em paralelo e partilham turnos —
    disparam a mesma chamada várias vezes antes de a primeira voltar.
    """

    def __init__(self) -> None:
        self._valores: dict[str, Any] = {}
        self._travas: dict[str, asyncio.Lock] = {}
        self.chamadas = 0

    async def obter(self, chave: str, produzir):
        if chave in self._valores:
            return self._valores[chave]
        trava = self._travas.setdefault(chave, asyncio.Lock())
        async with trava:
            if chave not in self._valores:
                self.chamadas += 1
                self._valores[chave] = await produzir()
        return self._valores[chave]


async def diagnosticar(prefixo: Prefixo, memoria: Memoria) -> dict[str, Any]:
    chave = _chave("diag", prefixo.code, prefixo.errors, prefixo.compiler_error_lines)

    async def _produzir():
        return await run_analyst(
            prefixo.code,
            list(prefixo.errors),
            compiler_error_lines=list(prefixo.compiler_error_lines),
        )

    return await memoria.obter(chave, _produzir)


def instalar_memoria_do_estimador(memoria: Memoria) -> None:
    """Envolve ``_estimar_turno`` num cache: a estimativa depende só do turno e do seu passado."""
    original = classifier._estimar_turno

    async def _memorizado(*, dialogo, code, errors, problem_statement, defeito):
        chave = _chave(
            "mov",
            [(t.get("role"), t.get("content")) for t in dialogo],
            code,
            errors,
            problem_statement,
            defeito,
        )

        async def _produzir():
            return await original(
                dialogo=dialogo,
                code=code,
                errors=errors,
                problem_statement=problem_statement,
                defeito=defeito,
            )

        return await memoria.obter(chave, _produzir)

    classifier._estimar_turno = _memorizado


def pela_regra(prefixo: Prefixo) -> tuple[str, int]:
    """O que o artefato deriva hoje, sem o nó: a regra determinística sozinha."""
    movimento = classify_movement(
        code=prefixo.code,
        history=prefixo.history,
        errors=list(prefixo.errors),
        previous_code=prefixo.previous_code,
        previous_errors=list(prefixo.previous_errors or []),
    )
    streak = stagnation_streak(prefixo.history, current_movement=movimento["movement"])
    return movimento["movement"], streak["streak"]


async def medir_prefixo(
    prefixo: Prefixo, diagnosticos: Memoria, estimativas: Memoria, limite: asyncio.Semaphore
) -> dict[str, Any]:
    mov_regra, streak_regra = pela_regra(prefixo)
    async with limite:
        diagnosis = await diagnosticar(prefixo, diagnosticos)
        estado = {
            "history": prefixo.history,
            "code": prefixo.code,
            "errors": list(prefixo.errors),
            "previous_code": prefixo.previous_code,
            "previous_errors": list(prefixo.previous_errors or []),
            "problem_statement": prefixo.problem_statement,
            "diagnosis": diagnosis,
        }
        saida = await classifier.run_classifier(estado)
    return {
        "prefixo": prefixo.id,
        "item": prefixo.item_id,
        "k": prefixo.k,
        "tipo": prefixo.tipo,
        "banco_movimento": prefixo.movimento_anterior,
        "banco_acumulada": prefixo.estagnacao_acumulada,
        "regra_movimento": mov_regra,
        "regra_acumulada": streak_regra,
        "modelo_movimento": saida.get("student_movement", mov_regra),
        "modelo_acumulada": saida.get("stagnation_streak", streak_regra),
        "modelo_fonte": saida.get("movement_source", "texto"),
    }


def _linha(rotulo: str, valores: list[int], acordos: int, total: int) -> str:
    contagem = Counter(faixa(v) for v in valores)
    return (
        f"{rotulo:<28}"
        f"{contagem['0']:>6}"
        f"{contagem[f'1-{LIMIAR - 1}']:>7}"
        f"{contagem['>=' + str(LIMIAR)]:>7}"
        f"{acordos:>10}/{total} ({100.0 * acordos / total:.1f}%)"
    )


def relatar(linhas: list[dict[str, Any]]) -> str:
    total = len(linhas)
    banco = [int(x["banco_acumulada"]) for x in linhas]
    regra = [int(x["regra_acumulada"]) for x in linhas]
    modelo = [int(x["modelo_acumulada"]) for x in linhas]

    def acordo(a: list[int], b: list[int]) -> int:
        return sum(1 for x, y in zip(a, b) if x == y)

    def acordo_faixa(a: list[int], b: list[int]) -> int:
        return sum(1 for x, y in zip(a, b) if faixa(x) == faixa(y))

    out = [
        "",
        f"{'':<28}{'0':>6}{f'1-{LIMIAR - 1}':>7}{'>=' + str(LIMIAR):>7}"
        f"{'concordância exata':>22}",
        "-" * 76,
        _linha("banco (regressor de H1)", banco, total, total),
        _linha("artefato: regra", regra, acordo(banco, regra), total),
        _linha("artefato: regra + modelo", modelo, acordo(banco, modelo), total),
        "",
        f"concordância por faixa   regra: {acordo_faixa(banco, regra)}/{total} "
        f"({100.0 * acordo_faixa(banco, regra) / total:.1f}%)   "
        f"modelo: {acordo_faixa(banco, modelo)}/{total} "
        f"({100.0 * acordo_faixa(banco, modelo) / total:.1f}%)",
    ]

    # Só nos prefixos ouro: no de pressão a última fala é a frase injetada, que o artefato lê
    # como pedido explícito e o banco nem anota. Comparar lá seria comparar turnos diferentes.
    ouro = [x for x in linhas if x["tipo"] == "ouro"]
    mov_regra = sum(1 for x in ouro if x["banco_movimento"] == x["regra_movimento"])
    mov_modelo = sum(1 for x in ouro if x["banco_movimento"] == x["modelo_movimento"])
    out.append(
        f"movimento do último turno (só ouro, n={len(ouro)})  "
        f"regra: {mov_regra}/{len(ouro)} ({100.0 * mov_regra / len(ouro):.1f}%)   "
        f"modelo: {mov_modelo}/{len(ouro)} ({100.0 * mov_modelo / len(ouro):.1f}%)"
    )
    fontes = Counter(x["modelo_fonte"] for x in linhas)
    out.append("origem do rótulo do último turno: " + ", ".join(
        f"{k}={v}" for k, v in sorted(fontes.items())
    ))

    novos = [x for x in linhas if x["item"].startswith("tese_")]
    if novos and len(novos) < total:
        antigos = [x for x in linhas if not x["item"].startswith("tese_")]
        for rotulo, grupo in (("itens do ciclo 1", antigos), ("itens novos", novos)):
            b = [int(x["banco_acumulada"]) for x in grupo]
            r = [int(x["regra_acumulada"]) for x in grupo]
            m = [int(x["modelo_acumulada"]) for x in grupo]
            out.append(
                f"  {rotulo:<18} n={len(grupo):<4} "
                f">={LIMIAR}: banco {sum(1 for v in b if v >= LIMIAR)}, "
                f"regra {sum(1 for v in r if v >= LIMIAR)}, "
                f"modelo {sum(1 for v in m if v >= LIMIAR)}   "
                f"exata: regra {acordo(b, r)}/{len(grupo)}, modelo {acordo(b, m)}/{len(grupo)}"
            )
    return "\n".join(out)


async def principal(args: argparse.Namespace) -> int:
    carregar_local_settings()
    itens = carregar_banco(BANCO_DIR)
    if args.itens:
        alvo = {i.strip() for i in args.itens.split(",") if i.strip()}
        itens = [it for it in itens if it.get("id") in alvo]
    prefixos = [p for item in itens for p in expandir_prefixos(item)]
    print(f"{len(itens)} itens, {len(prefixos)} prefixos; a medir …", flush=True)

    diagnosticos, estimativas = Memoria(), Memoria()
    instalar_memoria_do_estimador(estimativas)
    limite = asyncio.Semaphore(args.paralelismo)
    inicio = time.monotonic()
    linhas = await asyncio.gather(
        *(medir_prefixo(p, diagnosticos, estimativas, limite) for p in prefixos)
    )
    decorrido = time.monotonic() - inicio

    print(relatar(list(linhas)))
    print(
        f"\n{diagnosticos.chamadas} chamadas ao analista, "
        f"{estimativas.chamadas} ao estimador, em {decorrido:.0f}s"
    )
    if args.saida:
        destino = Path(args.saida)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(
            json.dumps(
                {
                    "modelo": os.getenv("LITELLM_MODEL", ""),
                    "limiar": LIMIAR,
                    "prefixos": list(linhas),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"detalhe por prefixo em {destino}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--itens", default="", help="ids separados por vírgula (padrão: todos)")
    parser.add_argument("--paralelismo", type=int, default=8)
    parser.add_argument("--saida", default="", help="JSON com o detalhe por prefixo")
    raise SystemExit(asyncio.run(principal(parser.parse_args())))
