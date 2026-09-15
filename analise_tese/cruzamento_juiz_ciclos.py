"""Cruzamento cap4 × cap5 do juiz sobre os turnos de referência — o par de julgamentos já pago.

Os turnos de referência dos 25 itens do ciclo 1 foram julgados nas duas corridas, com o mesmo
prompt (hash ``5dc2baa3…``) e o mesmo modelo. São dois julgamentos independentes sobre a mesma
unidade, sem custo adicional, e por isso valem como segunda medida de estabilidade do juiz —
**desde que** a entrada tenha sido a mesma. O script faz três coisas, nesta ordem, e a primeira
condiciona as outras:

a) **Confere a entrada.** Reconstrói, no commit de cada corrida (``git archive``), a mensagem
   exacta enviada ao juiz — ``prompt_sistema()`` + ``montar_entrada(item, contexto, turno)`` —
   para cada turno de referência, e compara hash a hash. Reporta os que diferem e **em quê**
   (texto do turno, código, histórico, campos do item, erros). Um turno cuja entrada mudou não
   mede estabilidade do juiz; mede a resposta a outra pergunta, e sai do κ.
b) **κ entre os dois ciclos** — ponderado (diretividade, fidelidade) e de Cohen (movimento,
   ancorado, falhas) — com IC percentílico por bootstrap (``estatistica.intervalo_bootstrap``),
   sobre os turnos de entrada idêntica; e, à parte e rotulado, sobre todos.
c) **Os pares da linha REF «bloqueio agregado»** da tabela de H1, nos dois ciclos: mesmos pares,
   quantos e quais viraram, e em que sentido — é a única taxa do capítulo onde a instabilidade
   do juiz sobre entrada idêntica fica visível.

Só leitura. Saída em ``analise_tese/saida/cruzamento_<a>_<b>.json``.

    python -m analise_tese.cruzamento_juiz_ciclos                       # cap4 × cap5
    python -m analise_tese.cruzamento_juiz_ciclos --commit-a f173f6d --commit-b 1e7e5cd
"""

from __future__ import annotations

import argparse
import collections
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from avaliacao.estatistica import intervalo_bootstrap, kappa_cohen, kappa_ponderado, wilson  # noqa: E402
from avaliacao.itens import AUTORIA_HUMANA  # noqa: E402
from analise_tese import comum  # noqa: E402

RAIZ = comum.RAIZ
EXECUCOES = RAIZ / "avaliacao" / "execucoes"
ESCALAS = {"diretividade": (0, 1, 2, 3), "fidelidade": (1, 2, 3)}
MOVIMENTOS_BLOQUEIO = ("ESTAGNACAO", "REGRESSAO")
REAMOSTRAS = 2000

#: Corre **dentro do snapshot** de um commit, com o `avaliacao` desse commit: banco, `_contexto`,
#: `montar_entrada` e `prompts/juiz.md` como estavam. É o que faz da comparação uma comparação
#: da entrada real, e não do banco de hoje consigo mesmo.
_TRABALHADOR = r'''
import hashlib, json, sys
snap = sys.argv[1]; sys.path.insert(0, snap)
from avaliacao import juiz
from avaliacao.config import BANCO_DIR
from avaliacao.itens import carregar_banco, turnos_de_referencia
itens = set(json.loads(sys.stdin.read()))
h = lambda s: hashlib.sha256(s.encode("utf-8")).hexdigest()
saida = {"hash_prompt_sistema": h(juiz.prompt_sistema()), "turnos": {}}
for item in carregar_banco(BANCO_DIR):
    if item["id"] not in itens:
        continue
    for r in turnos_de_referencia(item):
        ctx = {"history": r["history"], "code": r["code"], "errors": r["errors"]}
        saida["turnos"][r["id"]] = {
            "entrada": h(juiz.montar_entrada(item, ctx, r["texto"])),
            "texto": h(r["texto"]),
            "code": h(r["code"]),
            "history": h(json.dumps([(t.get("role"), t.get("content")) for t in r["history"]], ensure_ascii=False)),
            "item": h(json.dumps({k: item.get(k) for k in ("problem", "bug_code", "bug_desc", "bug_fixes", "anchor_tokens")}, ensure_ascii=False, sort_keys=True)),
            "errors": h(json.dumps(r["errors"], ensure_ascii=False)),
        }
print(json.dumps(saida))
'''


def _manifesto(execucao: str) -> dict:
    return json.loads((EXECUCOES / execucao / "manifesto.json").read_text(encoding="utf-8"))


def _referencias(execucao: str) -> dict[str, dict]:
    return {
        j["chave"]: j
        for j in comum.ndjson(EXECUCOES / execucao / "juizos.jsonl")
        if j.get("unidade") == "referencia" and not j.get("erro") and j.get("diretividade") is not None
    }


def _snapshot(commit: str, destino: Path) -> None:
    arquivo = subprocess.run(
        ["git", "-C", str(RAIZ), "archive", commit, "avaliacao"],
        check=True, capture_output=True,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(arquivo)) as tar:
        tar.extractall(destino)


def entradas_no_commit(commit: str, itens: list[str]) -> dict:
    with tempfile.TemporaryDirectory() as pasta:
        _snapshot(commit, Path(pasta))
        ambiente = {**os.environ, "PYTHONPATH": pasta}
        saida = subprocess.run(
            [sys.executable, "-c", _TRABALHADOR, pasta],
            input=json.dumps(itens), text=True, check=True, capture_output=True,
            cwd=pasta, env=ambiente,
        ).stdout
    return json.loads(saida)


def conferir_entrada(commit_a: str, commit_b: str, itens: list[str], chaves: list[str]) -> dict:
    a = entradas_no_commit(commit_a, itens)
    b = entradas_no_commit(commit_b, itens)
    identicos, diferentes = [], {}
    for chave in chaves:
        x, y = a["turnos"].get(chave), b["turnos"].get(chave)
        if x is None or y is None:
            diferentes[chave] = ["turno ausente num dos commits"]
            continue
        campos = [c for c in ("texto", "code", "history", "item", "errors") if x[c] != y[c]]
        if x["entrada"] == y["entrada"]:
            identicos.append(chave)
        else:
            diferentes[chave] = campos or ["montagem (código de `montar_entrada`)"]
    return {
        "commit_a": commit_a,
        "commit_b": commit_b,
        "prompt_sistema_igual": a["hash_prompt_sistema"] == b["hash_prompt_sistema"],
        "hash_prompt_sistema": {"a": a["hash_prompt_sistema"], "b": b["hash_prompt_sistema"]},
        "n": len(chaves),
        "identicos": len(identicos),
        "diferentes": len(diferentes),
        "diferentes_por_item": dict(collections.Counter(c.split("::")[0] for c in diferentes)),
        "diferentes_em": diferentes,
        "chaves_identicas": identicos,
    }


def _funcao(variavel: str):
    if variavel in ESCALAS:
        return lambda x, y: kappa_ponderado(x, y, escala=ESCALAS[variavel])
    return kappa_cohen


def _arredondar(valor: float) -> float | None:
    return None if valor != valor else round(valor, 4)


def kappas(ref_a: dict, ref_b: dict, chaves: list[str]) -> dict:
    saida: dict[str, Any] = {"n": len(chaves), "por_variavel": {}}
    for variavel in comum.VARIAVEIS:
        a = [comum.valor_juiz(ref_a[c], variavel) for c in chaves]
        b = [comum.valor_juiz(ref_b[c], variavel) for c in chaves]
        funcao = _funcao(variavel)
        intervalo = intervalo_bootstrap(a, b, funcao, reamostras=REAMOSTRAS)
        acordos = sum(1 for x, y in zip(a, b) if x == y)
        saida["por_variavel"][variavel] = {
            "kappa": _arredondar(funcao(a, b)),
            "ic95": [_arredondar(intervalo.inferior), _arredondar(intervalo.superior)],
            "reamostras_validas": intervalo.reamostras_validas,
            "bruta": round(acordos / len(a), 3) if a else None,
            "conta": f"{acordos}/{len(a)}",
        }
    deltas = collections.Counter(
        abs(int(ref_a[c]["diretividade"]) - int(ref_b[c]["diretividade"])) for c in chaves
    )
    saida["diretividade_mudou"] = {
        "turnos": sum(v for d, v in deltas.items() if d > 0),
        "por_distancia": {str(d): v for d, v in sorted(deltas.items())},
    }
    return saida


def contingente(movimento: str, anterior: int | None, atual: int | None) -> bool | None:
    """Mesma regra de ``avaliacao.analise._contingente``, replicada para não importar dali."""
    if anterior is None or atual is None:
        return None
    if movimento in MOVIMENTOS_BLOQUEIO:
        return atual > anterior or (atual == anterior == 2)
    if movimento == "PROGRESSO":
        return atual <= anterior
    return None


def pares_ref(referencias: dict[str, dict]) -> dict[tuple[str, int], dict]:
    """Os pares (d_{k-1}, d_k) da linha REF de H1, só sobre referência de autoria humana."""
    humanas = [j for j in referencias.values()
               if str(j.get("referencia_autoria") or AUTORIA_HUMANA) == AUTORIA_HUMANA]
    por_item: dict[str, dict[int, dict]] = collections.defaultdict(dict)
    for j in humanas:
        por_item[j["item_id"]][int(j.get("k", 0))] = j
    pares = {}
    for item_id, posicoes in por_item.items():
        for k, registro in sorted(posicoes.items()):
            anterior = posicoes.get(k - 1)
            if anterior is None:
                continue
            veredito = contingente(registro.get("movimento_anterior", ""),
                                   anterior.get("diretividade"), registro.get("diretividade"))
            if veredito is None:
                continue
            pares[(item_id, k)] = {
                "chave": registro["chave"],
                "movimento_anterior": registro.get("movimento_anterior", ""),
                "estagnacao_acumulada": int(registro.get("estagnacao_acumulada") or 0),
                "d_anterior": anterior.get("diretividade"),
                "d_atual": registro.get("diretividade"),
                "contingente": veredito,
            }
    return pares


def cruzar_ref_bloqueio(ref_a: dict, ref_b: dict, identicas: set[str]) -> dict:
    pa, pb = pares_ref(ref_a), pares_ref(ref_b)
    saida: dict[str, Any] = {"mesmos_pares": sorted(pa) == sorted(pb), "por_grupo": {}}
    grupos = (
        ("bloqueio_agregado", lambda p: p["movimento_anterior"] in MOVIMENTOS_BLOQUEIO),
        ("bloqueio_acc_ge_3", lambda p: p["movimento_anterior"] in MOVIMENTOS_BLOQUEIO and p["estagnacao_acumulada"] >= 3),
        ("apos_progresso", lambda p: p["movimento_anterior"] == "PROGRESSO"),
    )
    for nome, filtro in grupos:
        comuns = [k for k in sorted(pa) if k in pb and filtro(pa[k])]
        sa = sum(1 for k in comuns if pa[k]["contingente"])
        sb = sum(1 for k in comuns if pb[k]["contingente"])
        viraram = []
        for k in comuns:
            if pa[k]["contingente"] != pb[k]["contingente"]:
                chave = pa[k]["chave"]
                chave_anterior = f"{k[0]}::k{k[1] - 1}::referencia"
                viraram.append({
                    "item_id": k[0], "k": k[1], "chave": chave,
                    "movimento_anterior": pa[k]["movimento_anterior"],
                    "estagnacao_acumulada": pa[k]["estagnacao_acumulada"],
                    "a": {"d_anterior": pa[k]["d_anterior"], "d_atual": pa[k]["d_atual"], "contingente": pa[k]["contingente"]},
                    "b": {"d_anterior": pb[k]["d_anterior"], "d_atual": pb[k]["d_atual"], "contingente": pb[k]["contingente"]},
                    "entrada_identica": {"d_k": chave in identicas, "d_k-1": chave_anterior in identicas},
                })
        wa, wb = wilson(sa, len(comuns)), wilson(sb, len(comuns))
        saida["por_grupo"][nome] = {
            "n": len(comuns),
            "a": {"contingentes": sa, "taxa": wa.como_texto()},
            "b": {"contingentes": sb, "taxa": wb.como_texto()},
            "diferenca_pp": round(100 * (wb.estimativa - wa.estimativa), 1) if comuns else None,
            "viraram": len(viraram),
            "quais": viraram,
        }
    return saida


def main() -> None:
    analisador = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    analisador.add_argument("--a", default="cap4")
    analisador.add_argument("--b", default="cap5")
    analisador.add_argument("--commit-a", default="", help="padrão: commit_maieutica do manifesto de --a")
    analisador.add_argument("--commit-b", default="", help="padrão: commit_maieutica do manifesto de --b")
    args = analisador.parse_args()

    ma, mb = _manifesto(args.a), _manifesto(args.b)
    commit_a = args.commit_a or ma["commit_maieutica"]
    commit_b = args.commit_b or mb["commit_maieutica"]
    ref_a, ref_b = _referencias(args.a), _referencias(args.b)
    chaves = sorted(set(ref_a) & set(ref_b))
    so_em_a = sorted(set(ref_a) - set(ref_b))

    # Metadados que a análise lê e que também têm de ser os mesmos.
    meta_divergente = [
        c for c in chaves
        if any(ref_a[c].get(campo) != ref_b[c].get(campo)
               for campo in ("item_id", "k", "movimento_anterior", "estagnacao_acumulada"))
    ]
    if so_em_a or meta_divergente:
        raise SystemExit(
            f"turnos de referência de {args.a} ausentes em {args.b}: {so_em_a}; "
            f"metadados divergentes: {meta_divergente}"
        )
    if ma["hash_prompt_juiz"] != mb["hash_prompt_juiz"] or ma["juiz_modelo"] != mb["juiz_modelo"]:
        raise SystemExit("prompt ou modelo do juiz diferem entre as corridas: não é repetição.")

    itens = sorted({ref_a[c]["item_id"] for c in chaves})
    entrada = conferir_entrada(commit_a, commit_b, itens, chaves)
    identicas = set(entrada.pop("chaves_identicas"))

    relatorio = {
        "corridas": {
            "a": {"id": args.a, "commit": commit_a, "juiz": ma["juiz_modelo"], "hash_prompt_juiz": ma["hash_prompt_juiz"]},
            "b": {"id": args.b, "commit": commit_b, "juiz": mb["juiz_modelo"], "hash_prompt_juiz": mb["hash_prompt_juiz"]},
        },
        "ic": f"percentílico, bootstrap sobre os pares, {REAMOSTRAS} reamostras, semente fixa",
        "a_entrada": entrada,
        "b_kappa_entrada_identica": kappas(ref_a, ref_b, sorted(identicas)),
        "b_kappa_todos_ROTULADO_inclui_entrada_diferente": kappas(ref_a, ref_b, chaves),
        "c_linha_ref_h1": cruzar_ref_bloqueio(ref_a, ref_b, identicas),
    }
    destino = comum.escrever(f"cruzamento_{args.a}_{args.b}.json", relatorio)
    print(json.dumps(relatorio, indent=2, ensure_ascii=False))
    print(f"\n→ {destino}", file=sys.stderr)


if __name__ == "__main__":
    main()
