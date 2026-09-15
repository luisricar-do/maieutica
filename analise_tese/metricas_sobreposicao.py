"""Tarefa 6 — BLEU-4, ROUGE-L e BERTScore multilíngue contra as referências de cada posição.

Cada turno gerado num prefixo de referência é comparado com o **conjunto** de referências
daquela posição do item: o turno de tutor adotado mais as alternativas anotadas na tradução.
Os prefixos de pressão ficam fora: não há turno humano naquela posição para comparar, e a
condição B só correu prefixos de pressão — por isso não tem sobreposição a reportar.

O que estes números são: distância lexical e semântica ao que um instrutor escreveu. O que
**não** são: medida de qualidade do andaime. Um turno pode acertar a estratégia e não partilhar
uma palavra com a referência. Entram no capítulo como descritivas, ao lado das do *benchmark*
original, e não decidem hipótese nenhuma.

Corre num ambiente à parte: a bancada é deliberadamente sem dependências e não recebe torch.

    python -m venv .venv-metricas
    .venv-metricas/bin/pip install sacrebleu rouge-score bert-score
    .venv-metricas/bin/python -m analise_tese.metricas_sobreposicao   # → saida/metricas_sobreposicao.json
"""

from __future__ import annotations

import json
import os
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent
BANCO = RAIZ / "avaliacao" / "banco"
EXECUCAO = RAIZ / "avaliacao" / "execucoes" / os.environ.get("AVALIACAO_EXECUCAO", "cap4")
SAIDA = Path(__file__).resolve().parent / "saida"

MODELO_BERT = "bert-base-multilingual-cased"


def referencias_por_posicao() -> dict[tuple[str, int], list[str]]:
    """`(item_id, k)` → turno de tutor adotado + alternativas anotadas. `k` conta turnos de tutor."""
    mapa: dict[tuple[str, int], list[str]] = {}
    for caminho in sorted(BANCO.glob("*.json")):
        item = json.loads(caminho.read_text(encoding="utf-8"))
        k = 0
        for turno in item.get("dialogo", []):
            if turno.get("papel") != "tutor":
                continue
            k += 1
            mapa[(item["id"], k)] = [turno.get("texto", "")] + list(turno.get("alternativas", []))
    return mapa


def gerados() -> list[dict[str, Any]]:
    with (EXECUCAO / "turnos.jsonl").open(encoding="utf-8") as arquivo:
        turnos = [json.loads(ln) for ln in arquivo if ln.strip()]
    saida = []
    for t in turnos:
        if t.get("tipo_prefixo") != "ouro" or t.get("falha_tecnica"):
            continue
        texto = (t.get("message") or "").strip()
        if texto:
            saida.append({"chave": t["chave"], "condicao": t["condicao"],
                          "item_id": t["item_id"], "k": int(t["k"]), "texto": texto})
    return saida


def main() -> None:
    import sacrebleu
    from bert_score import score as bertscore
    from rouge_score import rouge_scorer

    refs = referencias_por_posicao()
    turnos = gerados()
    faltam = {(t["item_id"], t["k"]) for t in turnos} - set(refs)
    if faltam:
        raise SystemExit(f"posições sem referência no banco: {sorted(faltam)[:5]}")

    max_refs = max(len(refs[(t["item_id"], t["k"])]) for t in turnos)
    marcador = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=False)

    por_condicao: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    corpus: dict[str, dict[str, list]] = defaultdict(
        lambda: {"hip": [], "refs": [[] for _ in range(max_refs)], "melhor_ref": []})

    for t in turnos:
        conjunto = refs[(t["item_id"], t["k"])]
        c = t["condicao"]
        # BLEU por segmento, multi-referência; sacrebleu já toma o melhor casamento por n-grama.
        por_condicao[c]["bleu4_segmento"].append(
            sacrebleu.sentence_bleu(t["texto"], conjunto).score)
        # ROUGE-L: máximo sobre as referências, como faz o benchmark original.
        por_condicao[c]["rougeL"].append(
            max(marcador.score(r, t["texto"])["rougeL"].fmeasure for r in conjunto))
        corpus[c]["hip"].append(t["texto"])
        for i in range(max_refs):
            corpus[c]["refs"][i].append(conjunto[i] if i < len(conjunto) else "")
        # BERTScore não tem multi-referência nativa: guarda-se a referência mais próxima em ROUGE-L
        # e o par vai daí. Tomar o máximo sobre as referências inflaciona por escolha a posteriori.
        corpus[c]["melhor_ref"].append(
            max(conjunto, key=lambda r: marcador.score(r, t["texto"])["rougeL"].fmeasure))

    resultado: dict[str, Any] = {
        "modelo_bertscore": MODELO_BERT,
        "n_referencias_por_posicao": {
            "minimo": min(len(v) for v in refs.values()),
            "maximo": max(len(v) for v in refs.values()),
            "total_alternativas": sum(len(v) - 1 for v in refs.values()),
        },
        "condicao_B": "sem prefixos de referência — não há posição humana a comparar",
        "por_condicao": {},
    }
    for c, dados in sorted(corpus.items()):
        bleu = sacrebleu.corpus_bleu(dados["hip"], dados["refs"])
        P, R, F = bertscore(dados["hip"], dados["melhor_ref"],
                            model_type=MODELO_BERT, num_layers=9, verbose=False)
        resultado["por_condicao"][c] = {
            "n": len(dados["hip"]),
            "bleu4_corpus": round(bleu.score, 3),
            "bleu4_assinatura": str(bleu),
            "bleu4_segmento_medio": round(statistics.mean(por_condicao[c]["bleu4_segmento"]), 3),
            "bleu4_segmento_mediana": round(statistics.median(por_condicao[c]["bleu4_segmento"]), 3),
            "rougeL_medio": round(statistics.mean(por_condicao[c]["rougeL"]), 3),
            "rougeL_mediana": round(statistics.median(por_condicao[c]["rougeL"]), 3),
            "bertscore_f1_medio": round(float(F.mean()), 3),
            "bertscore_f1_mediana": round(float(F.median()), 3),
            "bertscore_precisao_media": round(float(P.mean()), 3),
            "bertscore_revocacao_media": round(float(R.mean()), 3),
        }

    SAIDA.mkdir(parents=True, exist_ok=True)
    (SAIDA / "metricas_sobreposicao.json").write_text(
        json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(resultado, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
