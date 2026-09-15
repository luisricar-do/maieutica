"""Confere a corrida contra os números que `avaliacao/CICLOS.md` regista. **Só leitura.**

Cada verificação imprime MEDIDO, DECLARADO e o veredito. Existe porque o pré-registo só vale se
for conferido contra o que a corrida produziu, e porque duas das verificações abaixo reprovam.

    AVALIACAO_EXECUCAO=cap5 python -m analise_tese.conferir_ciclos
"""

from __future__ import annotations

import collections
import glob
import json
import math
import os
from pathlib import Path
from typing import Any

from analise_tese import apurar_h1_h2

RAIZ = Path(__file__).resolve().parent.parent
EXECUCAO_ID = os.environ.get("AVALIACAO_EXECUCAO", "cap5")
EXECUCAO = RAIZ / "avaliacao" / "execucoes" / EXECUCAO_ID
BANCO = RAIZ / "avaliacao" / "banco"

Z = 1.959963984540054
MOVIMENTOS_BLOQUEIO = ("ESTAGNACAO", "REGRESSAO")
AUTORIA_HUMANA = "autor"

_falhas: list[str] = []


def wilson(s: int, n: int) -> str:
    if n == 0:
        return f"{s}/{n}"
    p = s / n
    d = 1 + Z * Z / n
    c = (p + Z * Z / (2 * n)) / d
    h = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / d
    return f"{s}/{n} = {p:.3f} [{max(0.0, c - h):.3f}; {min(1.0, c + h):.3f}]"


def checa(rotulo: str, medido: Any, declarado: Any) -> None:
    ok = medido == declarado
    if not ok:
        _falhas.append(rotulo)
    print(f"  [{'ok ' if ok else 'DIVERGE'}] {rotulo}")
    print(f"           medido    : {medido}")
    print(f"           CICLOS.md : {declarado}")


def ndjson(caminho: Path) -> list[dict]:
    with caminho.open(encoding="utf-8") as arquivo:
        return [json.loads(ln) for ln in arquivo if ln.strip()]


def main() -> None:
    turnos = ndjson(EXECUCAO / "turnos.jsonl")
    juizos = ndjson(EXECUCAO / "juizos.jsonl")
    print(f"EXECUÇÃO {EXECUCAO_ID}\n")

    print("== Números de controlo (seção «Números de controlo») ==")
    checa("chamadas de geração", len(turnos), 3420)
    checa("vereditos do juiz", len(juizos), 3720)
    prefixos = {t["prefixo_id"] for t in turnos}
    checa("prefixos", len(prefixos), 480)
    ouro = {t["prefixo_id"] for t in turnos if t["tipo_prefixo"] == "ouro"}
    checa("prefixos ouro", len(ouro), 300)
    checa("prefixos de pressão", len(prefixos) - len(ouro), 180)
    checa("falhas técnicas", sum(1 for t in turnos if t.get("falha_tecnica")), 0)

    a = [t for t in turnos if t["condicao"] == "A"]
    bloq = {t["prefixo_id"] for t in a
            if t.get("movimento_anterior") in MOVIMENTOS_BLOQUEIO and t["tipo_prefixo"] == "ouro"}
    checa("prefixos bloqueados (regressor de H1)", len(bloq), 74)
    faixa4 = {t["prefixo_id"] for t in a
              if t.get("movimento_anterior") in MOVIMENTOS_BLOQUEIO
              and (t.get("estagnacao_acumulada") or 0) >= 4}
    checa("prefixos bloqueados na faixa >= 4", len(faixa4), 7)
    faixa3 = {t["prefixo_id"] for t in a
              if t.get("movimento_anterior") in MOVIMENTOS_BLOQUEIO
              and (t.get("estagnacao_acumulada") or 0) >= 3}
    checa("prefixos bloqueados na faixa >= 3 (nota do limiar descritivo)", len(faixa3), 10)

    print("\n== Classificador de movimento na corrida (seção «O nó ... fica desligado») ==")
    checa("classificador_de_movimento no manifesto",
          json.loads((EXECUCAO / "manifesto.json").read_text())["classificador_de_movimento"], "regra")
    faixa = lambda v: 0 if v == 0 else (1 if 1 <= v <= 3 else 2)  # noqa: E731
    ex, fx = 0, 0
    dist_art, dist_banco = collections.Counter(), collections.Counter()
    variam = 0
    por_prefixo = collections.defaultdict(dict)
    for t in a:
        por_prefixo[t["prefixo_id"]][t["execucao"]] = t
    for pid, execs in por_prefixo.items():
        vistos = {(e["tutorMeta"] or {}).get("stagnationStreak") for e in execs.values()}
        if len(vistos) > 1:
            variam += 1
        t = execs[1]
        art = (t["tutorMeta"] or {}).get("stagnationStreak")
        banco = t["estagnacao_acumulada"]
        ex += art == banco
        fx += faixa(art) == faixa(banco)
        dist_art[faixa(art)] += 1
        dist_banco[faixa(banco)] += 1
    checa("concordância exacta do acumulado, artefato × banco", f"{ex}/480", "321/480")
    checa("concordância por faixa", f"{fx}/480", "328/480")
    checa("distribuição do artefato (0 / 1-3 / >=4)",
          f"{dist_art[0]} / {dist_art[1]} / {dist_art[2]}", "347 / 131 / 2")
    checa("distribuição do banco (0 / 1-3 / >=4)",
          f"{dist_banco[0]} / {dist_banco[1]} / {dist_banco[2]}", "384 / 89 / 7")
    checa("prefixos cujo acumulado varia entre as 3 execuções", variam, 0)

    print("\n== Referências de autoria assistida (seção «Dois pontos em aberto») ==")
    refs = [j for j in juizos if j.get("unidade") == "referencia"]
    tutor_novos = 0
    for caminho in sorted(glob.glob(str(BANCO / "*.json"))):
        item = json.loads(Path(caminho).read_text(encoding="utf-8"))
        if item.get("referencia_autoria") == "autor_com_assistencia":
            tutor_novos += sum(1 for t in item.get("dialogo", []) if t.get("papel") == "tutor")
    # 20 itens × 7 turnos de tutor. O CICLOS.md declarava 160, que é a contagem dos turnos do
    # **estudante** (20 × 8); corrigido em 2026-09-15, com a correcção ao lado do original.
    checa("turnos de tutor de referência dos 20 itens novos", tutor_novos, 140)

    assistidas_topo = sum(1 for j in refs if j.get("referencia_autoria") != AUTORIA_HUMANA)
    print(f"  referências marcadas `autor_com_assistencia` em juizos.jsonl: {assistidas_topo} de {len(refs)}")
    # A exclusão medida pela função real, não por uma cópia da sua regra aqui: uma cópia
    # concordaria com o filtro partido tão bem quanto com o corrigido.
    filtro = len(apurar_h1_h2.referencias(so_humanas=False)) - len(apurar_h1_h2.referencias())
    checa("excluídas por `apurar_h1_h2.referencias()`", filtro, assistidas_topo)

    def contingente(mov, ant, at):
        if ant is None or at is None:
            return None
        if mov in MOVIMENTOS_BLOQUEIO:
            return at > ant or (at == ant == 2)
        if mov == "PROGRESSO":
            return at <= ant
        return None

    def taxas(conjunto, rotulo):
        por_item = collections.defaultdict(dict)
        for r in conjunto:
            por_item[r["item_id"]][int(r.get("k", 0))] = r
        linhas = []
        for pos in por_item.values():
            for k, reg in sorted(pos.items()):
                ant = pos.get(k - 1)
                if ant is None:
                    continue
                v = contingente(reg.get("movimento_anterior", ""),
                                ant.get("diretividade"), reg.get("diretividade"))
                if v is not None:
                    linhas.append({"mov": reg.get("movimento_anterior", ""),
                                   "acc": int(reg.get("estagnacao_acumulada") or 0), "c": v})
        print(f"  --- {rotulo} ---")
        for r, f in (("bloqueio agregado", lambda ln: ln["mov"] in MOVIMENTOS_BLOQUEIO),
                     ("bloqueio acc >= 3", lambda ln: ln["mov"] in MOVIMENTOS_BLOQUEIO and ln["acc"] >= 3),
                     ("bloqueio acc >= 4", lambda ln: ln["mov"] in MOVIMENTOS_BLOQUEIO and ln["acc"] >= 4),
                     ("progresso", lambda ln: ln["mov"] == "PROGRESSO")):
            alvo = [ln for ln in linhas if f(ln)]
            print(f"    {r:20s} {wilson(sum(1 for ln in alvo if ln['c']), len(alvo))}")

    # As duas camadas continuam lado a lado: a de cima é o que a apuração reportava antes de
    # 2026-09-15, e fica porque é ela que está citada no histórico do CICLOS.md.
    taxas(refs, "todas as referências — o que a apuração contava com o filtro inerte")
    taxas([j for j in refs if j.get("referencia_autoria", AUTORIA_HUMANA) == AUTORIA_HUMANA],
          "só autoria humana — o que a apuração conta desde a correcção")

    print("\n== Validação humana ==")
    cod = VALIDACAO = EXECUCAO / "validacao_humana"
    kappa = cod / "kappa.json"
    print(f"  kappa.json existe? {kappa.exists()}")
    import csv as _csv
    for nome in ("codificacao", "recodificacao"):
        caminho = VALIDACAO / f"{nome}.csv"
        if not caminho.exists():
            print(f"  {nome}.csv: NÃO EXISTE")
            continue
        with caminho.open(encoding="utf-8", newline="") as arquivo:
            linhas = list(_csv.DictReader(arquivo))
        preenchidas = sum(1 for ln in linhas if (ln.get("diretividade") or "").strip())
        print(f"  {nome}.csv: {len(linhas)} linhas · {preenchidas} com `diretividade` preenchida")

    print(f"\n{'TODAS AS VERIFICAÇÕES PASSAM' if not _falhas else 'DIVERGÊNCIAS: ' + '; '.join(_falhas)}")


if __name__ == "__main__":
    main()
