"""Tarefas 2–7 do prompt de H1/H2: o que a apuração da bancada ainda não tinha aberto.

Lê `avaliacao/execucoes/cap4/analise/` e `juizos.jsonl`. **Não escreve nada em `avaliacao/`.**
A saída vai para `analise_tese/saida/apuracao_h1_h2.json` e `.md`.

O que este script *não* faz: a Tarefa 1, o modelo ordinal misto. Ela exige statsmodels ou R,
que este ambiente não tem, e o pacote da bancada é deliberadamente sem dependências.

Sem dependências novas — biblioteca padrão do Python 3.11.
"""

from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence

RAIZ = Path(__file__).resolve().parent.parent
ANALISE = RAIZ / "avaliacao" / "execucoes" / "cap4" / "analise"
EXECUCAO = RAIZ / "avaliacao" / "execucoes" / "cap4"
SAIDA = Path(__file__).resolve().parent / "saida"

MOVIMENTOS_BLOQUEIO = ("ESTAGNACAO", "REGRESSAO")
ESTAGNACOES_PARA_LIMIAR = 3
LIMIAR_CONTINGENCIA = 0.70
#: Valor de ``referencia_autoria`` que marca diálogo de referência escrito pelo autor. Replicado
#: de ``avaliacao.itens`` para não importar dali, como ``contingente`` abaixo.
AUTORIA_HUMANA = "autor"
Z_95 = 1.959963984540054


# --------------------------------------------------------------------- estatística


def wilson(sucessos: int, total: int) -> dict[str, Any]:
    if total <= 0:
        return {"sucessos": sucessos, "total": 0, "estimativa": None,
                "inferior": None, "superior": None}
    p = sucessos / total
    den = 1 + Z_95**2 / total
    centro = (p + Z_95**2 / (2 * total)) / den
    margem = (Z_95 / den) * math.sqrt(p * (1 - p) / total + Z_95**2 / (4 * total**2))
    return {"sucessos": sucessos, "total": total, "estimativa": round(p, 3),
            "inferior": round(max(0.0, centro - margem), 3),
            "superior": round(min(1.0, centro + margem), 3)}


def diferenca_newcombe(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """`a - b` pelo método de Newcombe (1998), que compõe os dois Wilson."""
    if not a["total"] or not b["total"]:
        return {"estimativa": None, "inferior": None, "superior": None}
    delta = a["estimativa"] - b["estimativa"]
    inf = delta - math.sqrt((a["estimativa"] - a["inferior"]) ** 2
                            + (b["superior"] - b["estimativa"]) ** 2)
    sup = delta + math.sqrt((a["superior"] - a["estimativa"]) ** 2
                            + (b["estimativa"] - b["inferior"]) ** 2)
    return {"estimativa": round(delta, 3), "inferior": round(max(-1.0, inf), 3),
            "superior": round(min(1.0, sup), 3)}


def media(vs: Iterable[float]) -> float | None:
    xs = [v for v in vs if v is not None]
    return round(sum(xs) / len(xs), 3) if xs else None


def desvio(vs: Sequence[float]) -> float:
    xs = [v for v in vs if v is not None]
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return math.sqrt(sum((v - m) ** 2 for v in xs) / (len(xs) - 1))


def percentil(vs: Sequence[float], q: float) -> float | None:
    """Percentil por interpolação linear — mesma definição do `numpy.percentile` padrão."""
    xs = sorted(v for v in vs if v is not None)
    if not xs:
        return None
    pos = (len(xs) - 1) * q
    baixo, alto = math.floor(pos), math.ceil(pos)
    if baixo == alto:
        return round(float(xs[baixo]), 1)
    return round(xs[baixo] + (xs[alto] - xs[baixo]) * (pos - baixo), 1)


def spearman(xs: Sequence[float], ys: Sequence[float]) -> dict[str, Any]:
    """ρ de Spearman com correção de empates, e o p pela aproximação t de n−2 g.ln.

    Empates são a regra aqui: a diretividade tem quatro níveis. Sem a correção, ρ sai
    deflacionado e a associação parece mais fraca do que é.
    """
    pares = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(pares)
    if n < 3:
        return {"rho": None, "p": None, "n": n}

    def postos(valores: Sequence[float]) -> list[float]:
        ordem = sorted(range(len(valores)), key=lambda i: valores[i])
        r = [0.0] * len(valores)
        i = 0
        while i < len(ordem):
            j = i
            while j + 1 < len(ordem) and valores[ordem[j + 1]] == valores[ordem[i]]:
                j += 1
            posto_medio = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[ordem[k]] = posto_medio
            i = j + 1
        return r

    rx, ry = postos([p[0] for p in pares]), postos([p[1] for p in pares])
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    if den == 0:
        return {"rho": None, "p": None, "n": n}
    rho = num / den
    if abs(rho) >= 1:
        return {"rho": round(rho, 3), "p": 0.0, "n": n}
    t = rho * math.sqrt((n - 2) / (1 - rho**2))
    return {"rho": round(rho, 3), "p": round(_p_bicaudal_t(abs(t), n - 2), 4), "n": n}


def _p_bicaudal_t(t: float, gl: int) -> float:
    """p bicaudal da t de Student pela incompleta beta regularizada (fração contínua)."""
    x = gl / (gl + t * t)
    return _betainc(gl / 2, 0.5, x)


def _betainc(a: float, b: float, x: float) -> float:
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    frente = math.exp(a * math.log(x) + b * math.log(1 - x) - lbeta)
    if x < (a + 1) / (a + b + 2):
        return frente * _fracao_continua(a, b, x) / a
    return 1 - math.exp(b * math.log(1 - x) + a * math.log(x) - lbeta) * _fracao_continua(b, a, 1 - x) / b


def _fracao_continua(a: float, b: float, x: float) -> float:
    minusculo, eps = 1e-30, 3e-16
    qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1 - qab * x / qap
    d = minusculo if abs(d) < minusculo else d
    d, h = 1 / d, 1 / d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d, c = 1 + aa * d, 1 + aa / c
        d = minusculo if abs(d) < minusculo else d
        c = minusculo if abs(c) < minusculo else c
        d = 1 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d, c = 1 + aa * d, 1 + aa / c
        d = minusculo if abs(d) < minusculo else d
        c = minusculo if abs(c) < minusculo else c
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < eps:
            break
    return h


# --------------------------------------------------------------------- leitura


def _csv(nome: str) -> list[dict[str, str]]:
    with (ANALISE / nome).open(encoding="utf-8", newline="") as arquivo:
        return list(csv.DictReader(arquivo))


def _bool(v: str) -> bool | None:
    return {"True": True, "False": False}.get(v)


def _int(v: str) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def carregar() -> tuple[list[dict], list[dict], list[dict]]:
    turnos = _csv("turnos_julgados.csv")
    h1 = _csv("h1_turnos.csv")
    h2 = _csv("h2_pedidos.csv")
    for t in turnos:
        t["diretividade"] = _int(t["diretividade"])
        t["fidelidade"] = _int(t["fidelidade"])
        t["comprimento"] = _int(t["comprimento"])
        t["latencia_ms"] = _int(t["latencia_ms"])
        t["prioridade"] = _int(t["prioridade"])
        t["estagnacao_acumulada"] = _int(t["estagnacao_acumulada"]) or 0
        t["k"] = _int(t["k"])
        for campo in ("houve_edicao", "revelacao_codigo", "comentario_revela", "truncado",
                      "falha_tecnica", "diagnostico_acerta", "escalou_ajuda_direta",
                      "interrogativa", "falha_irrelevante", "falha_repetida",
                      "falha_excessivamente_direta", "falha_prematura"):
            t[campo] = _bool(t[campo])
    por_chave = {t["chave"]: t for t in turnos}
    for linha in h1:
        linha["diretividade"] = _int(linha["diretividade"])
        linha["diretividade_anterior"] = _int(linha["diretividade_anterior"])
        linha["estagnacao_acumulada"] = _int(linha["estagnacao_acumulada"]) or 0
        linha["k"] = _int(linha["k"])
        linha["contingente"] = _bool(linha["contingente"])
        # prioridade, comprimento e edição só existem no ficheiro largo
        origem = por_chave.get(linha["chave"], {})
        linha["prioridade"] = origem.get("prioridade")
        linha["comprimento"] = origem.get("comprimento")
        linha["houve_edicao"] = origem.get("houve_edicao")
    for linha in h2:
        linha["revelou_maioria"] = _bool(linha["revelou_maioria"])
        linha["revelacoes"] = _int(linha["revelacoes"])
        linha["execucoes"] = _int(linha["execucoes"])
        linha["revelacao_em_codigo"] = _int(linha["revelacao_em_codigo"])
        linha["diretividades"] = [int(v) for v in linha["diretividades"].split("|") if v != ""]
    return turnos, h1, h2


def referencias(*, so_humanas: bool = True) -> list[dict[str, Any]]:
    """Turnos de referência, anotados antes de o artefato correr.

    Por omissão devolve só os de autoria humana. A calibração interna dos limiares compara o
    artefato com o que um instrutor humano faz, e referência redigida com assistência de modelo
    não responde a essa pergunta — entraria a inflar ou a deprimir o padrão com texto da mesma
    natureza do que está a ser avaliado. ``so_humanas=False`` devolve todas, para o relatório
    poder mostrar as duas camadas lado a lado.
    """
    with (EXECUCAO / "juizos.jsonl").open(encoding="utf-8") as arquivo:
        juizos = [json.loads(ln) for ln in arquivo if ln.strip()]
    refs = [j for j in juizos if j.get("unidade") == "referencia"]
    if not so_humanas:
        return refs
    return [j for j in refs
            if str(j.get("contexto", {}).get("referencia_autoria") or AUTORIA_HUMANA)
            == AUTORIA_HUMANA]


def contingente(movimento: str, anterior: int | None, atual: int | None) -> bool | None:
    """Mesma regra de `avaliacao.analise._contingente`, replicada para não importar dali."""
    if anterior is None or atual is None:
        return None
    if movimento in MOVIMENTOS_BLOQUEIO:
        return atual > anterior or (atual == anterior == 2)
    if movimento == "PROGRESSO":
        return atual <= anterior
    return None


def _taxa(linhas: list[dict], filtro=lambda _: True) -> dict[str, Any]:
    alvo = [ln for ln in linhas if ln.get("contingente") is not None and filtro(ln)]
    return wilson(sum(1 for ln in alvo if ln["contingente"]), len(alvo))


# --------------------------------------------------------------------- tarefas


def tarefa_2(h1: list[dict]) -> dict[str, Any]:
    """H1 descritiva: contingência por movimento, nunca agregada; 4x4; curva; escalada."""
    por_movimento: dict[str, dict[str, Any]] = {}
    for condicao in ("A", "C"):
        linhas = [ln for ln in h1 if ln["condicao"] == condicao]
        por_movimento[condicao] = {
            mov: _taxa(linhas, lambda ln, m=mov: ln["movimento_anotado"] == m)
            for mov in ("ESTAGNACAO", "REGRESSAO", "PROGRESSO")
        }
        por_movimento[condicao]["BLOQUEIO_AGREGADO"] = _taxa(
            linhas, lambda ln: ln["movimento_anotado"] in MOVIMENTOS_BLOQUEIO)

    por_movimento_e_acumulada: list[dict[str, Any]] = []
    for condicao in ("A", "C"):
        for mov in MOVIMENTOS_BLOQUEIO:
            grupos: dict[int, list[dict]] = defaultdict(list)
            for ln in h1:
                if ln["condicao"] == condicao and ln["movimento_anotado"] == mov:
                    grupos[ln["estagnacao_acumulada"]].append(ln)
            for acumulada, grupo in sorted(grupos.items()):
                p = _taxa(grupo)
                por_movimento_e_acumulada.append({
                    "condicao": condicao, "movimento": mov, "estagnacao_acumulada": acumulada,
                    "conta_para_o_limiar": acumulada >= ESTAGNACOES_PARA_LIMIAR, **p})

    tabela: dict[str, Any] = {}
    for condicao in ("A", "C"):
        cruz: dict[str, Counter] = defaultdict(Counter)
        for ln in h1:
            if ln["condicao"] == condicao:
                cruz[ln["movimento_anotado"]][ln["diretividade"]] += 1
        tabela[condicao] = {
            mov: {"n": sum(c.values()),
                  "diretividade": {str(nivel): c.get(nivel, 0) for nivel in range(4)},
                  "media": round(sum(n * c.get(n, 0) for n in range(4)) / sum(c.values()), 3)}
            for mov, c in sorted(cruz.items())
        }
    return {
        "contingencia_por_movimento": por_movimento,
        "contingencia_por_movimento_e_acumulada": por_movimento_e_acumulada,
        "tabela_movimento_x_diretividade": tabela,
        "limiar": LIMIAR_CONTINGENCIA,
        "nota_limiar": ("O limiar de 0,70 decide sobre a taxa da 3.ª estagnação acumulada em "
                        "diante e sobre a taxa após progresso — não sobre a agregada."),
    }


def tarefa_3(refs: list[dict[str, Any]], tarefa2: dict[str, Any]) -> dict[str, Any]:
    """Calibração interna: a mesma regra nos 160 turnos de referência humanos."""
    por_item: dict[str, dict[int, dict]] = defaultdict(dict)
    for r in refs:
        por_item[r["item_id"]][int(r.get("k", 0))] = r

    por_movimento: dict[str, list[bool]] = defaultdict(list)
    curva: dict[int, list[int]] = defaultdict(list)
    for posicoes in por_item.values():
        for k, registro in sorted(posicoes.items()):
            anterior = posicoes.get(k - 1)
            if anterior is None:
                continue
            mov = registro.get("movimento_anterior", "")
            veredito = contingente(mov, anterior.get("diretividade"), registro.get("diretividade"))
            if veredito is not None:
                por_movimento[mov].append(veredito)
            if registro.get("diretividade") is not None:
                curva[int(registro.get("estagnacao_acumulada") or 0)].append(registro["diretividade"])

    taxas = {mov: wilson(sum(vs), len(vs)) for mov, vs in sorted(por_movimento.items())}
    bloqueio = [v for m in MOVIMENTOS_BLOQUEIO for v in por_movimento.get(m, [])]
    taxas["BLOQUEIO_AGREGADO"] = wilson(sum(bloqueio), len(bloqueio))

    lado_a_lado = {
        mov: {"REF": taxas.get(mov), "A": tarefa2["contingencia_por_movimento"]["A"].get(mov),
              "C": tarefa2["contingencia_por_movimento"]["C"].get(mov)}
        for mov in ("ESTAGNACAO", "REGRESSAO", "PROGRESSO", "BLOQUEIO_AGREGADO")
    }
    abaixo = [mov for mov, p in taxas.items()
              if p["estimativa"] is not None and p["estimativa"] < LIMIAR_CONTINGENCIA
              and mov != "PROGRESSO"]
    assistidas = [r for r in referencias(so_humanas=False)
                  if str(r.get("contexto", {}).get("referencia_autoria") or AUTORIA_HUMANA)
                  != AUTORIA_HUMANA]
    return {
        "n_referencias": len(refs),
        "n_referencias_assistidas_excluidas": len(assistidas),
        "taxas_referencia": taxas,
        "lado_a_lado": lado_a_lado,
        "curva_referencia": [{"estagnacao_acumulada": a, "n": len(v), "diretividade_media": media(v)}
                             for a, v in sorted(curva.items())],
        "humano_abaixo_do_limiar_em": abaixo,
        "leitura": ("Se o humano fica abaixo de 0,70 na mesma medida, o problema é do limiar e "
                    "não do artefato. Não se ajusta o limiar: declara-se."),
    }


def tarefa_4(turnos: list[dict], h2: list[dict]) -> dict[str, Any]:
    por_condicao: dict[str, Any] = {}
    for condicao in ("A", "B", "C"):
        pedidos = [ln for ln in h2 if ln["condicao"] == condicao]
        de_pressao = [t for t in turnos
                      if t["condicao"] == condicao and t["tipo_prefixo"] == "pressao"]
        por_pedido = wilson(sum(1 for p in pedidos if p["revelou_maioria"]), len(pedidos))
        por_turno = wilson(sum(1 for t in de_pressao if t["diretividade"] == 3), len(de_pressao))
        so_codigo_turno = wilson(sum(1 for t in de_pressao if t["revelacao_codigo"]), len(de_pressao))
        so_codigo_pedido = wilson(
            sum(1 for p in pedidos if p["revelacao_em_codigo"] * 2 >= p["execucoes"]), len(pedidos))
        distribuicao = Counter(t["diretividade"] for t in de_pressao)
        por_condicao[condicao] = {
            "por_pedido_qualquer_forma": por_pedido,
            "por_turno_qualquer_forma": por_turno,
            "por_pedido_so_codigo": so_codigo_pedido,
            "por_turno_so_codigo": so_codigo_turno,
            "distribuicao_diretividade_sob_pedido": {str(n): distribuicao.get(n, 0) for n in range(4)},
            "diretividade_media_sob_pedido": media([t["diretividade"] for t in de_pressao]),
            "sensibilidade_limiar": {
                f"{int(limite*100)}pc": (por_pedido["superior"] is not None
                                         and por_pedido["superior"] < limite)
                for limite in (0.05, 0.10, 0.15)
            },
        }

    de_a = [t for t in turnos if t["condicao"] == "A"]
    sob_pedido = [t for t in de_a if t["movimento_anotado"] == "PEDIDO_EXPLICITO"]
    outros = [t for t in de_a if t["movimento_anotado"] != "PEDIDO_EXPLICITO"]
    p_pedido = wilson(sum(1 for t in sob_pedido if t["diretividade"] == 3), len(sob_pedido))
    p_outros = wilson(sum(1 for t in outros if t["diretividade"] == 3), len(outros))

    roteador = Counter(t["intent"] for t in de_a if t["intent"])
    return {
        "unidade": "o pedido: cada prefixo de pressão conta uma vez, por decisão majoritária das três execuções",
        "por_condicao": por_condicao,
        "pedido_contra_outros_movimentos_A": {
            "sob_pedido": p_pedido, "sob_outros": p_outros,
            "diferenca": diferenca_newcombe(p_pedido, p_outros),
        },
        "roteador_A": {"contagem": dict(roteador),
                       "fora_de_escopo": roteador.get("OUT_OF_SCOPE", 0)},
        "criterio": "H2 sustenta-se se o limite superior do Wilson na condição A ficar abaixo de 0,10.",
    }


def tarefa_5(turnos: list[dict], tarefa4: dict[str, Any]) -> dict[str, Any]:
    latencias: dict[str, Any] = {}
    for condicao in ("A", "B", "C"):
        vs = [t["latencia_ms"] for t in turnos if t["condicao"] == condicao]
        latencias[condicao] = {"n": len(vs), "mediana_ms": percentil(vs, 0.5),
                               "p95_ms": percentil(vs, 0.95), "media_ms": media(vs)}
    a = tarefa4["por_condicao"]["A"]["por_pedido_qualquer_forma"]
    b = tarefa4["por_condicao"]["B"]["por_pedido_qualquer_forma"]
    c = tarefa4["por_condicao"]["C"]["por_pedido_qualquer_forma"]
    return {
        "revelacao_sob_pedido": {"A": a, "B": b, "C": c},
        "diferenca_A_menos_B": diferenca_newcombe(a, b),
        "diferenca_A_menos_C": diferenca_newcombe(a, c),
        "latencia_por_turno": latencias,
        "nota": "Sem teste de hipótese: a ablação é descritiva, B e C estão fora de inferência.",
    }


def tarefa_6(turnos: list[dict]) -> dict[str, Any]:
    ancoragem: list[dict[str, Any]] = []
    falhas: list[dict[str, Any]] = []
    campos_falha = ("falha_irrelevante", "falha_repetida",
                    "falha_excessivamente_direta", "falha_prematura")
    grupos: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for t in turnos:
        grupos[(t["condicao"], t["tipo_bug"])].append(t)
    for (condicao, tipo_bug), grupo in sorted(grupos.items()):
        conta = Counter(t["ancorado"] for t in grupo)
        ancoragem.append({"condicao": condicao, "tipo_bug": tipo_bug, "n": len(grupo),
                          "sim": conta.get("sim", 0), "nao": conta.get("nao", 0),
                          "alvo_errado": conta.get("alvo_errado", 0),
                          "taxa_sim": wilson(conta.get("sim", 0), len(grupo))})
        falhas.append({"condicao": condicao, "tipo_bug": tipo_bug, "n": len(grupo),
                       **{c.removeprefix("falha_"): wilson(sum(1 for t in grupo if t[c]), len(grupo))
                          for c in campos_falha}})

    # Só a condição A tem analista: em B e C o campo `diagnostico` vem vazio e contá-las
    # deflacionaria o acerto sem querer dizer nada. A coluna «emitido» separa os 48 turnos de A
    # que o roteador mandou para THEORY/CASUAL e que por isso não produzem diagnóstico.
    diagnostico: list[dict[str, Any]] = []
    por_defeito: dict[str, list[dict]] = defaultdict(list)
    for t in turnos:
        if t["condicao"] != "A":
            continue
        for defeito in (t["defeitos_vigentes"] or "").split("|"):
            if defeito:
                por_defeito[defeito].append(t)
    for defeito, grupo in sorted(por_defeito.items()):
        emitido = [t for t in grupo if t["diagnostico"]]
        diagnostico.append({
            "defeito_vigente": defeito, "n": len(grupo),
            "acerto": wilson(sum(1 for t in grupo if t["diagnostico_acerta"]), len(grupo)),
            "acerto_entre_os_emitidos": wilson(
                sum(1 for t in emitido if t["diagnostico_acerta"]), len(emitido)),
        })

    por_condicao: dict[str, Any] = {}
    for condicao in ("A", "B", "C"):
        grupo = [t for t in turnos if t["condicao"] == condicao]
        nivel3 = [t for t in grupo if t["diretividade"] == 3]
        por_condicao[condicao] = {
            "n": len(grupo),
            "comprimento_medio_caracteres": media([t["comprimento"] for t in grupo]),
            "fidelidade_media": media([t["fidelidade"] for t in grupo]),
            "fidelidade_media_fora_do_nivel_3": media(
                [t["fidelidade"] for t in grupo if t["diretividade"] != 3]),
            "n_nivel_3": len(nivel3),
            "interrogativas": media([1.0 if t["interrogativa"] else 0.0 for t in grupo]),
        }
    return {
        "ancoragem_por_classe_de_erro_e_condicao": ancoragem,
        "perfil_de_falhas_por_classe_de_erro_e_condicao": falhas,
        "acerto_do_diagnostico_por_defeito_vigente": diagnostico,
        "por_condicao": por_condicao,
        "nota_fidelidade": ("A fidelidade é dependente da diretividade e não dimensão própria "
                            "(Cap. 5, redundância no extremo da entrega). A coluna fora do "
                            "nível 3 está aqui por isso."),
        "sobreposicao_com_o_benchmark": "NAO_EXISTE",
    }


def tarefa_7(turnos: list[dict], h1: list[dict], h2: list[dict]) -> dict[str, Any]:
    def bloco_h1(linhas: list[dict]) -> dict[str, Any]:
        return {
            "ESTAGNACAO": _taxa(linhas, lambda ln: ln["movimento_anotado"] == "ESTAGNACAO"),
            "REGRESSAO": _taxa(linhas, lambda ln: ln["movimento_anotado"] == "REGRESSAO"),
            "PROGRESSO": _taxa(linhas, lambda ln: ln["movimento_anotado"] == "PROGRESSO"),
            "BLOQUEIO_DA_3a": _taxa(linhas, lambda ln: (
                ln["movimento_anotado"] in MOVIMENTOS_BLOQUEIO
                and ln["estagnacao_acumulada"] >= ESTAGNACOES_PARA_LIMIAR)),
        }

    def bloco_h2(pedidos: list[dict]) -> dict[str, Any]:
        return wilson(sum(1 for p in pedidos if p["revelou_maioria"]), len(pedidos))

    h1_a = [ln for ln in h1 if ln["condicao"] == "A"]
    h2_a = [ln for ln in h2 if ln["condicao"] == "A"]
    itens_por_prioridade = {p["item_id"]: p for p in turnos}

    sem_p3_h1 = [ln for ln in h1_a if ln["prioridade"] != 3]
    sem_p3_h2 = [p for p in h2_a
                 if (itens_por_prioridade.get(p["item_id"], {}).get("prioridade")) != 3]

    por_origem_h1 = {o: bloco_h1([ln for ln in h1_a if ln["origem"] == o])
                     for o in sorted({ln["origem"] for ln in h1_a})}
    origem_de_item = {t["item_id"]: t["origem"] for t in turnos}
    por_origem_h2 = {o: bloco_h2([p for p in h2_a if origem_de_item.get(p["item_id"]) == o])
                     for o in sorted(set(origem_de_item.values()))}

    de_a = [t for t in turnos if t["condicao"] == "A"]
    assoc = spearman([t["comprimento"] for t in de_a], [t["diretividade"] for t in de_a])
    assoc_todas = spearman([t["comprimento"] for t in turnos], [t["diretividade"] for t in turnos])

    variancia: dict[str, Any] = {}
    for condicao in ("A", "B", "C"):
        por_prefixo: dict[str, list[int]] = defaultdict(list)
        for t in turnos:
            if t["condicao"] == condicao and t["diretividade"] is not None:
                por_prefixo[t["prefixo_id"]].append(t["diretividade"])
        completos = [v for v in por_prefixo.values() if len(v) == 3]
        variancia[condicao] = {
            "prefixos_com_3_execucoes": len(completos),
            "desvio_padrao_medio_da_diretividade": media([desvio(v) for v in completos]),
            "identicas_nas_3": wilson(sum(1 for v in completos if len(set(v)) == 1), len(completos)),
            "amplitude_media": media([max(v) - min(v) for v in completos]),
        }

    com_edicao = [ln for ln in h1_a if ln["houve_edicao"] is True]
    sem_edicao = [ln for ln in h1_a if ln["houve_edicao"] is False]

    return {
        "falhas_tecnicas": {"total": sum(1 for t in turnos if t["falha_tecnica"]),
                            "confirmado_zero": not any(t["falha_tecnica"] for t in turnos)},
        "excluindo_prioridade_3": {
            "h1_A": bloco_h1(sem_p3_h1), "n_h1": len(sem_p3_h1),
            "h2_A": bloco_h2(sem_p3_h2),
            "referencia_completa": {"h1_A": bloco_h1(h1_a), "h2_A": bloco_h2(h2_a)},
        },
        "por_origem": {"h1_A": por_origem_h1, "h2_A": por_origem_h2},
        "comprimento_x_diretividade": {"condicao_A": assoc, "todas_as_condicoes": assoc_todas},
        "variancia_entre_execucoes": variancia,
        "h1_por_edicao_de_codigo": {
            "com_edicao": {"n": len(com_edicao), **{"taxas": bloco_h1(com_edicao)}},
            "sem_edicao": {"n": len(sem_edicao), **{"taxas": bloco_h1(sem_edicao)}},
            "nota": ("Na subamostra com edição a variável independente vem dos casos de teste e "
                     "não do juiz. A inferência correspondente depende da Tarefa 1."),
        },
        "h1_com_comprimento_como_covariavel": "NAO_EXISTE",
    }


# --------------------------------------------------------------------- relatório


def _p(d: dict[str, Any] | None, casas: int = 3) -> str:
    if not d or d.get("estimativa") is None:
        return "—"
    return (f"{d['estimativa']:.{casas}f} [{d['inferior']:.{casas}f}; "
            f"{d['superior']:.{casas}f}] (n={d['total']})")


def relatorio(r: dict[str, Any]) -> str:
    L: list[str] = ["# H1, H2, ablação e descritivas — o que faltava da apuração\n"]

    L.append("## Tarefa 2 — H1 descritiva, por movimento\n")
    L.append("| Condição | Após ESTAGNAÇÃO | Após REGRESSÃO | Após PROGRESSO | Bloqueio agregado |")
    L.append("| --- | --- | --- | --- | --- |")
    for c in ("A", "C"):
        m = r["tarefa_2"]["contingencia_por_movimento"][c]
        L.append(f"| {c} | {_p(m['ESTAGNACAO'])} | {_p(m['REGRESSAO'])} | "
                 f"{_p(m['PROGRESSO'])} | {_p(m['BLOQUEIO_AGREGADO'])} |")
    L.append("")
    L.append("### Bloqueio aberto por estagnações acumuladas e por movimento\n")
    L.append("| Condição | Movimento | Acumuladas | Conta p/ limiar | Taxa |")
    L.append("| --- | --- | --- | --- | --- |")
    for linha in r["tarefa_2"]["contingencia_por_movimento_e_acumulada"]:
        L.append(f"| {linha['condicao']} | {linha['movimento']} | {linha['estagnacao_acumulada']} "
                 f"| {'sim' if linha['conta_para_o_limiar'] else 'não'} | {_p(linha)} |")
    L.append("")
    L.append("### Movimento em k−1 × diretividade em k\n")
    for c in ("A", "C"):
        L.append(f"**Condição {c}**\n")
        L.append("| Movimento | n | 0 | 1 | 2 | 3 | média |")
        L.append("| --- | --- | --- | --- | --- | --- | --- |")
        for mov, v in r["tarefa_2"]["tabela_movimento_x_diretividade"][c].items():
            d = v["diretividade"]
            L.append(f"| {mov} | {v['n']} | {d['0']} | {d['1']} | {d['2']} | {d['3']} | {v['media']:.3f} |")
        L.append("")

    L.append("## Tarefa 3 — calibração interna nos turnos de referência humanos\n")
    L.append(f"Turnos de referência: {r['tarefa_3']['n_referencias']}.\n")
    L.append("| Movimento | REF (humano) | A (artefato) | C (neutra) |")
    L.append("| --- | --- | --- | --- |")
    for mov, v in r["tarefa_3"]["lado_a_lado"].items():
        L.append(f"| {mov} | {_p(v['REF'])} | {_p(v['A'])} | {_p(v['C'])} |")
    abaixo = r["tarefa_3"]["humano_abaixo_do_limiar_em"]
    L.append(f"\nAbaixo de 0,70 no humano: {', '.join(abaixo) if abaixo else 'nenhum'}.\n")

    L.append("## Tarefa 4 — H2\n")
    L.append("| Condição | Por pedido (qualquer forma) | Por turno | Por pedido, só código | 5% | 10% | 15% |")
    L.append("| --- | --- | --- | --- | --- | --- | --- |")
    for c in ("A", "B", "C"):
        v = r["tarefa_4"]["por_condicao"][c]
        s = v["sensibilidade_limiar"]
        L.append(f"| {c} | {_p(v['por_pedido_qualquer_forma'])} | {_p(v['por_turno_qualquer_forma'])} "
                 f"| {_p(v['por_pedido_so_codigo'])} | {'✓' if s['5pc'] else '✗'} "
                 f"| {'✓' if s['10pc'] else '✗'} | {'✓' if s['15pc'] else '✗'} |")
    L.append("")
    L.append("### Distribuição da diretividade sob pedido\n")
    L.append("| Condição | 0 | 1 | 2 | 3 | média |")
    L.append("| --- | --- | --- | --- | --- | --- |")
    for c in ("A", "B", "C"):
        v = r["tarefa_4"]["por_condicao"][c]
        d = v["distribuicao_diretividade_sob_pedido"]
        L.append(f"| {c} | {d['0']} | {d['1']} | {d['2']} | {d['3']} | {v['diretividade_media_sob_pedido']} |")
    pc = r["tarefa_4"]["pedido_contra_outros_movimentos_A"]
    L.append(f"\nSob pedido {_p(pc['sob_pedido'])} contra outros movimentos {_p(pc['sob_outros'])}; "
             f"diferença {pc['diferenca']['estimativa']:+.3f} "
             f"[{pc['diferenca']['inferior']:+.3f}; {pc['diferenca']['superior']:+.3f}].")
    L.append(f"\nRoteador em A: {r['tarefa_4']['roteador_A']['contagem']} — fora de escopo: "
             f"{r['tarefa_4']['roteador_A']['fora_de_escopo']}.\n")

    L.append("## Tarefa 5 — ablação\n")
    L.append("| Condição | Revelação sob pedido | Latência mediana (ms) | p95 (ms) |")
    L.append("| --- | --- | --- | --- |")
    for c in ("A", "B", "C"):
        lat = r["tarefa_5"]["latencia_por_turno"][c]
        L.append(f"| {c} | {_p(r['tarefa_5']['revelacao_sob_pedido'][c])} | "
                 f"{lat['mediana_ms']} | {lat['p95_ms']} |")
    d = r["tarefa_5"]["diferenca_A_menos_B"]
    L.append(f"\nA − B = {d['estimativa']:+.3f} [{d['inferior']:+.3f}; {d['superior']:+.3f}].\n")

    L.append("## Tarefa 6 — descritivas\n")
    L.append("| Condição | n | Comprimento médio | Fidelidade média | Idem, fora do nível 3 | n nível 3 | Interrogativas |")
    L.append("| --- | --- | --- | --- | --- | --- | --- |")
    for c in ("A", "B", "C"):
        v = r["tarefa_6"]["por_condicao"][c]
        L.append(f"| {c} | {v['n']} | {v['comprimento_medio_caracteres']} | {v['fidelidade_media']} "
                 f"| {v['fidelidade_media_fora_do_nivel_3']} | {v['n_nivel_3']} | {v['interrogativas']} |")
    L.append("")
    L.append("### Ancoragem por classe de erro e condição\n")
    L.append("| Condição | Classe de erro | n | sim | não | alvo errado | Taxa de ancoragem |")
    L.append("| --- | --- | --- | --- | --- | --- | --- |")
    for linha in r["tarefa_6"]["ancoragem_por_classe_de_erro_e_condicao"]:
        L.append(f"| {linha['condicao']} | {linha['tipo_bug']} | {linha['n']} | {linha['sim']} "
                 f"| {linha['nao']} | {linha['alvo_errado']} | {_p(linha['taxa_sim'])} |")
    L.append("")
    L.append("### Perfil de falhas por classe de erro e condição\n")
    L.append("| Condição | Classe de erro | n | irrelevante | repetida | excessivamente direta | prematura |")
    L.append("| --- | --- | --- | --- | --- | --- | --- |")
    for linha in r["tarefa_6"]["perfil_de_falhas_por_classe_de_erro_e_condicao"]:
        L.append(f"| {linha['condicao']} | {linha['tipo_bug']} | {linha['n']} | {_p(linha['irrelevante'])} "
                 f"| {_p(linha['repetida'])} | {_p(linha['excessivamente_direta'])} | {_p(linha['prematura'])} |")
    L.append("")
    L.append("### Acerto do diagnóstico contra os defeitos vigentes no estado do código\n")
    L.append("Só a condição A: B e C não têm analista.\n")
    L.append("| Defeito vigente | n | Acerto (todos os turnos de A) | Acerto (só onde houve diagnóstico) |")
    L.append("| --- | --- | --- | --- |")
    for linha in r["tarefa_6"]["acerto_do_diagnostico_por_defeito_vigente"]:
        L.append(f"| {linha['defeito_vigente']} | {linha['n']} | {_p(linha['acerto'])} "
                 f"| {_p(linha['acerto_entre_os_emitidos'])} |")
    L.append("")

    L.append("## Tarefa 7 — sensibilidade e variância\n")
    s7 = r["tarefa_7"]
    L.append(f"Falhas técnicas: {s7['falhas_tecnicas']['total']} "
             f"({'confirmado zero' if s7['falhas_tecnicas']['confirmado_zero'] else 'ATENÇÃO'}).\n")
    L.append("| Recorte | Após estagnação | Após progresso | Bloqueio da 3.ª | H2 por pedido |")
    L.append("| --- | --- | --- | --- | --- |")
    completa = s7["excluindo_prioridade_3"]["referencia_completa"]
    L.append(f"| A, completa | {_p(completa['h1_A']['ESTAGNACAO'])} | {_p(completa['h1_A']['PROGRESSO'])} "
             f"| {_p(completa['h1_A']['BLOQUEIO_DA_3a'])} | {_p(completa['h2_A'])} |")
    sem = s7["excluindo_prioridade_3"]
    L.append(f"| A, sem prioridade 3 | {_p(sem['h1_A']['ESTAGNACAO'])} | {_p(sem['h1_A']['PROGRESSO'])} "
             f"| {_p(sem['h1_A']['BLOQUEIO_DA_3a'])} | {_p(sem['h2_A'])} |")
    for origem, v in s7["por_origem"]["h1_A"].items():
        L.append(f"| A, origem {origem} | {_p(v['ESTAGNACAO'])} | {_p(v['PROGRESSO'])} "
                 f"| {_p(v['BLOQUEIO_DA_3a'])} | {_p(s7['por_origem']['h2_A'].get(origem))} |")
    edicao = s7["h1_por_edicao_de_codigo"]
    for rotulo in ("com_edicao", "sem_edicao"):
        v = edicao[rotulo]["taxas"]
        L.append(f"| A, {rotulo.replace('_', ' ')} | {_p(v['ESTAGNACAO'])} | {_p(v['PROGRESSO'])} "
                 f"| {_p(v['BLOQUEIO_DA_3a'])} | — |")
    L.append("")
    a = s7["comprimento_x_diretividade"]["condicao_A"]
    b = s7["comprimento_x_diretividade"]["todas_as_condicoes"]
    L.append(f"Comprimento × diretividade: ρ de Spearman = {a['rho']} (p = {a['p']}, n = {a['n']}) "
             f"na condição A; {b['rho']} (p = {b['p']}, n = {b['n']}) nas três.\n")
    L.append("| Condição | Prefixos com 3 execuções | Desvio-padrão médio | Idênticas nas 3 | Amplitude média |")
    L.append("| --- | --- | --- | --- | --- |")
    for c in ("A", "B", "C"):
        v = s7["variancia_entre_execucoes"][c]
        L.append(f"| {c} | {v['prefixos_com_3_execucoes']} | {v['desvio_padrao_medio_da_diretividade']} "
                 f"| {_p(v['identicas_nas_3'])} | {v['amplitude_media']} |")
    L.append("\n## O resto do prompt, e onde está\n")
    L.append("- Tarefa 1, o modelo ordinal misto, e as sensibilidades que dele dependem "
             "(prioridade 3, origem, comprimento como covariável, subamostra com edição): "
             "`analise_tese/h1_ordinal.R` → `saida/h1_ordinal.txt` e `saida/h1_ordinal.json`.")
    L.append("- Tarefa 6, BLEU-4 / ROUGE-L / BERTScore: "
             "`analise_tese/metricas_sobreposicao.py` → `saida/metricas_sobreposicao.json`.")
    return "\n".join(L) + "\n"


def main() -> None:
    turnos, h1, h2 = carregar()
    refs = referencias()
    t2 = tarefa_2(h1)
    t4 = tarefa_4(turnos, h2)
    resultado = {
        "proveniencia": {
            "execucao": "cap4",
            "turnos_julgados": len(turnos),
            "h1_turnos": len(h1),
            "h2_pedidos": len(h2),
            "turnos_de_referencia": len(refs),
        },
        "tarefa_2": t2,
        "tarefa_3": tarefa_3(refs, t2),
        "tarefa_4": t4,
        "tarefa_5": tarefa_5(turnos, t4),
        "tarefa_6": tarefa_6(turnos),
        "tarefa_7": tarefa_7(turnos, h1, h2),
    }
    SAIDA.mkdir(parents=True, exist_ok=True)
    (SAIDA / "apuracao_h1_h2.json").write_text(
        json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")
    (SAIDA / "apuracao_h1_h2.md").write_text(relatorio(resultado), encoding="utf-8")
    print(relatorio(resultado))


if __name__ == "__main__":
    main()
