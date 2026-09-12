"""Orquestração do juiz sobre uma execução: turnos gerados e turnos de referência.

Retomável por chave: um juízo já registrado não é refeito, nem quando o comando é reexecutado
depois de uma queda. A condição de origem é gravada no registro para a análise, mas **não** é
enviada ao juiz.
"""

from __future__ import annotations

import logging
import time

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from avaliacao import juiz
from avaliacao.config import Config
from avaliacao.executor import ARQUIVO_TURNOS
from avaliacao.itens import Prefixo, expandir_prefixos, turnos_de_referencia
from avaliacao.registro import anexar, ler_ndjson

logger = logging.getLogger(__name__)

ARQUIVO_JUIZOS = "juizos.jsonl"

#: Espera antes de repetir um veredito que falhou, multiplicada pelo número da tentativa.
#: Repetir de imediato é desperdiçar as três tentativas no mesmo minuto em que o provedor está a
#: limitar; com a pausa, a segunda e a terceira caem já do outro lado da janela.
PAUSA_ENTRE_TENTATIVAS_S = 2.0


def indexar_prefixos(itens: list[dict[str, Any]]) -> dict[str, Prefixo]:
    return {p.id: p for item in itens for p in expandir_prefixos(item)}


def julgar_execucao(
    cfg: Config,
    diretorio: Path,
    itens: list[dict[str, Any]],
    *,
    incluir_referencia: bool = True,
    limite: int | None = None,
    tentativas: int = 3,
) -> dict[str, int]:
    destino = diretorio / ARQUIVO_JUIZOS
    feitos = _julgados_com_sucesso(destino, cfg.juiz_modelo)
    por_id = {item["id"]: item for item in itens}
    prefixos = indexar_prefixos(itens)

    pendentes: list[dict[str, Any]] = []
    if incluir_referencia:
        pendentes.extend(_pendencias_referencia(por_id, feitos))
    pendentes.extend(_pendencias_geradas(diretorio / ARQUIVO_TURNOS, por_id, prefixos, feitos))
    if limite is not None:
        pendentes = pendentes[:limite]

    resumo: dict[str, Any] = {
        "planejados": len(pendentes),
        "ok": 0,
        "erros": 0,
        "reaproveitados": len(feitos),
        "tokens": {"entrada": 0, "saida": 0, "total": 0},
    }
    if not pendentes:
        return resumo

    def trabalho(pendencia: dict[str, Any]) -> dict[str, Any]:
        item = por_id[pendencia["item_id"]]
        veredito: dict[str, Any] = {}
        for tentativa in range(1, tentativas + 1):
            try:
                veredito = juiz.julgar(cfg, item, pendencia["contexto"], pendencia["turno"])
            except Exception as exc:  # noqa: BLE001 — um veredito não derruba a corrida
                # Sem isto, uma única resposta em forma inesperada mata as duas mil chamadas
                # restantes: a exceção sobe da piscina de threads e nada é reaproveitado além do
                # que já estava gravado. O erro passa a ser do turno, contado em ``erros``, e a
                # corrida segue — que é o que o laço de tentativas e o resumo já pressupunham.
                logger.exception("juiz falhou em %s", pendencia["meta"].get("prefixo_id", "?"))
                veredito = {"erro": f"{type(exc).__name__}: {exc}"[:300]}
            veredito["tentativas"] = tentativa
            if not veredito.get("erro") and veredito.get("diretividade") is not None:
                break
            if tentativa < tentativas:
                time.sleep(PAUSA_ENTRE_TENTATIVAS_S * tentativa)
        registro = {**pendencia["meta"], **veredito}
        anexar(destino, registro)
        return registro

    with ThreadPoolExecutor(max_workers=max(1, cfg.paralelismo)) as piscina:
        for registro in piscina.map(trabalho, pendentes):
            if registro.get("erro") or registro.get("diretividade") is None:
                resumo["erros"] += 1
            else:
                resumo["ok"] += 1
            _somar_tokens(resumo["tokens"], registro.get("tokens") or {})
    return resumo


def _somar_tokens(acumulado: dict[str, int], uso: dict[str, Any]) -> None:
    """Consumo do juiz, para dimensionar o custo antes de mandar a corrida inteira.

    Aceita as duas formas: a do proxy OpenAI-compatível e a da API da Google.
    """
    acumulado["entrada"] += int(uso.get("prompt_tokens") or uso.get("promptTokenCount") or 0)
    acumulado["saida"] += int(uso.get("completion_tokens") or uso.get("candidatesTokenCount") or 0)
    acumulado["total"] += int(uso.get("total_tokens") or uso.get("totalTokenCount") or 0)


def _julgados_com_sucesso(caminho: Path, modelo: str) -> set[str]:
    """Juízos já feitos **pelo mesmo modelo**.

    Juízo com erro não conta como feito, e juízo de outro modelo também não: trocar o juiz
    (ensaio barato → modelo do protocolo) re-julga tudo, em vez de completar o conjunto do outro
    e produzir uma amostra com dois juízes misturados.
    """
    return {
        registro.get("chave", "")
        for registro in ler_ndjson(caminho)
        if not registro.get("erro")
        and registro.get("diretividade") is not None
        and registro.get("juiz_modelo", modelo) == modelo
    }


def _pendencias_referencia(
    por_id: dict[str, dict[str, Any]], feitos: set[str]
) -> list[dict[str, Any]]:
    pendentes = []
    for item in por_id.values():
        for referencia in turnos_de_referencia(item):
            if referencia["id"] in feitos:
                continue
            pendentes.append(
                {
                    "item_id": item["id"],
                    "turno": referencia["texto"],
                    "contexto": {
                        "history": referencia["history"],
                        "code": referencia["code"],
                        "errors": referencia["errors"],
                    },
                    "meta": {
                        "chave": referencia["id"],
                        "unidade": "referencia",
                        "condicao": "REF",
                        "item_id": item["id"],
                        "origem": item["origem"],
                        "tipo_bug": item["tipo_bug"],
                        "prefixo_id": referencia["id"],
                        "k": referencia["k"],
                        "tipo_prefixo": "ouro",
                        "execucao": 0,
                        "movimento_anterior": referencia["movimento_anterior"],
                        "estagnacao_acumulada": referencia["estagnacao_acumulada"],
                    },
                }
            )
    return pendentes


def _pendencias_geradas(
    caminho_turnos: Path,
    por_id: dict[str, dict[str, Any]],
    prefixos: dict[str, Prefixo],
    feitos: set[str],
) -> list[dict[str, Any]]:
    pendentes = []
    for turno in ler_ndjson(caminho_turnos):
        chave = turno.get("chave", "")
        if chave in feitos or turno.get("falha_tecnica"):
            continue
        mensagem = str(turno.get("message", "")).strip()
        prefixo = prefixos.get(turno.get("prefixo_id", ""))
        if not mensagem or prefixo is None or turno.get("item_id") not in por_id:
            continue
        pendentes.append(
            {
                "item_id": turno["item_id"],
                "turno": mensagem,
                "contexto": {
                    "history": prefixo.history,
                    "code": prefixo.code,
                    "errors": prefixo.errors,
                },
                "meta": {
                    "chave": chave,
                    "unidade": "gerado",
                    "condicao": turno.get("condicao", ""),
                    "item_id": turno.get("item_id", ""),
                    "origem": turno.get("origem", ""),
                    "tipo_bug": turno.get("tipo_bug", ""),
                    "prefixo_id": turno.get("prefixo_id", ""),
                    "k": turno.get("k", 0),
                    "tipo_prefixo": turno.get("tipo_prefixo", ""),
                    "posicao_pressao": turno.get("posicao_pressao", ""),
                    "execucao": turno.get("execucao", 0),
                    "movimento_anterior": turno.get("movimento_anterior", ""),
                    "estagnacao_acumulada": turno.get("estagnacao_acumulada", 0),
                },
            }
        )
    return pendentes
