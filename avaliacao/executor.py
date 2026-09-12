"""Execução da bancada: prefixos × condições × repetições (Subseção 4.3.2 da dissertação).

Cada prefixo é executado ``n`` vezes por condição, em ordem aleatorizada entre condições, e a
variância entre execuções é reportada. Falhas técnicas são reexecutadas até duas vezes e,
persistindo, marcadas e excluídas do denominador, com a taxa reportada.

A condição B corre só nos prefixos de pressão: a ablação mede revelação sob pedido explícito.
O resumo da corrida traz a contagem de turnos cortados no limite de tokens (``finish_reason``
``length``) por condição — em A o comunicador só traduz um plano interno, em B a mesma chamada
tem de analisar, decidir e falar, e um turno cortado seria classificado com diretividade errada.
"""

from __future__ import annotations

import random
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from avaliacao import condicoes
from avaliacao.config import Config
from avaliacao.itens import Prefixo
from avaliacao.registro import anexar, chaves_existentes

ARQUIVO_TURNOS = "turnos.jsonl"


#: Nome da função de condição em ``avaliacao.condicoes``, resolvido na hora da chamada.
_EXECUTOR_POR_CONDICAO = {"A": "executar_a", "B": "executar_b", "C": "executar_c"}


def chave(prefixo_id: str, condicao: str, execucao: int) -> str:
    return f"{prefixo_id}|{condicao}|{execucao}"


def _chamada(condicao: str):
    nome = _EXECUTOR_POR_CONDICAO.get(condicao)
    if nome is None:
        raise SystemExit(f"condição desconhecida: {condicao}")
    return getattr(condicoes, nome)


def cabe(prefixo: Prefixo, condicao: str) -> bool:
    """B só nos prefixos de pressão; as demais condições correm o banco todo."""
    return condicao not in condicoes.CONDICOES_SO_PRESSAO or prefixo.tipo == "pressao"


def montar_tarefas(
    prefixos: list[Prefixo],
    *,
    condicoes_alvo: tuple[str, ...],
    execucoes: int,
    semente: int,
) -> list[tuple[Prefixo, str, int]]:
    tarefas = [
        (prefixo, condicao, execucao)
        for prefixo in prefixos
        for condicao in condicoes_alvo
        for execucao in range(1, execucoes + 1)
        if cabe(prefixo, condicao)
    ]
    random.Random(semente).shuffle(tarefas)
    return tarefas


def executar(
    cfg: Config,
    prefixos: list[Prefixo],
    diretorio: Path,
    *,
    condicoes_alvo: tuple[str, ...] = condicoes.CONDICOES,
    execucoes: int = 3,
    reexecucoes: int = 2,
    semente: int = 20260912,
    ao_terminar: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, int]:
    """Roda o que falta e devolve o resumo da corrida. Turnos já registrados são preservados."""
    destino = diretorio / ARQUIVO_TURNOS
    feitos = chaves_existentes(destino)
    tarefas = [
        tarefa
        for tarefa in montar_tarefas(
            prefixos, condicoes_alvo=condicoes_alvo, execucoes=execucoes, semente=semente
        )
        if chave(tarefa[0].id, tarefa[1], tarefa[2]) not in feitos
    ]

    resumo: dict[str, Any] = {
        "planejados": len(tarefas),
        "ok": 0,
        "falhas_tecnicas": 0,
        "reaproveitados": len(feitos),
        "chamadas_por_condicao": {},
        "truncadas_por_condicao": {},
    }
    if not tarefas:
        return resumo

    def trabalho(tarefa: tuple[Prefixo, str, int]) -> dict[str, Any]:
        prefixo, condicao, execucao = tarefa
        registro = _com_reexecucoes(cfg, prefixo, condicao, execucao, reexecucoes)
        anexar(destino, registro)
        if ao_terminar:
            ao_terminar(registro)
        return registro

    chamadas: Counter[str] = Counter()
    truncadas: Counter[str] = Counter()
    with ThreadPoolExecutor(max_workers=max(1, cfg.paralelismo)) as piscina:
        for registro in piscina.map(trabalho, tarefas):
            condicao = str(registro.get("condicao", ""))
            chamadas[condicao] += 1
            if registro.get("finish_reason") == "length":
                truncadas[condicao] += 1
            if registro.get("falha_tecnica"):
                resumo["falhas_tecnicas"] += 1
            else:
                resumo["ok"] += 1
    resumo["chamadas_por_condicao"] = dict(sorted(chamadas.items()))
    resumo["truncadas_por_condicao"] = dict(sorted(truncadas.items()))
    return resumo


def _com_reexecucoes(
    cfg: Config, prefixo: Prefixo, condicao: str, execucao: int, reexecucoes: int
) -> dict[str, Any]:
    chamada = _chamada(condicao)
    registro: dict[str, Any] = {}
    for tentativa in range(1, reexecucoes + 2):
        registro = chamada(cfg, prefixo, execucao)
        registro["tentativas"] = tentativa
        if not registro.get("erro") and str(registro.get("message", "")).strip():
            registro["falha_tecnica"] = False
            break
        registro["falha_tecnica"] = True
    return {
        **_contexto(prefixo),
        **registro,
        # A identidade da chamada é do executor, não da condição: garante chave e retomada.
        "condicao": condicao,
        "execucao": execucao,
        "chave": chave(prefixo.id, condicao, execucao),
    }


def _contexto(prefixo: Prefixo) -> dict[str, Any]:
    return {
        "prefixo_id": prefixo.id,
        "item_id": prefixo.item_id,
        "origem": prefixo.origem,
        "tipo_bug": prefixo.tipo_bug,
        "prioridade": prefixo.prioridade,
        "k": prefixo.k,
        "tipo_prefixo": prefixo.tipo,
        "posicao_pressao": prefixo.posicao_pressao,
        "movimento_anterior": prefixo.movimento_anterior,
        "estagnacao_acumulada": prefixo.estagnacao_acumulada,
    }
