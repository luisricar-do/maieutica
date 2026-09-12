"""Pré-computação dos estados de código do banco (Subseção 4.3.2, ``errors`` pré-computados).

Cada ``bug_code`` e cada estado intermediário é compilado **uma vez** com o mesmo motor da IDE,
fora do navegador (``packages/runner/lib/headless/cli.js`` do fork), e o resultado é gravado no
item. A bancada, em tempo de execução, só faz chamadas HTTP: é daqui que vêm os ``errors`` e os
``compilerErrorLines`` que ela envia, na forma exata em que a IDE os envia em uso real.

Os casos de teste do item também rodam aqui: o número de casos que passam em cada estado é a
regra objetiva do movimento do estudante quando há edição de código.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

RUNNER_PADRAO = Path("../portugol-ai-tutor/packages/runner/lib/headless/cli.js")


def caminho_runner(explicito: str = "") -> Path:
    bruto = explicito or os.getenv("PORTUGOL_RUNNER", "")
    caminho = Path(bruto) if bruto else (Path(__file__).resolve().parent.parent / RUNNER_PADRAO)
    caminho = caminho.resolve()
    if not caminho.is_file():
        raise SystemExit(
            f"executor headless não encontrado em {caminho}. "
            "Aponte com PORTUGOL_RUNNER ou --runner (fork portugol-ai-tutor, `packages/runner`)."
        )
    return caminho


def rodar(runner: Path, tarefas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Executa uma lista de ``{code, stdin, timeoutMs}`` no motor da IDE e devolve os resultados."""
    processo = subprocess.run(
        ["node", str(runner)],
        input=json.dumps(tarefas, ensure_ascii=False),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        cwd=str(runner.parent.parent.parent),
    )
    if processo.returncode != 0 or not processo.stdout.strip():
        raise SystemExit(f"executor headless falhou: {processo.stderr[-500:]}")
    return json.loads(processo.stdout)


def formatar_erros(resultado: dict[str, Any]) -> list[str]:
    """Mesma forma que a IDE envia: ``Linha L, coluna C: mensagem``."""
    todos = list(resultado.get("errors", [])) + list(resultado.get("parseErrors", []))
    return [
        f"Linha {erro.get('startLine')}, coluna {int(erro.get('startCol', 0)) + 1}: {erro.get('message')}"
        for erro in todos
    ]


def precomputar_item(item: dict[str, Any], runner: Path) -> dict[str, Any]:
    """Preenche ``errors``, ``compilerErrorLines`` e ``casos_ok`` de cada estado do item."""
    estados = item.get("estados_codigo", [])
    casos = item.get("unit_tests", [])

    compilacoes = rodar(runner, [{"code": e.get("codigo", ""), "timeoutMs": 5000} for e in estados])
    for estado, resultado in zip(estados, compilacoes):
        estado["errors"] = formatar_erros(resultado)
        estado["compilerErrorLines"] = list(resultado.get("compilerErrorLines", []))

    if casos:
        tarefas = [
            {"code": estado.get("codigo", ""), "stdin": list(caso.get("entrada", [])), "timeoutMs": 5000}
            for estado in estados
            for caso in casos
        ]
        execucoes = rodar(runner, tarefas)
        for indice, estado in enumerate(estados):
            fatia = execucoes[indice * len(casos) : (indice + 1) * len(casos)]
            passaram = sum(1 for caso, resultado in zip(casos, fatia) if _passou(caso, resultado))
            estado["casos_ok"] = passaram
            estado["casos_total"] = len(casos)
            estado["timeout"] = any(r.get("timedOut") for r in fatia)
    return item


def _passou(caso: dict[str, Any], resultado: dict[str, Any]) -> bool:
    """Um caso passa quando o programa executa, termina e a saída bate com o esperado.

    A quebra de linha final do esperado é **preservada**: sem ela, ``"Media = 2"`` casa dentro de
    ``"Media = 2.5"`` e um estado com defeito conta como caso aprovado. Como ``casos_ok`` é a
    regra objetiva do movimento do estudante (Subseção 5.2), esse falso positivo entraria direto
    em H1. Só espaços e tabulações são aparados.
    """
    if not resultado.get("executed") or resultado.get("timedOut"):
        return False
    saida = resultado.get("stdout") or ""
    esperado = str(caso.get("saida_contem", "")).strip(" \t")
    proibido = str(caso.get("saida_nao_contem", "")).strip(" \t")
    if esperado and esperado not in saida:
        return False
    return not (proibido and proibido in saida)


def precomputar_banco(
    diretorio: Path, runner: Path, *, ids: set[str] | None = None
) -> list[dict[str, Any]]:
    """Reescreve cada arquivo do banco com os estados pré-computados.

    ``ids`` restringe aos itens escolhidos (``--itens``); sem ele, o banco inteiro.
    """
    resumo = []
    for caminho in sorted(diretorio.glob("*.json")):
        item = json.loads(caminho.read_text(encoding="utf-8"))
        if ids is not None and item.get("id") not in ids:
            continue
        precomputar_item(item, runner)
        caminho.write_text(
            json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        resumo.append(
            {
                "item": item.get("id"),
                "estados": [
                    {
                        "id": estado.get("id"),
                        "erros": len(estado.get("errors", [])),
                        "linhas": estado.get("compilerErrorLines", []),
                        "casos_ok": estado.get("casos_ok"),
                        "casos_total": estado.get("casos_total"),
                    }
                    for estado in item.get("estados_codigo", [])
                ],
            }
        )
    return resumo
