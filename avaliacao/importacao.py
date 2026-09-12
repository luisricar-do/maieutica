"""Importação de diálogos do *benchmark* de Al-Hossami para o formato do banco.

O conjunto original (Al-Hossami et al., 2023, 2024) é texto com marcas::

    <problem> <bug_code> <bug_desc> <bug_fixes> <unit_tests> <stu_desc> <dialogue>

Este módulo faz a parte **mecânica** da Subseção 2.4 da especificação: lê um diálogo, separa as
marcas, reconstrói os estados de código a partir dos blocos ``<code>`` e devolve o esqueleto do
item já na estrutura do banco, com o texto original preservado em ``fonte`` para a revisão do
segundo docente.

O que **não** faz, por ser tradução e não conversão: verter o código para Portugol Studio, o texto
para português, escrever ``unit_tests`` na forma de entrada/saída da IDE, classificar ``tipo_bug``
e anotar ``movimentos_ouro``. Esses campos saem marcados como pendência e o item só passa em
``validar`` depois de preenchidos — é de propósito, para que nada entre no banco por inércia.

Ordem de uso::

    python -m avaliacao importar --dialogo 56_15_compute_average_socratic_dialogue
    # traduzir o rascunho em avaliacao/traducao/ e movê-lo para avaliacao/banco/
    python -m avaliacao estados && python -m avaliacao validar
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

#: Marcado nos campos que dependem de tradução humana; ``validar`` recusa o item enquanto existir.
PENDENTE = "PENDENTE"

#: Prioridade por problema, da Subseção 2.2 da especificação (tabela de seleção).
PRIORIDADE: dict[int, int] = {
    56: 1, 1: 1, 61: 1, 60: 1, 64: 1,
    15: 2, 24: 2, 62: 2, 59: 2, 65: 2, 66: 2,
    0: 3, 21: 3, 67: 3, 58: 3, 2: 3, 3: 3, 63: 3,
}

_MARCAS = ("problem", "bug_code", "bug_desc", "bug_fixes", "unit_tests", "stu_desc", "dialogue")
_NUMERO_DE_LINHA = re.compile(r"^\s*\d+\.\s?")
#: Papéis do conjunto original. ``Instructor:`` aparece duas vezes, nos fios 1 e 2 de
#: ``compute_average``, onde o resto do conjunto usa ``Assistant:``; sem ele essas duas falas do
#: tutor seriam coladas ao turno anterior. A Tabela 1 do artigo reporta 920 turnos de instrutor,
#: que é a contagem de ``Assistant:`` — as duas de ``Instructor:`` ficam de fora dela.
_PAPEL = re.compile(r"^(User|Student|Assistant|Instructor|Tutor):\s*(.*)$")
_PAPEL_ESTUDANTE = ("User", "Student")


def _bloco(texto: str, marca: str) -> str:
    achado = re.search(rf"<{marca}>(.*?)</{marca}>", texto, re.S)
    return achado.group(1).strip("\n") if achado else ""


def _sem_numeros(codigo: str) -> str:
    """Remove a numeração ``1. `` que o conjunto original usa para citar linhas no diálogo."""
    linhas = [_NUMERO_DE_LINHA.sub("", linha) for linha in codigo.strip("\n").split("\n")]
    return "\n".join(linhas).rstrip() + "\n"


def parsear_dialogo(bruto: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Devolve ``(turnos, codigos)``: turnos com papel, texto e alternativas; códigos por edição.

    Cada bloco ``<code>`` do original é uma edição do estudante e vira um estado do item; o turno
    em que ele aparece passa a apontar para esse estado.
    """
    turnos: list[dict[str, Any]] = []
    codigos: list[str] = []
    dentro_do_codigo = False
    acumulado: list[str] = []

    for linha in bruto.split("\n"):
        nua = linha.strip()
        if nua == "<code>":
            dentro_do_codigo, acumulado = True, []
            continue
        if nua == "</code>":
            dentro_do_codigo = False
            codigos.append(_sem_numeros("\n".join(acumulado)))
            if turnos:
                turnos[-1]["_indice_codigo"] = len(codigos) - 1
            continue
        if dentro_do_codigo:
            acumulado.append(linha)
            continue

        papel = _PAPEL.match(nua)
        if papel:
            turnos.append({
                "papel": "estudante" if papel.group(1) in _PAPEL_ESTUDANTE else "tutor",
                "texto": papel.group(2).strip(),
                "alternativas": [],
            })
            continue
        if nua.startswith("<alt>") and turnos:
            turnos[-1]["alternativas"].append(nua[len("<alt>"):].strip())
            continue
        if nua and turnos:  # continuação de uma fala de várias linhas
            alvo = turnos[-1]["alternativas"] if turnos[-1]["alternativas"] else None
            if alvo:
                alvo[-1] = f"{alvo[-1]} {nua}".strip()
            else:
                turnos[-1]["texto"] = f"{turnos[-1]['texto']} {nua}".strip()

    return turnos, codigos


def _ancoras(bug_desc: str, bug_fixes: str) -> dict[str, Any]:
    """Primeira aproximação das âncoras: linhas citadas na descrição e identificadores em crase."""
    texto = f"{bug_desc}\n{bug_fixes}"
    linhas = sorted({int(n) for n in re.findall(r"lines?\s+(\d+)", texto, re.I)})
    identificadores = [t for t in re.findall(r"`([^`]+)`", texto) if re.fullmatch(r"\w+", t)]
    return {
        "linhas": linhas,
        "variaveis": sorted(dict.fromkeys(identificadores))[:4],
        "construtos": [],
    }


def importar(caminho: Path, *, commit: str = "") -> dict[str, Any]:
    """Lê um arquivo do conjunto original e devolve o esqueleto do item."""
    texto = caminho.read_text(encoding="utf-8")
    partes = {marca: _bloco(texto, marca) for marca in _MARCAS}
    turnos, codigos = parsear_dialogo(partes["dialogue"])

    nome = caminho.stem
    problema_id = int(nome.split("_")[0])
    thread = re.search(r"^(.*)_conversational_thread_(\d+)$", nome)
    if thread:
        identificador = f"{thread.group(1)}_t{thread.group(2)}"
    else:
        identificador = re.sub(r"_socratic_dialogue$", "", nome)

    estados: list[dict[str, Any]] = [{
        "id": "s0",
        "codigo": PENDENTE,
        "errors": [],
        "compilerErrorLines": [],
        "casos_ok": None,
        "casos_total": None,
        "timeout": False,
        "descricao": "código inicial com o defeito",
        "defeitos_vigentes": [PENDENTE],
    }]
    for n, _ in enumerate(codigos, start=1):
        estados.append({
            "id": f"s{n}",
            "codigo": PENDENTE,
            "errors": [],
            "compilerErrorLines": [],
            "casos_ok": None,
            "casos_total": None,
            "timeout": False,
            "descricao": PENDENTE,
            "defeitos_vigentes": [PENDENTE],
        })

    estado_atual = "s0"
    dialogo: list[dict[str, Any]] = []
    primeiro_estudante = True
    for turno in turnos:
        indice = turno.pop("_indice_codigo", None)
        if indice is not None:
            estado_atual = f"s{indice + 1}"
        saida: dict[str, Any] = {"papel": turno["papel"], "texto": turno["texto"]}
        if turno["papel"] == "tutor":
            saida["alternativas"] = turno["alternativas"]
        else:
            saida["estado_codigo"] = estado_atual
            saida["movimento"] = "NENHUM" if primeiro_estudante else PENDENTE
            primeiro_estudante = False
            if turno["alternativas"]:
                saida["alternativas_estudante_originais"] = turno["alternativas"]
        dialogo.append(saida)

    # Turnos depois de o estudante alcançar o estado final: no original são cortesia de
    # encerramento, mas cada um vira um prefixo-ouro (``_prefixos_ouro``) com o defeito já
    # corrigido. Marcados aqui; cortar ou manter é decisão do tradutor, não do importador.
    estado_final = f"s{len(codigos)}" if codigos else ""
    corte = next(
        (i for i, t in enumerate(dialogo)
         if t["papel"] == "estudante" and t.get("estado_codigo") == estado_final and estado_final),
        None,
    )
    cauda = len(dialogo) - corte if corte is not None else 0
    tutores_na_cauda = sum(1 for t in dialogo[corte:] if t["papel"] == "tutor") if corte else 0

    return {
        "id": identificador,
        "origem": "al_hossami_v2",
        "prioridade": PRIORIDADE.get(problema_id, 3),
        "tipo_bug": PENDENTE,
        "conceitos": [],
        "problem": PENDENTE,
        "bug_code": PENDENTE,
        "bug_desc": PENDENTE,
        "bug_fixes": [],
        "unit_tests": [],
        "estados_codigo": estados,
        "fix_patterns": [],
        "anchor_tokens": _ancoras(partes["bug_desc"], partes["bug_fixes"]),
        "dialogo": dialogo,
        "revisado_por": None,
        "notas_traducao": PENDENTE,
        "estado_solucao": estado_final or PENDENTE,
        "cauda_pos_solucao": {
            "primeiro_turno": corte,
            "turnos": cauda,
            "turnos_do_tutor": tutores_na_cauda,
            "nota": (
                "turnos a partir daí ocorrem com o defeito já corrigido; cada turno do tutor "
                "nessa faixa vira um prefixo-ouro. Decidir na tradução se entram no item."
            ),
        },
        "fonte": {
            "conjunto": "al_hossami socratic-debugging-benchmark, v2_sigcse/final_dataset",
            "arquivo": caminho.name,
            "commit": commit,
            "problema_id": problema_id,
            "problem": partes["problem"],
            "bug_code": _sem_numeros(partes["bug_code"]),
            "bug_desc": partes["bug_desc"],
            "bug_fixes": partes["bug_fixes"],
            "unit_tests": [t for t in partes["unit_tests"].split("\n") if t.strip()],
            "codigos_por_edicao": codigos,
        },
    }


#: Campos de ``fonte`` que acompanham o item no banco. O resto — enunciado, código e diálogo
#: originais em inglês — fica só no rascunho: serve à revisão da tradução, mas publicar o banco
#: com ele redistribuiria o texto de Al-Hossami et al., que não traz licença explícita.
CAMPOS_PONTEIRO = ("conjunto", "arquivo", "commit", "problema_id")


def fonte_ponteiro(fonte: dict[str, Any]) -> dict[str, Any]:
    """Reduz ``fonte`` à proveniência: de onde veio, de que versão, qual problema."""
    return {campo: fonte[campo] for campo in CAMPOS_PONTEIRO if campo in fonte}


def commit_do_conjunto(diretorio: Path) -> str:
    try:
        saida = subprocess.run(
            ["git", "-C", str(diretorio), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return saida.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def pendencias(item: dict[str, Any]) -> list[str]:
    """Lista o que falta traduzir, para o rascunho dizer por si só o que ainda não foi feito."""
    faltas: list[str] = []
    for campo in ("tipo_bug", "problem", "bug_code", "bug_desc", "notas_traducao"):
        if item.get(campo) == PENDENTE:
            faltas.append(campo)
    for campo in ("bug_fixes", "unit_tests", "fix_patterns", "conceitos"):
        if not item.get(campo):
            faltas.append(campo)
    pendentes_estado = [e["id"] for e in item["estados_codigo"] if e["codigo"] == PENDENTE]
    if pendentes_estado:
        faltas.append(f"estados_codigo ({', '.join(pendentes_estado)})")
    pendentes_mov = sum(1 for t in item["dialogo"] if t.get("movimento") == PENDENTE)
    if pendentes_mov:
        faltas.append(f"movimento em {pendentes_mov} turno(s) do estudante")
    if not item["anchor_tokens"]["construtos"]:
        faltas.append("anchor_tokens.construtos")
    cauda = item.get("cauda_pos_solucao", {})
    if cauda.get("turnos_do_tutor"):
        faltas.append(
            f"decidir sobre a cauda: {cauda['turnos_do_tutor']} turno(s) do tutor após a correção"
        )
    return faltas


def escrever(item: dict[str, Any], destino: Path) -> Path:
    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / f"{item['id']}.json"
    arquivo.write_text(json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return arquivo
