"""Validação humana do juiz: amostra estratificada e concordância (Subseção 4.3.4).

A classificação automática só é reportada depois de validada. Este módulo exporta a planilha
cega — sem a condição de origem e sem o veredito do juiz — para os dois codificadores e, depois
de preenchida, calcula o kappa entre os humanos e entre o consenso humano e o juiz, além da
acurácia do detector objetivo de revelação contra a codificação humana.

Aceitação: κ ≥ 0,60. Abaixo disso, o prompt do juiz é recalibrado **uma** vez; persistindo, a
variável é reportada só na amostra humana. κ **indefinido** — subamostra com uma só categoria —
não é aceitação: sai em ``indefinidos`` e conta como variável ainda não validada.
"""

from __future__ import annotations

import csv
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

from avaliacao.analise import _linha
from avaliacao.estatistica import kappa_cohen, kappa_ponderado
from avaliacao.executor import ARQUIVO_TURNOS
from avaliacao.itens import Prefixo, turnos_de_referencia
from avaliacao.julgamento import ARQUIVO_JUIZOS, indexar_prefixos
from avaliacao.registro import escrever_json, ler_json, ler_ndjson

ACEITACAO_KAPPA = 0.60

#: Escala declarada de cada ordinal (Apêndices de diretividade e da rubrica). É ela, e não a
#: amplitude observada na subamostra, que define os pesos do κ ponderado.
ESCALAS_ORDINAIS: dict[str, tuple[int, ...]] = {
    "diretividade": (0, 1, 2, 3),
    "fidelidade": (1, 2, 3),
}

VARIAVEIS_ORDINAIS = ("diretividade", "fidelidade")
VARIAVEIS_BOOLEANAS = ("irrelevante", "repetida", "excessivamente_direta", "prematura")
VARIAVEIS_TEXTUAIS = ("movimento_estudante", "ancorado")
VARIAVEIS = VARIAVEIS_ORDINAIS + VARIAVEIS_TEXTUAIS + VARIAVEIS_BOOLEANAS

COLUNAS_CONTEXTO = (
    "id_cego",
    "item_id",
    "tipo_bug",
    "enunciado",
    "codigo_no_prefixo",
    "erros_no_prefixo",
    "conversa_ate_aqui",
    "turno_do_tutor",
)
COLUNAS_CODIFICACAO = COLUNAS_CONTEXTO + VARIAVEIS + ("notas",)

_VERDADEIROS = frozenset({"sim", "s", "true", "verdadeiro", "1", "x"})
_FALSOS = frozenset({"nao", "não", "n", "false", "falso", "0"})


#: Turnos gerados na amostra. A tese pede ~150 e acrescenta ~30 para acomodar a condição B
#: sem desfazer a estratificação.
TAMANHO_GERADOS = 180
#: Turnos de referência (humanos) na mesma planilha — a codificação é cega, por isso eles não
#: podem sair num arquivo à parte: o codificador distinguiria a origem pela folha.
TAMANHO_REFERENCIA = 30


def _candidatos_gerados(
    diretorio: Path,
    por_id: dict[str, Any],
    juizos: dict[str, Any],
    prefixos: dict[str, Prefixo],
) -> list[dict[str, Any]]:
    turnos = {t.get("chave", ""): t for t in ler_ndjson(diretorio / ARQUIVO_TURNOS)}
    candidatos = []
    for chave, turno in turnos.items():
        if turno.get("falha_tecnica"):
            continue
        linha = _linha(turno, juizos, por_id, prefixos)
        if not linha["julgado"]:
            continue
        prefixo = prefixos.get(linha["prefixo_id"])
        candidatos.append(
            {
                "chave": chave,
                "unidade": "gerado",
                "item_id": linha["item_id"],
                "tipo_bug": linha["tipo_bug"],
                "estrato": (linha["condicao"], linha["tipo_bug"], linha["diretividade"]),
                "revelacao_codigo": linha["revelacao_codigo"],
                "code": prefixo.code if prefixo else "",
                "errors": list(prefixo.errors) if prefixo else [],
                "history": list(prefixo.history) if prefixo else [],
                "turno_do_tutor": turno.get("message", ""),
            }
        )
    return candidatos


def _candidatos_referencia(
    itens: list[dict[str, Any]], juizos: dict[str, Any]
) -> list[dict[str, Any]]:
    """Turnos do tutor humano do banco, já julgados — a calibração interna dos limiares."""
    candidatos = []
    for item in itens:
        for referencia in turnos_de_referencia(item):
            juizo = juizos.get(referencia["id"])
            if not juizo or juizo.get("erro") or juizo.get("diretividade") is None:
                continue
            candidatos.append(
                {
                    "chave": referencia["id"],
                    "unidade": "referencia",
                    "item_id": referencia["item_id"],
                    "tipo_bug": item.get("tipo_bug", ""),
                    "estrato": (item.get("tipo_bug", ""), juizo.get("diretividade")),
                    "revelacao_codigo": False,
                    "code": referencia["code"],
                    "errors": list(referencia["errors"]),
                    "history": list(referencia["history"]),
                    "turno_do_tutor": referencia["texto"],
                }
            )
    return candidatos


def _sortear_por_estrato(
    candidatos: list[dict[str, Any]],
    quantidade: int,
    sorteio: random.Random,
    ja_escolhidas: set[str],
) -> list[dict[str, Any]]:
    """Rodízio entre estratos: nenhum cresce mais que os outros enquanto houver de onde tirar."""
    estratos: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for candidato in candidatos:
        if candidato["chave"] not in ja_escolhidas:
            estratos[candidato["estrato"]].append(candidato)
    for grupo in estratos.values():
        sorteio.shuffle(grupo)

    chaves = sorted(estratos, key=str)
    escolhidas: list[dict[str, Any]] = []
    passo = 0
    while len(escolhidas) < quantidade and any(estratos[c] for c in chaves):
        grupo = estratos[chaves[passo % len(chaves)]]
        if grupo:
            escolhidas.append(grupo.pop())
        passo += 1
    return escolhidas


def gerar_amostra(
    diretorio: Path,
    itens: list[dict[str, Any]],
    *,
    tamanho: int = TAMANHO_GERADOS,
    tamanho_referencia: int = TAMANHO_REFERENCIA,
    semente: int = 20260912,
) -> dict[str, Any]:
    """Amostra estratificada por condição, classe de erro e nível de diretividade previsto.

    Todos os casos de revelação em código entram, até um quarto da amostra dos gerados. Os turnos
    de referência entram na **mesma** planilha, embaralhados com os gerados: a codificação é cega
    à condição, e uma folha separada entregaria a origem.
    """
    por_id = {item["id"]: item for item in itens}
    juizos = {j["chave"]: j for j in ler_ndjson(diretorio / ARQUIVO_JUIZOS)}
    prefixos = indexar_prefixos(itens)

    gerados = _candidatos_gerados(diretorio, por_id, juizos, prefixos)
    if not gerados:
        raise SystemExit("nenhum turno julgado nesta execução: rode `julgar` antes.")
    referencia = _candidatos_referencia(itens, juizos)

    sorteio = random.Random(semente)
    teto_revelacao = max(1, tamanho // 4)
    revelacoes = [c for c in gerados if c["revelacao_codigo"]]
    sorteio.shuffle(revelacoes)
    escolhidas = revelacoes[:teto_revelacao]
    n_revelacoes = len(escolhidas)
    ja_escolhidas = {c["chave"] for c in escolhidas}

    escolhidas += _sortear_por_estrato(
        gerados, tamanho - len(escolhidas), sorteio, ja_escolhidas
    )
    n_gerados = len(escolhidas)
    escolhidas += _sortear_por_estrato(referencia, tamanho_referencia, sorteio, set())
    n_referencia = len(escolhidas) - n_gerados

    sorteio.shuffle(escolhidas)
    mapa: dict[str, str] = {}
    registros: list[dict[str, Any]] = []
    for posicao, candidato in enumerate(escolhidas, start=1):
        id_cego = f"T{posicao:04d}"
        mapa[id_cego] = candidato["chave"]
        item = por_id.get(candidato["item_id"], {})
        registros.append(
            {
                "id_cego": id_cego,
                "item_id": candidato["item_id"],
                "tipo_bug": candidato["tipo_bug"],
                "enunciado": item.get("problem", ""),
                "codigo_no_prefixo": candidato["code"],
                "erros_no_prefixo": "; ".join(candidato["errors"]),
                "conversa_ate_aqui": _conversa(candidato["history"]),
                "turno_do_tutor": candidato["turno_do_tutor"],
                **{coluna: "" for coluna in VARIAVEIS + ("notas",)},
            }
        )

    destino = diretorio / "validacao_humana"
    destino.mkdir(parents=True, exist_ok=True)
    for nome in ("codificador_1.csv", "codificador_2.csv"):
        _escrever(destino / nome, registros, COLUNAS_CODIFICACAO)
    escrever_json(destino / "mapa_amostra.json", mapa)
    return {
        "amostra": len(registros),
        "gerados": n_gerados,
        "referencia": n_referencia,
        "revelacoes_em_codigo": n_revelacoes,
        "destino": str(destino),
    }


def calcular_kappa(diretorio: Path, itens: list[dict[str, Any]]) -> dict[str, Any]:
    """κ humano×humano e consenso×juiz, mais precisão e cobertura do detector objetivo."""
    destino = diretorio / "validacao_humana"
    mapa = ler_json(destino / "mapa_amostra.json")
    codificador_1 = _ler(destino / "codificador_1.csv")
    codificador_2 = _ler(destino / "codificador_2.csv")
    consenso_manual = _ler(destino / "consenso.csv")

    ids = sorted(set(codificador_1) & set(codificador_2))
    if not ids:
        raise SystemExit(
            f"nada para comparar: preencha {destino / 'codificador_1.csv'} e "
            f"{destino / 'codificador_2.csv'} (uma linha por turno, colunas da rubrica)."
        )

    por_id = {item["id"]: item for item in itens}
    juizos = {j["chave"]: j for j in ler_ndjson(diretorio / ARQUIVO_JUIZOS)}
    prefixos = indexar_prefixos(itens)
    linhas = {
        t.get("chave", ""): _linha(t, juizos, por_id, prefixos)
        for t in ler_ndjson(diretorio / ARQUIVO_TURNOS)
    }

    resultado: dict[str, Any] = {"n_amostra": len(ids), "humano_humano": {}, "consenso_juiz": {}}
    divergencias: list[dict[str, Any]] = []

    for variavel in VARIAVEIS:
        funcao = _funcao_kappa(variavel)
        a = [_valor(codificador_1[i], variavel) for i in ids]
        b = [_valor(codificador_2[i], variavel) for i in ids]
        resultado["humano_humano"][variavel] = _arredondar(funcao(a, b))

        consenso: list[Any] = []
        do_juiz: list[Any] = []
        for id_cego in ids:
            valor_1 = _valor(codificador_1[id_cego], variavel)
            valor_2 = _valor(codificador_2[id_cego], variavel)
            resolvido = _valor(consenso_manual.get(id_cego, {}), variavel)
            if valor_1 == valor_2:
                valor = valor_1
            elif resolvido is not None:
                valor = resolvido
            else:
                valor = None
                divergencias.append(
                    {
                        "id_cego": id_cego,
                        "variavel": variavel,
                        "codificador_1": valor_1,
                        "codificador_2": valor_2,
                    }
                )
            juizo = juizos.get(mapa.get(id_cego, ""))
            if valor is None or not juizo:
                continue
            consenso.append(valor)
            do_juiz.append(_do_juiz(juizo, variavel))
        resultado["consenso_juiz"][variavel] = _arredondar(funcao(consenso, do_juiz))

    resultado["detector"] = _acuracia_detector(ids, codificador_1, codificador_2, mapa, linhas)
    resultado["abaixo_da_aceitacao"] = sorted(
        f"{grupo}:{variavel}"
        for grupo in ("humano_humano", "consenso_juiz")
        for variavel, valor in resultado[grupo].items()
        if valor is not None and valor < ACEITACAO_KAPPA
    )
    # κ indefinido (amostra degenerada, uma só categoria) também não está validado: entra como
    # pendência, e não como silêncio que passa no critério.
    resultado["indefinidos"] = sorted(
        f"{grupo}:{variavel}"
        for grupo in ("humano_humano", "consenso_juiz")
        for variavel, valor in resultado[grupo].items()
        if valor is None
    )
    resultado["validadas"] = not resultado["abaixo_da_aceitacao"] and not resultado["indefinidos"]
    resultado["divergencias"] = len(divergencias)
    _escrever(
        destino / "divergencias.csv",
        divergencias,
        ("id_cego", "variavel", "codificador_1", "codificador_2"),
    )
    escrever_json(destino / "kappa.json", resultado)
    return resultado


def _acuracia_detector(
    ids: list[str],
    codificador_1: dict[str, dict[str, str]],
    codificador_2: dict[str, dict[str, str]],
    mapa: dict[str, str],
    linhas: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Detector de nível 3 em código contra a codificação humana concordante."""
    acertos = disparos = humanos_tres = concordantes = 0
    verdadeiros_positivos = 0
    for id_cego in ids:
        humano = _valor(codificador_1[id_cego], "diretividade")
        outro = _valor(codificador_2[id_cego], "diretividade")
        linha = linhas.get(mapa.get(id_cego, ""))
        if humano is None or humano != outro or linha is None:
            continue
        concordantes += 1
        disparou = bool(linha["revelacao_codigo"])
        eh_tres = humano == 3
        disparos += int(disparou)
        humanos_tres += int(eh_tres)
        verdadeiros_positivos += int(disparou and eh_tres)
        acertos += int(disparou == eh_tres)
    return {
        "n": concordantes,
        "acuracia": None if not concordantes else round(acertos / concordantes, 4),
        "precisao": None if not disparos else round(verdadeiros_positivos / disparos, 4),
        "cobertura": None if not humanos_tres else round(verdadeiros_positivos / humanos_tres, 4),
        "disparos": disparos,
        "humanos_nivel_3": humanos_tres,
    }


def _conversa(history: list[dict[str, str]]) -> str:
    return "\n".join(
        f"{'Estudante' if t.get('role') == 'user' else 'Tutor'}: {t.get('content', '')}"
        for t in history
    )


def _escrever(caminho: Path, registros: list[dict[str, Any]], campos: tuple[str, ...]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=list(campos), extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(registros)


def _ler(caminho: Path) -> dict[str, dict[str, str]]:
    if not caminho.is_file():
        return {}
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        return {
            linha["id_cego"]: linha
            for linha in csv.DictReader(arquivo)
            if linha.get("id_cego") and any(str(linha.get(v, "")).strip() for v in VARIAVEIS)
        }


def _funcao_kappa(variavel: str):
    """κ ponderado com a escala declarada para as ordinais; κ de Cohen para as demais."""
    if variavel not in VARIAVEIS_ORDINAIS:
        return kappa_cohen
    escala = ESCALAS_ORDINAIS[variavel]
    return lambda a, b: kappa_ponderado(a, b, escala=escala)


def _valor(linha: dict[str, str], variavel: str) -> Any:
    bruto = str(linha.get(variavel, "") or "").strip()
    if not bruto:
        return None
    if variavel in VARIAVEIS_ORDINAIS:
        try:
            valor = int(bruto)
        except ValueError:
            return None
        # Fora da escala declarada é erro de preenchimento: entra como célula em branco.
        return valor if valor in ESCALAS_ORDINAIS[variavel] else None
    if variavel in VARIAVEIS_BOOLEANAS:
        minusculo = bruto.casefold()
        if minusculo in _VERDADEIROS:
            return True
        if minusculo in _FALSOS:
            return False
        return None
    if variavel == "movimento_estudante":
        return bruto.upper()
    return bruto.casefold()


def _do_juiz(juizo: dict[str, Any], variavel: str) -> Any:
    if variavel in VARIAVEIS_ORDINAIS:
        return juizo.get(variavel)
    if variavel in VARIAVEIS_BOOLEANAS:
        return bool((juizo.get("falhas") or {}).get(variavel))
    if variavel == "movimento_estudante":
        return str(juizo.get("movimento_estudante", "")).upper()
    return str(juizo.get("ancorado", "")).casefold()


def _arredondar(valor: float) -> float | None:
    return None if valor != valor else round(valor, 4)  # NaN != NaN
