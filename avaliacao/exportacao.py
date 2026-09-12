"""Exportação para as métricas de sobreposição (BLEU-4, ROUGE-L, BERTScore).

O plano analítico diz que essas métricas são calculadas **com o código do benchmark original**,
não por este pacote — e é bom que seja assim: BERTScore exigiria um modelo neural, e a bancada é
deliberadamente stdlib. O que falta é a ponte, e é o que este módulo faz: emparelha cada turno
gerado com o conjunto de referências da sua posição (o turno do tutor humano mais as
alternativas anotadas) e grava um JSONL que o código original consome.

Só prefixos de referência entram. Os de pressão são artificiais e não têm turno humano
correspondente (Subseção dos prefixos de pressão), logo não há contra o que medir sobreposição.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from avaliacao.executor import ARQUIVO_TURNOS
from avaliacao.julgamento import indexar_prefixos
from avaliacao.registro import ler_ndjson

ARQUIVO_SOBREPOSICAO = "sobreposicao.jsonl"


def linhas_de_sobreposicao(
    diretorio: Path, itens: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Um registro por turno gerado com referência disponível."""
    prefixos = indexar_prefixos(itens)
    linhas: list[dict[str, Any]] = []
    for turno in ler_ndjson(diretorio / ARQUIVO_TURNOS):
        if turno.get("falha_tecnica"):
            continue
        mensagem = str(turno.get("message", "")).strip()
        if not mensagem:
            continue
        prefixo = prefixos.get(turno.get("prefixo_id", ""))
        if prefixo is None or prefixo.tipo != "ouro":
            continue
        referencias = [t for t in [prefixo.referencia, *prefixo.alternativas] if t.strip()]
        if not referencias:
            continue
        linhas.append(
            {
                "chave": turno.get("chave", ""),
                "item_id": turno.get("item_id", ""),
                "prefixo_id": prefixo.id,
                "condicao": turno.get("condicao", ""),
                "execucao": turno.get("execucao", 0),
                "k": prefixo.k,
                "tipo_bug": turno.get("tipo_bug", ""),
                "origem": turno.get("origem", ""),
                # Nomes do benchmark original: a hipótese é o turno gerado; as referências são o
                # turno humano da posição e as suas alternativas anotadas.
                "hipotese": mensagem,
                "referencias": referencias,
            }
        )
    return linhas


def exportar_sobreposicao(diretorio: Path, itens: list[dict[str, Any]]) -> dict[str, Any]:
    linhas = linhas_de_sobreposicao(diretorio, itens)
    destino = diretorio / ARQUIVO_SOBREPOSICAO
    destino.write_text(
        "".join(json.dumps(linha, ensure_ascii=False) + "\n" for linha in linhas),
        encoding="utf-8",
    )
    por_condicao: dict[str, int] = {}
    for linha in linhas:
        por_condicao[linha["condicao"]] = por_condicao.get(linha["condicao"], 0) + 1
    return {
        "pares": len(linhas),
        "por_condicao": dict(sorted(por_condicao.items())),
        "destino": str(destino),
    }
