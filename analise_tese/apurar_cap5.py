"""Apuração fechada dos valores do Capítulo 5 — Tarefas A a G.

Só leitura: abre ``avaliacao/execucoes/cap4/`` e ``avaliacao/prompts/`` e escreve apenas em
``analise_tese/saida/``. Nenhum artefato congelado é tocado.

    python -m analise_tese.apurar_cap5
"""

from __future__ import annotations

import collections
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from avaliacao.estatistica import kappa_cohen, kappa_ponderado  # noqa: E402
from analise_tese import comum  # noqa: E402

ESCALAS = {"diretividade": (0, 1, 2, 3), "fidelidade": (1, 2, 3)}


def _kappa(variavel: str, a: list, b: list) -> float:
    if variavel in ESCALAS:
        return kappa_ponderado(a, b, escala=ESCALAS[variavel])
    return kappa_cohen(a, b)


def tarefa_a(dados: dict) -> dict:
    """Composição dos prefixos: distintos, por tipo, e unidades por condição."""
    turnos = dados["turnos"].values()
    por_tipo = collections.defaultdict(set)
    unidades = set()
    for turno in turnos:
        por_tipo[turno["tipo_prefixo"]].add(turno["prefixo_id"])
        unidades.add((turno["prefixo_id"], turno["condicao"]))
    ouro, pressao = len(por_tipo["ouro"]), len(por_tipo["pressao"])
    por_condicao = collections.Counter(condicao for _, condicao in unidades)
    execucoes = collections.Counter(
        collections.Counter((t["prefixo_id"], t["condicao"]) for t in turnos).values()
    )
    return {
        "prefixos_distintos": ouro + pressao,
        "prefixos_referencia_ouro": ouro,
        "prefixos_pressao": pressao,
        "unidades_prefixo_condicao": dict(sorted(por_condicao.items())),
        "unidades_total": sum(por_condicao.values()),
        "execucoes_por_unidade": dict(execucoes),
        "turnos_gerados": len(dados["turnos"]),
        "turnos_referencia_julgados": sum(
            1 for j in dados["juizos"].values() if j["unidade"] == "referencia"
        ),
        "juizos_total": len(dados["juizos"]),
        "conta_referencia_mais_pressao_x2_mais_pressao": (ouro + pressao) * 2 + pressao,
        "prefixos_no_manifesto": dados["manifesto"]["prefixos"],
        "itens_no_banco": len(dados["manifesto"]["itens"]),
    }


def tarefa_b(dados: dict) -> dict:
    """Concordância bruta e κ humano×juiz nas oito variáveis, sobre os 210 codificados."""
    ids = sorted(dados["codificacao"])
    saida = {}
    for variavel in comum.VARIAVEIS:
        humano, juiz = [], []
        for id_cego in ids:
            valor = comum.valor_humano(dados["codificacao"][id_cego], variavel)
            juizo = dados["juizos"].get(dados["mapa"].get(id_cego, ""))
            if valor is None or not juizo:
                continue
            humano.append(valor)
            juiz.append(comum.valor_juiz(juizo, variavel))
        acordos = sum(1 for a, b in zip(humano, juiz) if a == b)
        registro = {
            "n": len(humano),
            "bruta": round(acordos / len(humano), 3),
            "conta": f"{acordos}/{len(humano)}",
            "kappa": round(_kappa(variavel, humano, juiz), 4),
        }
        if variavel in ESCALAS:
            um_nivel = sum(1 for a, b in zip(humano, juiz) if abs(a - b) <= 1)
            registro["bruta_dentro_de_um_nivel"] = round(um_nivel / len(humano), 3)
            registro["conta_dentro_de_um_nivel"] = f"{um_nivel}/{len(humano)}"
        saida[variavel] = registro

    # Fidelidade fora do bloco de nível 3, onde a rubrica impõe o acordo (commit dd8f83d).
    humano, juiz = [], []
    for id_cego in ids:
        if comum.valor_humano(dados["codificacao"][id_cego], "diretividade") == 3:
            continue
        juizo = dados["juizos"][dados["mapa"][id_cego]]
        humano.append(comum.valor_humano(dados["codificacao"][id_cego], "fidelidade"))
        juiz.append(comum.valor_juiz(juizo, "fidelidade"))
    acordos = sum(1 for a, b in zip(humano, juiz) if a == b)
    saida["fidelidade_restrita_diretividade_0_2"] = {
        "n": len(humano),
        "bruta": round(acordos / len(humano), 3),
        "conta": f"{acordos}/{len(humano)}",
        "kappa": round(_kappa("fidelidade", humano, juiz), 4),
    }
    return saida


def tarefa_c(dados: dict) -> dict:
    """Os turnos cuja anotação da tradução é ``NENHUM`` ou ``REGRESSAO``, nos 180 gerados."""
    gerados = [i for i in sorted(dados["codificacao"]) if dados["mapa"][i] in dados["turnos"]]
    alvo = [
        i for i in gerados
        if dados["turnos"][dados["mapa"][i]]["movimento_anterior"] in ("NENHUM", "REGRESSAO")
    ]
    linhas = []
    for id_cego in alvo:
        chave = dados["mapa"][id_cego]
        linhas.append(
            {
                "id_cego": id_cego,
                "chave": chave,
                "condicao": comum.condicao_de(chave),
                "anotacao": dados["turnos"][chave]["movimento_anterior"],
                "humano": comum.valor_humano(dados["codificacao"][id_cego], "movimento_estudante"),
                "juiz": comum.valor_juiz(dados["juizos"][chave], "movimento_estudante"),
            }
        )
    anotacao = [dados["turnos"][dados["mapa"][i]]["movimento_anterior"] for i in gerados]
    humano = [comum.valor_humano(dados["codificacao"][i], "movimento_estudante") for i in gerados]
    juiz = [comum.valor_juiz(dados["juizos"][dados["mapa"][i]], "movimento_estudante") for i in gerados]
    return {
        "n_alvo": len(alvo),
        "anotacao_nos_180": dict(collections.Counter(anotacao)),
        "turnos": linhas,
        "cruzada_anotacao_humano": {
            f"{a}->{b}": n
            for (a, b), n in sorted(collections.Counter((x["anotacao"], x["humano"]) for x in linhas).items())
        },
        "cruzada_anotacao_juiz": {
            f"{a}->{b}": n
            for (a, b), n in sorted(collections.Counter((x["anotacao"], x["juiz"]) for x in linhas).items())
        },
        "movimento_180_gerados": {
            "anotacao_x_humano": {
                "kappa": round(kappa_cohen(anotacao, humano), 4),
                "bruta": round(sum(a == b for a, b in zip(anotacao, humano)) / len(gerados), 3),
                "conta": f"{sum(a == b for a, b in zip(anotacao, humano))}/{len(gerados)}",
            },
            "anotacao_x_juiz": {
                "kappa": round(kappa_cohen(anotacao, juiz), 4),
                "bruta": round(sum(a == b for a, b in zip(anotacao, juiz)) / len(gerados), 3),
                "conta": f"{sum(a == b for a, b in zip(anotacao, juiz))}/{len(gerados)}",
            },
        },
    }


def tarefa_d(dados: dict) -> dict:
    """Turnos cortados no limite de tokens e o que a análise faz com eles."""
    truncados = [t for t in dados["turnos"].values() if t.get("finish_reason") == "length"]
    inverso = {v: k for k, v in dados["mapa"].items()}
    return {
        "n": len(truncados),
        "por_condicao": dict(collections.Counter(t["condicao"] for t in truncados)),
        "turnos": sorted(
            (
                {
                    "chave": t["chave"],
                    "condicao": t["condicao"],
                    "item_id": t["item_id"],
                    "prefixo_id": t["prefixo_id"],
                    "k": t["k"],
                    "execucao": t["execucao"],
                    "tokens_saida": (t.get("tokens") or {}).get("completionTokens"),
                    "id_cego": inverso.get(t["chave"], ""),
                }
                for t in truncados
            ),
            key=lambda r: (r["prefixo_id"], r["execucao"]),
        ),
        "julgados": sum(1 for t in truncados if t["chave"] in dados["juizos"]),
        "marcados_falha_tecnica": sum(1 for t in truncados if t.get("falha_tecnica")),
        "na_amostra_humana": [inverso[t["chave"]] for t in truncados if t["chave"] in inverso],
    }


def tarefa_e(dados: dict) -> dict:
    """Os turnos de diretividade 3 na codificação humana: origem e condição."""
    ids = sorted(dados["codificacao"])
    tres = [i for i in ids if comum.valor_humano(dados["codificacao"][i], "diretividade") == 3]
    juiz_tres = [i for i in ids if comum.valor_juiz(dados["juizos"][dados["mapa"][i]], "diretividade") == 3]
    return {
        "humanos_nivel_3": len(tres),
        "por_unidade": dict(
            collections.Counter(
                "gerado" if dados["mapa"][i] in dados["turnos"] else "referencia" for i in tres
            )
        ),
        "por_condicao": dict(collections.Counter(comum.condicao_de(dados["mapa"][i]) for i in tres)),
        "referencia_nivel_3": [i for i in tres if dados["mapa"][i] not in dados["turnos"]],
        "juiz_nivel_3": len(juiz_tres),
        "juiz_nivel_3_com_fidelidade_1": sum(
            1 for i in juiz_tres if comum.valor_juiz(dados["juizos"][dados["mapa"][i]], "fidelidade") == 1
        ),
        "humanos_nivel_3_com_fidelidade_1": sum(
            1 for i in tres if comum.valor_humano(dados["codificacao"][i], "fidelidade") == 1
        ),
    }


def tarefa_f(dados: dict) -> dict:
    """A variável só-humana ``incorreta``: frequência, identificadores e cobertura das notas."""
    ids = sorted(dados["codificacao"])
    marcados = [i for i in ids if comum.valor_humano(dados["codificacao"][i], "incorreta") is True]
    preenchidos = [i for i in ids if comum.valor_humano(dados["codificacao"][i], "incorreta") is not None]
    return {
        "marcados": len(marcados),
        "de": len(preenchidos),
        "ids": marcados,
        "linhas_com_notas": sum(1 for i in ids if dados["codificacao"][i]["notas"].strip()),
        "por_condicao": dict(collections.Counter(comum.condicao_de(dados["mapa"][i]) for i in marcados)),
        "diretividade_humana": dict(
            collections.Counter(comum.valor_humano(dados["codificacao"][i], "diretividade") for i in marcados)
        ),
        "juiz_marcou_irrelevante": sum(
            1 for i in marcados if comum.valor_juiz(dados["juizos"][dados["mapa"][i]], "irrelevante")
        ),
    }


def tarefa_g(dados: dict) -> dict:
    """Hashes, versão do juiz devolvida pela API e datas da corrida."""
    prompts = comum.RAIZ / "avaliacao" / "prompts"
    def _hashes(nome: str) -> dict:
        caminho = prompts / nome
        bruto = caminho.read_bytes()
        texto = caminho.read_text(encoding="utf-8").strip()
        return {
            "arquivo": str(caminho.relative_to(comum.RAIZ)),
            "sha256_bytes": hashlib.sha256(bruto).hexdigest(),
            "sha256_texto_strip": hashlib.sha256(texto.encode("utf-8")).hexdigest(),
        }

    juizos = list(dados["juizos"].values())
    turnos = list(dados["turnos"].values())
    return {
        "manifesto_hash_prompt_juiz": dados["manifesto"]["hash_prompt_juiz"],
        "juiz_md": _hashes("juiz.md"),
        "juiz_revisto_md": _hashes("juiz-revisto.md"),
        "juiz_prompt_hash_nos_juizos": dict(collections.Counter(j["juiz_prompt_hash"] for j in juizos)),
        "juiz_modelo_pedido": dados["manifesto"]["juiz_modelo"],
        "juiz_versao_devolvida": dict(collections.Counter(j.get("juiz_versao") for j in juizos)),
        "juiz_transporte": dict(collections.Counter(j.get("juiz_transporte") for j in juizos)),
        "manifesto_criado_em": dados["manifesto"]["criado_em"],
        "manifesto_atualizado_em": dados["manifesto"]["atualizado_em"],
        "commit_maieutica": dados["manifesto"]["commit_maieutica"],
        "turnos_ts": [min(t["ts"] for t in turnos), max(t["ts"] for t in turnos)],
        "juizos_ts": [min(j["ts"] for j in juizos), max(j["ts"] for j in juizos)],
        "juizos_com_erro": sum(1 for j in juizos if j.get("erro")),
        "juizos_chaves_unicas": len(dados["juizos"]),
        "tokens_juiz": {
            "entrada": sum((j.get("tokens") or {}).get("prompt_tokens", 0) for j in juizos),
            "saida": sum((j.get("tokens") or {}).get("completion_tokens", 0) for j in juizos),
            "total": sum((j.get("tokens") or {}).get("total_tokens", 0) for j in juizos),
        },
    }


def main() -> None:
    dados = comum.carregar()
    relatorio = {
        "A_composicao_prefixos": tarefa_a(dados),
        "B_concordancia": tarefa_b(dados),
        "C_movimento": tarefa_c(dados),
        "D_truncados": tarefa_d(dados),
        "E_nivel_3": tarefa_e(dados),
        "F_incorreta": tarefa_f(dados),
        "G_hashes": tarefa_g(dados),
    }
    destino = comum.escrever("apuracao_cap5.json", relatorio)
    import json
    print(json.dumps(relatorio, indent=2, ensure_ascii=False))
    print(f"\n[escrito] {destino}", file=sys.stderr)


if __name__ == "__main__":
    main()
