"""Análise da bancada: H1, H2, calibração interna e descritivas (Subseção 4.3.5).

Junta três fontes por turno — a resposta registrada, o veredito do juiz e o detector objetivo de
revelação — e produz o conjunto de dados da análise (``turnos_julgados.csv``), as tabelas do
Capítulo 5 e um resumo legível com o veredito de cada hipótese contra os limiares fixados antes
dos dados (contingência ≥ 0,70; limite superior da revelação sob pedido < 0,10).

A diretividade final de um turno é 3 quando o detector objetivo dispara; caso contrário, é a do
juiz. A inferência principal de H1 (modelo ordinal misto) roda fora daqui, sobre o CSV exportado.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from avaliacao import detector
from avaliacao.estatistica import Proporcao, media, mediana, wilson
from avaliacao.itens import expandir_prefixos
from avaliacao.executor import ARQUIVO_TURNOS
from avaliacao.julgamento import ARQUIVO_JUIZOS
from avaliacao.juiz import familia_distinta
from avaliacao.registro import escrever_json, ler_json, ler_ndjson

LIMIAR_CONTINGENCIA = 0.70
LIMIAR_REVELACAO = 0.10
LIMIARES_SENSIBILIDADE = (0.05, 0.10, 0.15)

#: Mapeamento fixado antes dos dados entre a classe do item e o rótulo do analista.
DIAGNOSTICO_ACEITO: dict[str, set[str]] = {
    "sintaxe": {"syntax", "undeclared_identifier"},
    "tipo": {"type_mismatch"},
    "laco_infinito": {"infinite_loop"},
    "logica": {"logic"},
    "limite": {"logic"},
    "fluxo_dados": {"logic"},
}

MOVIMENTOS_BLOQUEIO = ("ESTAGNACAO", "REGRESSAO")

#: Estagnação "persistente": a política sustenta o nível nos dois primeiros turnos bloqueados
#: por projeto, e é a partir daí que a expectativa de escalada vale (Subseção 4.3.5).
MINIMO_ESTAGNACOES = 2


def analisar(
    diretorio: Path, itens: list[dict[str, Any]], *, juiz_modelo: str = ""
) -> dict[str, Any]:
    por_id = {item["id"]: item for item in itens}
    registros = list(ler_ndjson(diretorio / ARQUIVO_JUIZOS))
    procedencia = _procedencia_do_juiz(diretorio, registros, juiz_modelo)
    juizos = {
        j["chave"]: j
        for j in registros
        if not procedencia["modelo"] or j.get("juiz_modelo", procedencia["modelo"]) == procedencia["modelo"]
    }
    procedencia["juizos_usados"] = len(juizos)
    turnos = list(ler_ndjson(diretorio / ARQUIVO_TURNOS))
    prefixos = {p.id: p for item in itens for p in expandir_prefixos(item)}
    linhas = [_linha(turno, juizos, por_id, prefixos) for turno in turnos]

    saida = diretorio / "analise"
    saida.mkdir(parents=True, exist_ok=True)
    _escrever_csv(saida / "turnos_julgados.csv", linhas)

    h1 = _h1(linhas, juizos, por_id, saida)
    h2 = _h2(linhas, saida)
    descritivas = _descritivas(linhas, saida)
    banco = _tabela_banco(itens, linhas, saida)

    resumo = {
        "juiz": procedencia,
        "banco": banco,
        "h1": h1,
        "h2": h2,
        "descritivas": descritivas,
    }
    escrever_json(saida / "resumo.json", resumo)
    (saida / "resumo.md").write_text(_resumo_markdown(resumo), encoding="utf-8")
    return resumo


# --------------------------------------------------------------------------- montagem das linhas


def _procedencia_do_juiz(
    diretorio: Path, registros: list[dict[str, Any]], escolhido: str
) -> dict[str, Any]:
    """Qual juiz sustenta esta análise — e se ele satisfaz o requisito de família do protocolo.

    Um arquivo de juízos pode ter mais de um modelo (ensaio barato e depois o do protocolo). A
    análise usa **um** deles: o pedido, o do manifesto ou o do registro mais recente.
    """
    modelos = [r.get("juiz_modelo", "") for r in registros if r.get("juiz_modelo")]
    manifesto = ler_json(diretorio / "manifesto.json")
    modelo = escolhido or manifesto.get("juiz_modelo", "") or (modelos[-1] if modelos else "")
    modelo_tutor = manifesto.get("modelo_base", "")
    return {
        "modelo": modelo,
        "transporte": manifesto.get("juiz_transporte", ""),
        "modelo_tutor": modelo_tutor,
        "familia_distinta": familia_distinta(modelo, modelo_tutor) if modelo and modelo_tutor else None,
        "outros_no_arquivo": sorted({m for m in modelos if m != modelo}),
    }


def _linha(
    turno: dict[str, Any],
    juizos: dict[str, Any],
    por_id: dict[str, Any],
    prefixos: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item = por_id.get(turno.get("item_id"), {})
    juizo = juizos.get(turno.get("chave", "")) or {}
    prefixo = (prefixos or {}).get(turno.get("prefixo_id", ""))
    marca = detector.detectar(
        turno.get("message", ""),
        item.get("fix_patterns", []),
        turno.get("actions") or [],
        codigo_vigente=prefixo.code if prefixo else str(turno.get("code", "")),
    )
    diretividade_juiz = juizo.get("diretividade")
    diretividade = 3 if marca.revelacao_codigo else diretividade_juiz
    diagnostico = (turno.get("diagnosis") or {}).get("errorType", "")
    falhas = juizo.get("falhas") or {}
    mensagem = turno.get("message", "") or ""

    return {
        "chave": turno.get("chave", ""),
        "prefixo_id": turno.get("prefixo_id", ""),
        "item_id": turno.get("item_id", ""),
        "origem": turno.get("origem", ""),
        "tipo_bug": turno.get("tipo_bug", ""),
        "prioridade": turno.get("prioridade", 0),
        "condicao": turno.get("condicao", ""),
        "execucao": turno.get("execucao", 0),
        "k": turno.get("k", 0),
        "tipo_prefixo": turno.get("tipo_prefixo", ""),
        "posicao_pressao": turno.get("posicao_pressao", ""),
        "movimento_anotado": turno.get("movimento_anterior", ""),
        "movimento_juiz": juizo.get("movimento_estudante", ""),
        "movimento_runtime": turno.get("movimento_runtime", ""),
        "estagnacao_acumulada": turno.get("estagnacao_acumulada", 0),
        "diretividade": diretividade,
        "diretividade_juiz": diretividade_juiz,
        "revelacao_codigo": marca.revelacao_codigo,
        "comentario_revela": marca.comentario_revela,
        "escalou_ajuda_direta": marca.escalou_ajuda_direta,
        "fidelidade": juizo.get("fidelidade"),
        "falha_irrelevante": bool(falhas.get("irrelevante")),
        "falha_repetida": bool(falhas.get("repetida")),
        "falha_excessivamente_direta": bool(falhas.get("excessivamente_direta")),
        "falha_prematura": bool(falhas.get("prematura")),
        "ancorado": juizo.get("ancorado", ""),
        "intent": turno.get("intent", ""),
        "diagnostico": diagnostico,
        "diagnostico_acerta": diagnostico in DIAGNOSTICO_ACEITO.get(turno.get("tipo_bug", ""), set()),
        "interrogativa": "?" in mensagem,
        "comprimento": len(mensagem),
        "latencia_ms": turno.get("latencia_ms", 0),
        "modelo": turno.get("modelo", ""),
        "truncado": turno.get("finish_reason", "") == "length",
        "falha_tecnica": bool(turno.get("falha_tecnica")),
        "julgado": diretividade is not None,
        "justificativa_juiz": juizo.get("justificativa", ""),
    }


def _validos(linhas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fora do denominador: falhas técnicas e turnos ainda sem juízo."""
    return [linha for linha in linhas if not linha["falha_tecnica"] and linha["diretividade"] is not None]


# --------------------------------------------------------------------------- H1


def _h1(
    linhas: list[dict[str, Any]],
    juizos: dict[str, Any],
    por_id: dict[str, Any],
    saida: Path,
) -> dict[str, Any]:
    elegiveis = [linha for linha in _validos(linhas)
        if linha["tipo_prefixo"] == "ouro"
        and linha["k"] >= 2
        and linha["movimento_anotado"] in MOVIMENTOS_BLOQUEIO + ("PROGRESSO",)
    ]
    for linha in elegiveis:
        anterior = juizos.get(f"{linha['item_id']}::k{linha['k'] - 1}::referencia") or {}
        linha["diretividade_anterior"] = anterior.get("diretividade")
        linha["contingente"] = _contingente(
            linha["movimento_anotado"], linha["diretividade_anterior"], linha["diretividade"]
        )

    taxas: dict[str, dict[str, Proporcao]] = {}
    for condicao in sorted({linha["condicao"] for linha in elegiveis}):
        do_grupo = [linha for linha in elegiveis if linha["condicao"] == condicao]
        taxas[condicao] = {
            "apos_bloqueio": _taxa(do_grupo, MOVIMENTOS_BLOQUEIO),
            "apos_progresso": _taxa(do_grupo, ("PROGRESSO",)),
        }
    taxas["REF"] = _taxas_referencia(juizos, por_id)

    curva = _curva_estagnacao(_validos(linhas))
    _escrever_csv(saida / "h1_contingencia.csv", _linhas_contingencia(taxas))
    _escrever_csv(saida / "h1_curva.csv", curva)
    _escrever_csv(
        saida / "h1_turnos.csv",
        [
            {
                chave: linha.get(chave)
                for chave in (
                    "chave", "item_id", "prefixo_id", "condicao", "execucao", "k",
                    "movimento_anotado", "estagnacao_acumulada", "diretividade",
                    "diretividade_anterior", "contingente", "tipo_bug", "origem",
                )
            }
            for linha in elegiveis
        ],
    )
    _tabela_h1_tex(taxas, saida)

    escalada = _escalada_sob_estagnacao(_validos(linhas))
    return {
        "taxas": {
            condicao: {nome: _proporcao_dict(p) for nome, p in valores.items()}
            for condicao, valores in taxas.items()
        },
        "curva": curva,
        "escalada_sob_estagnacao": escalada,
        "n_elegiveis": len(elegiveis),
        "sustentada_descritivamente": all(
            (taxas.get("A", {}).get(nome) or wilson(0, 0)).estimativa >= LIMIAR_CONTINGENCIA
            for nome in ("apos_bloqueio", "apos_progresso")
        ),
    }


def _contingente(movimento: str, anterior: int | None, atual: int | None) -> bool | None:
    if anterior is None or atual is None:
        return None
    if movimento in MOVIMENTOS_BLOQUEIO:
        # Manter o nível 2 conta como contingente: subir seria a revelação que H2 proíbe.
        return atual > anterior or (atual == anterior == 2)
    if movimento == "PROGRESSO":
        return atual <= anterior
    return None


def _taxa(linhas: list[dict[str, Any]], movimentos: tuple[str, ...]) -> Proporcao:
    alvo = [linha for linha in linhas if linha["movimento_anotado"] in movimentos and linha.get("contingente") is not None]
    return wilson(sum(1 for linha in alvo if linha["contingente"]), len(alvo))


def _taxas_referencia(juizos: dict[str, Any], por_id: dict[str, Any]) -> dict[str, Proporcao]:
    """Calibração interna: a mesma regra aplicada aos turnos de referência humanos do banco."""
    registros = [j for j in juizos.values() if j.get("unidade") == "referencia"]
    por_item: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
    for registro in registros:
        por_item[registro["item_id"]][int(registro.get("k", 0))] = registro

    bloqueio: list[bool] = []
    progresso: list[bool] = []
    for item_id, posicoes in por_item.items():
        for k, registro in sorted(posicoes.items()):
            anterior = posicoes.get(k - 1)
            if anterior is None:
                continue
            veredito = _contingente(
                registro.get("movimento_anterior", ""),
                anterior.get("diretividade"),
                registro.get("diretividade"),
            )
            if veredito is None:
                continue
            if registro.get("movimento_anterior") in MOVIMENTOS_BLOQUEIO:
                bloqueio.append(veredito)
            else:
                progresso.append(veredito)
    return {
        "apos_bloqueio": wilson(sum(bloqueio), len(bloqueio)),
        "apos_progresso": wilson(sum(progresso), len(progresso)),
    }


def _curva_estagnacao(linhas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Figura principal: diretividade média contra estagnações consecutivas."""
    agrupado: dict[tuple[str, int], list[int]] = defaultdict(list)
    for linha in linhas:
        if linha["tipo_prefixo"] != "ouro":
            continue
        agrupado[(linha["condicao"], int(linha["estagnacao_acumulada"]))].append(linha["diretividade"])
    return [
        {
            "condicao": condicao,
            "estagnacao_acumulada": acumulada,
            "n": len(valores),
            "diretividade_media": round(media(valores), 3),
        }
        for (condicao, acumulada), valores in sorted(agrupado.items())
    ]


def _escalada_sob_estagnacao(
    linhas: list[dict[str, Any]], *, minimo_estagnacoes: int = MINIMO_ESTAGNACOES
) -> dict[str, Any]:
    """Posição em que a diretividade atinge o nível 2 sob estagnação **persistente**.

    Duas correções contra a leitura otimista. Primeira: só entram trajetórias efetivamente
    bloqueadas, com ao menos ``minimo_estagnacoes`` turnos acumulados desde o último progresso —
    a política sustenta o nível nos dois primeiros por projeto, e contar essas posições puxaria
    a mediana para baixo justamente onde a tese prevê o 4.º–5.º turno. Segunda: quem nunca
    atinge o nível 2 não desaparece; fica no denominador e é reportado em ``nunca_atinge_2``,
    porque descartá-lo é censurar o caso desfavorável.
    """
    trajetorias: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for linha in linhas:
        if linha["condicao"] != "A" or linha["movimento_anotado"] not in MOVIMENTOS_BLOQUEIO:
            continue
        # Em bancada a trajetória é o item; em uso real, a sessão.
        trajetorias[(linha["item_id"], int(linha["execucao"]))].append(linha)

    posicoes: list[int] = []
    nunca = 0
    elegiveis = 0
    for turnos in trajetorias.values():
        if max(int(t["estagnacao_acumulada"]) for t in turnos) < minimo_estagnacoes:
            continue
        elegiveis += 1
        atingiram = [
            int(t["k"]) for t in turnos if t["diretividade"] is not None and t["diretividade"] >= 2
        ]
        if atingiram:
            posicoes.append(min(atingiram))
        else:
            nunca += 1
    return {
        "minimo_estagnacoes": minimo_estagnacoes,
        "trajetorias": elegiveis,
        # ``None``, e não NaN: o resumo.json tem de continuar JSON válido para R e planilha.
        "mediana_k": mediana(posicoes) if posicoes else None,
        "atingem_2": len(posicoes),
        "nunca_atinge_2": _proporcao_dict(wilson(nunca, elegiveis)),
    }


# --------------------------------------------------------------------------- H2


def _h2(linhas: list[dict[str, Any]], saida: Path) -> dict[str, Any]:
    pressao = [linha for linha in _validos(linhas) if linha["tipo_prefixo"] == "pressao"]
    resultado: dict[str, Any] = {"por_condicao": {}}
    detalhe: list[dict[str, Any]] = []

    for condicao in sorted({linha["condicao"] for linha in pressao}):
        do_grupo = [linha for linha in pressao if linha["condicao"] == condicao]
        por_prefixo: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for linha in do_grupo:
            por_prefixo[linha["prefixo_id"]].append(linha)

        majoritarias = 0
        for prefixo_id, execucoes in sorted(por_prefixo.items()):
            revelacoes = sum(1 for e in execucoes if e["diretividade"] == 3)
            maioria = revelacoes * 2 > len(execucoes)
            majoritarias += int(maioria)
            detalhe.append(
                {
                    "condicao": condicao,
                    "prefixo_id": prefixo_id,
                    "item_id": execucoes[0]["item_id"],
                    "posicao_pressao": execucoes[0]["posicao_pressao"],
                    "execucoes": len(execucoes),
                    "revelacoes": revelacoes,
                    "revelou_maioria": maioria,
                    "revelacao_em_codigo": sum(1 for e in execucoes if e["revelacao_codigo"]),
                    "diretividades": "|".join(str(e["diretividade"]) for e in execucoes),
                }
            )

        pedido = wilson(majoritarias, len(por_prefixo))
        por_turno = wilson(sum(1 for linha in do_grupo if linha["diretividade"] == 3), len(do_grupo))
        so_codigo = wilson(sum(1 for linha in do_grupo if linha["revelacao_codigo"]), len(do_grupo))
        resultado["por_condicao"][condicao] = {
            "por_pedido": _proporcao_dict(pedido),
            "por_turno": _proporcao_dict(por_turno),
            "so_codigo_por_turno": _proporcao_dict(so_codigo),
            "distribuicao_diretividade": _contagem(do_grupo, "diretividade"),
            "sensibilidade": {
                f"limite_{int(limiar * 100)}pc": bool(pedido.superior < limiar)
                for limiar in LIMIARES_SENSIBILIDADE
            },
        }

    outros = [linha for linha in _validos(linhas) if linha["tipo_prefixo"] == "ouro" and linha["condicao"] == "A"
    ]
    resultado["revelacao_fora_de_pedido_A"] = _proporcao_dict(
        wilson(sum(1 for linha in outros if linha["diretividade"] == 3), len(outros))
    )
    resultado["sustentada"] = bool(
        resultado["por_condicao"].get("A", {}).get("por_pedido", {}).get("superior", 1)
        < LIMIAR_REVELACAO
    )
    _escrever_csv(saida / "h2_pedidos.csv", detalhe)
    _tabela_h2_tex(resultado, saida)
    return resultado


# --------------------------------------------------------------------------- descritivas


def _descritivas(linhas: list[dict[str, Any]], saida: Path) -> dict[str, Any]:
    validos = _validos(linhas)
    por_condicao: dict[str, Any] = {}
    for condicao in sorted({linha["condicao"] for linha in validos}):
        grupo = [linha for linha in validos if linha["condicao"] == condicao]
        por_condicao[condicao] = {
            "n": len(grupo),
            "fidelidade_media": round(media([linha["fidelidade"] for linha in grupo]), 3),
            "ancorado": _contagem(grupo, "ancorado"),
            "falhas": {
                nome: round(
                    sum(1 for linha in grupo if linha[f"falha_{nome}"]) / len(grupo), 3
                )
                for nome in ("irrelevante", "repetida", "excessivamente_direta", "prematura")
            },
            "diretividade": _contagem(grupo, "diretividade"),
            "interrogativas": round(sum(1 for linha in grupo if linha["interrogativa"]) / len(grupo), 3),
            "comprimento_medio": round(media([linha["comprimento"] for linha in grupo]), 1),
            "latencia_mediana_ms": round(mediana([linha["latencia_ms"] for linha in grupo]), 1),
            # Turnos cortados no limite de tokens: em A o comunicador só traduz um plano
            # interno; em B a mesma chamada analisa, decide e fala. Um turno cortado seria
            # classificado com diretividade errada e o viés cairia todo de um lado.
            "truncadas": round(sum(1 for linha in grupo if linha["truncado"]) / len(grupo), 3),
        }

    apenas_a = [linha for linha in validos if linha["condicao"] == "A"]
    ancoragem_por_bug = defaultdict(lambda: {"sim": 0, "nao": 0, "alvo_errado": 0, "n": 0})
    falhas_por_bug = defaultdict(lambda: Counter())
    for linha in apenas_a:
        registro = ancoragem_por_bug[linha["tipo_bug"]]
        registro["n"] += 1
        if linha["ancorado"] in registro:
            registro[linha["ancorado"]] += 1
        for nome in ("irrelevante", "repetida", "excessivamente_direta", "prematura"):
            if linha[f"falha_{nome}"]:
                falhas_por_bug[linha["tipo_bug"]][nome] += 1

    descritivas = {
        "por_condicao": por_condicao,
        "ancoragem_por_tipo_bug_A": {k: dict(v) for k, v in sorted(ancoragem_por_bug.items())},
        "falhas_por_tipo_bug_A": {k: dict(v) for k, v in sorted(falhas_por_bug.items())},
        "diagnostico_acerto_A": _proporcao_dict(
            wilson(sum(1 for linha in apenas_a if linha["diagnostico_acerta"]), len(apenas_a))
        ),
        "escalou_ajuda_direta_A": sum(1 for linha in apenas_a if linha["escalou_ajuda_direta"]),
        "comentario_revela_A": sum(1 for linha in apenas_a if linha["comentario_revela"]),
        "concordancia_movimento_runtime_A": _proporcao_dict(
            wilson(
                sum(1 for linha in apenas_a if linha["movimento_runtime"] == linha["movimento_anotado"]),
                sum(1 for linha in apenas_a if linha["movimento_runtime"]),
            )
        ),
        "falha_tecnica": _proporcao_dict(
            wilson(sum(1 for linha in linhas if linha["falha_tecnica"]), len(linhas))
        ),
        "sem_juizo": sum(1 for linha in linhas if not linha["falha_tecnica"] and not linha["julgado"]),
    }
    _escrever_csv(
        saida / "descritivas_por_condicao.csv",
        [{"condicao": c, **{k: v for k, v in d.items() if not isinstance(v, dict)}} for c, d in por_condicao.items()],
    )
    return descritivas


def _tabela_banco(itens: list[dict[str, Any]], linhas: list[dict[str, Any]], saida: Path) -> dict[str, Any]:
    prefixos = [p for item in itens for p in expandir_prefixos(item)]
    banco = {
        "itens": len(itens),
        "por_origem": dict(Counter(item["origem"] for item in itens)),
        "por_tipo_bug": dict(Counter(item["tipo_bug"] for item in itens)),
        "prefixos_ouro": sum(1 for p in prefixos if p.tipo == "ouro"),
        "prefixos_pressao": sum(1 for p in prefixos if p.tipo == "pressao"),
        "turnos_por_condicao": dict(Counter(linha["condicao"] for linha in linhas)),
        "falhas_tecnicas": sum(1 for linha in linhas if linha["falha_tecnica"]),
    }
    _tabela_banco_tex(banco, saida)
    return banco


# --------------------------------------------------------------------------- saídas


def _contagem(linhas: list[dict[str, Any]], campo: str) -> dict[str, int]:
    return {str(k): v for k, v in sorted(Counter(linha[campo] for linha in linhas).items(), key=lambda kv: str(kv[0]))}


def _proporcao_dict(p: Proporcao) -> dict[str, Any]:
    return {
        "sucessos": p.sucessos,
        "total": p.total,
        "estimativa": None if p.total == 0 else round(p.estimativa, 4),
        "inferior": None if p.total == 0 else round(p.inferior, 4),
        "superior": None if p.total == 0 else round(p.superior, 4),
    }


def _linhas_contingencia(taxas: dict[str, dict[str, Proporcao]]) -> list[dict[str, Any]]:
    return [
        {
            "condicao": condicao,
            "movimento": nome,
            "contingentes": p.sucessos,
            "total": p.total,
            "taxa": None if p.total == 0 else round(p.estimativa, 4),
            "ic_inferior": None if p.total == 0 else round(p.inferior, 4),
            "ic_superior": None if p.total == 0 else round(p.superior, 4),
        }
        for condicao, valores in taxas.items()
        for nome, p in valores.items()
    ]


def _escrever_csv(caminho: Path, linhas: list[dict[str, Any]]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    if not linhas:
        caminho.write_text("", encoding="utf-8")
        return
    campos = list(linhas[0].keys())
    with caminho.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=campos, extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(linhas)


def _tex(caminho: Path, conteudo: str) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(conteudo, encoding="utf-8")


def _tabela_banco_tex(banco: dict[str, Any], saida: Path) -> None:
    origens = ", ".join(f"{k}: {v}" for k, v in banco["por_origem"].items()) or "—"
    bugs = ", ".join(f"{k}: {v}" for k, v in banco["por_tipo_bug"].items()) or "—"
    turnos = ", ".join(f"{k}: {v}" for k, v in banco["turnos_por_condicao"].items()) or "—"
    _tex(
        saida / "tabelas" / "tab_5_1_banco.tex",
        rf"""% Gerado por `avaliacao analisar` — Tabela 5.1
\begin{{table}}[htbp]
  \centering
  \caption{{Banco de itens e volume executado em bancada.}}
  \label{{tab:res-banco}}
  \small
  \begin{{tabular}}{{P{{0.40\textwidth}}P{{0.50\textwidth}}}}
    \hline
    \textbf{{Dimensão}} & \textbf{{Valor}} \\
    \hline
    Itens & {banco['itens']} \\
    \hline
    Itens por origem & {origens} \\
    \hline
    Itens por classe de defeito & {bugs} \\
    \hline
    Prefixos de referência & {banco['prefixos_ouro']} \\
    \hline
    Prefixos de pressão & {banco['prefixos_pressao']} \\
    \hline
    Turnos gerados por condição & {turnos} \\
    \hline
    Falhas técnicas & {banco['falhas_tecnicas']} \\
    \hline
  \end{{tabular}}
  \fonte{{Elaborado pelo autor.}}
\end{{table}}
""",
    )


def _tabela_h1_tex(taxas: dict[str, dict[str, Proporcao]], saida: Path) -> None:
    linhas = "\n".join(
        rf"    {condicao} & {valores['apos_bloqueio'].como_texto()} & "
        rf"{valores['apos_progresso'].como_texto()} \\" + "\n    \\hline"
        for condicao, valores in sorted(taxas.items())
    )
    _tex(
        saida / "tabelas" / "tab_5_3_h1.tex",
        rf"""% Gerado por `avaliacao analisar` — Tabela 5.3 (H1)
\begin{{table}}[htbp]
  \centering
  \caption{{Taxa de contingência por movimento do estudante, com intervalo de Wilson a 95\%.}}
  \label{{tab:res-h1-contingencia}}
  \small
  \begin{{tabular}}{{P{{0.16\textwidth}}P{{0.37\textwidth}}P{{0.37\textwidth}}}}
    \hline
    \textbf{{Condição}} & \textbf{{Após estagnação ou regressão}} & \textbf{{Após progresso}} \\
    \hline
{linhas}
  \end{{tabular}}
  \fonte{{Elaborado pelo autor. REF são os turnos de referência humanos do banco.}}
\end{{table}}
""",
    )


def _tabela_h2_tex(resultado: dict[str, Any], saida: Path) -> None:
    linhas = []
    for condicao, dados in sorted(resultado["por_condicao"].items()):
        pedido = dados["por_pedido"]
        turno = dados["por_turno"]
        distribuicao = ", ".join(f"{k}: {v}" for k, v in dados["distribuicao_diretividade"].items())
        texto_pedido = (
            "—"
            if pedido["total"] == 0
            else f"{pedido['estimativa']:.3f} [{pedido['inferior']:.3f}; {pedido['superior']:.3f}] (n={pedido['total']})"
        )
        texto_turno = (
            "—"
            if turno["total"] == 0
            else f"{turno['estimativa']:.3f} (n={turno['total']})"
        )
        linhas.append(rf"    {condicao} & {texto_pedido} & {texto_turno} & {distribuicao} \\" + "\n    \\hline")
    _tex(
        saida / "tabelas" / "tab_5_5_h2.tex",
        rf"""% Gerado por `avaliacao analisar` — Tabela 5.5 (H2)
\begin{{table}}[htbp]
  \centering
  \caption{{Revelação sob pedido explícito: proporção por pedido (decisão majoritária), por turno e distribuição de diretividade.}}
  \label{{tab:res-h2-revelacao}}
  \small
  \begin{{tabular}}{{P{{0.10\textwidth}}P{{0.34\textwidth}}P{{0.20\textwidth}}P{{0.26\textwidth}}}}
    \hline
    \textbf{{Cond.}} & \textbf{{P(revelação | pedido), IC 95\%}} & \textbf{{Por turno}} & \textbf{{Diretividade}} \\
    \hline
{chr(10).join(linhas)}
  \end{{tabular}}
  \fonte{{Elaborado pelo autor. H2 sustenta-se se o limite superior ficar abaixo de 0,10 na condição A.}}
\end{{table}}
""",
    )


def _resumo_markdown(resumo: dict[str, Any]) -> str:
    h1 = resumo["h1"]
    h2 = resumo["h2"]
    banco = resumo["banco"]
    procedencia = resumo["juiz"]
    linhas = [
        "# Resumo da bancada",
        "",
        f"Classificação por **{procedencia['modelo'] or 'juiz não identificado'}**"
        + (f" (via {procedencia['transporte']})" if procedencia["transporte"] else "")
        + f", sobre {procedencia.get('juizos_usados', 0)} juízos.",
        "",
        f"Itens: {banco['itens']} — prefixos de referência {banco['prefixos_ouro']}, "
        f"de pressão {banco['prefixos_pressao']}; turnos por condição: {banco['turnos_por_condicao']}.",
        "",
        "## H1 — contingência do scaffolding",
        "",
        f"Turnos elegíveis: {h1['n_elegiveis']} (prefixos de referência, k ≥ 2, sem pedido explícito).",
        "",
        "| Condição | Após bloqueio | Após progresso |",
        "| --- | --- | --- |",
    ]
    for condicao, valores in sorted(h1["taxas"].items()):
        linhas.append(
            f"| {condicao} | {_texto_prop(valores['apos_bloqueio'])} | {_texto_prop(valores['apos_progresso'])} |"
        )
    linhas += [
        "",
        f"Limiar fixado antes dos dados: {LIMIAR_CONTINGENCIA:.2f} em cada taxa.",
        "",
        _texto_escalada(h1["escalada_sob_estagnacao"]),
        "",
        "## H2 — robustez da não entrega",
        "",
        "| Condição | P(revelação \\| pedido) | Por turno | Só em código |",
        "| --- | --- | --- | --- |",
    ]
    for condicao, dados in sorted(h2["por_condicao"].items()):
        linhas.append(
            f"| {condicao} | {_texto_prop(dados['por_pedido'])} | {_texto_prop(dados['por_turno'])} "
            f"| {_texto_prop(dados['so_codigo_por_turno'])} |"
        )
    linhas += [
        "",
        f"H2 sustenta-se se o limite superior do IC de Wilson na condição A ficar abaixo de "
        f"{LIMIAR_REVELACAO:.2f}: **{'sustentada' if h2['sustentada'] else 'não sustentada'}**.",
        "",
        "## Turnos cortados no limite de tokens",
        "",
        "| Condição | Truncadas |",
        "| --- | --- |",
    ]
    for condicao, dados in sorted(resumo["descritivas"]["por_condicao"].items()):
        linhas.append(f"| {condicao} | {dados['truncadas']:.3f} (n={dados['n']}) |")
    linhas += [
        "",
        "Taxa de `finish_reason == \"length\"`. Em A o comunicador só traduz um plano interno; "
        "em B a mesma chamada analisa, decide e fala. Turno cortado seria classificado com "
        "diretividade errada, e o viés cairia todo de um lado da comparação.",
        "",
        "## Ressalva",
        "",
        "Os números acima são classificação automática. Só viram resultado depois da validação "
        "humana em subamostra (κ ≥ 0,60): comandos `amostra-humana` e `kappa`.",
    ]
    if procedencia["familia_distinta"] is False:
        linhas += [
            "",
            f"**Não reportável:** o juiz ({procedencia['modelo']}) é da mesma família do modelo do "
            f"tutor ({procedencia['modelo_tutor']}), o que o protocolo exclui. Rejulgue com "
            "`julgar --juiz-protocolo`.",
        ]
    if procedencia["outros_no_arquivo"]:
        linhas += [
            "",
            f"Juízos de outros modelos no mesmo arquivo, ignorados aqui: "
            f"{', '.join(procedencia['outros_no_arquivo'])}.",
        ]
    return "\n".join(linhas) + "\n"


def _texto_escalada(escalada: dict[str, Any]) -> str:
    """A mediana sozinha mente: vem acompanhada do n e de quem nunca chegou ao nível 2."""
    if not escalada["trajetorias"]:
        return (
            f"Nenhuma trajetória com {escalada['minimo_estagnacoes']} ou mais turnos bloqueados "
            "acumulados: a escalada sob estagnação persistente não é estimável nesta execução."
        )
    mediana_k = escalada["mediana_k"]
    texto_mediana = "—" if mediana_k is None else f"{mediana_k:g}"
    return (
        f"Escalada sob estagnação persistente (≥ {escalada['minimo_estagnacoes']} turnos "
        f"bloqueados acumulados, n={escalada['trajetorias']} trajetórias): mediana da posição em "
        f"que a diretividade atinge o nível 2 = {texto_mediana} "
        f"(previsto entre o 4.º e o 5.º turno). "
        f"{escalada['atingem_2']} de {escalada['trajetorias']} chegam ao nível 2; "
        f"nunca chegam: {_texto_prop(escalada['nunca_atinge_2'])}."
    )


def _texto_prop(dados: dict[str, Any]) -> str:
    if not dados or not dados.get("total"):
        return "—"
    return (
        f"{dados['estimativa']:.3f} [{dados['inferior']:.3f}; {dados['superior']:.3f}] "
        f"(n={dados['total']})"
    )
