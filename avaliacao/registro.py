"""Persistência da bancada: NDJSON por linha, diretório por execução, manifesto de congelamento.

Toda etapa é retomável: quem já está no arquivo não é refeito. Isso importa porque uma corrida
completa são ~1.300 turnos gerados e outros tantos juízos, e nenhuma delas deve ser reiniciada
do zero por uma queda de rede.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from avaliacao.config import EXECUCOES_DIR

_ESCRITA = threading.Lock()


def novo_id_execucao() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def diretorio_execucao(id_execucao: str | None, *, criar: bool = True) -> Path:
    alvo = EXECUCOES_DIR / (id_execucao or ultima_execucao() or novo_id_execucao())
    if criar:
        alvo.mkdir(parents=True, exist_ok=True)
    return alvo


def ultima_execucao() -> str | None:
    if not EXECUCOES_DIR.is_dir():
        return None
    candidatos = sorted(p.name for p in EXECUCOES_DIR.iterdir() if p.is_dir())
    return candidatos[-1] if candidatos else None


def ler_ndjson(caminho: Path) -> Iterator[dict[str, Any]]:
    if not caminho.is_file():
        return
    with caminho.open(encoding="utf-8") as arquivo:
        for linha in arquivo:
            linha = linha.strip()
            if linha:
                yield json.loads(linha)


def chaves_existentes(caminho: Path, campo: str = "chave") -> set[str]:
    return {registro.get(campo, "") for registro in ler_ndjson(caminho)}


def anexar(caminho: Path, registro: dict[str, Any]) -> None:
    linha = json.dumps(registro, ensure_ascii=False)
    with _ESCRITA:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        with caminho.open("a", encoding="utf-8") as arquivo:
            arquivo.write(linha + "\n")


def escrever_json(caminho: Path, conteudo: Any) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(conteudo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ler_json(caminho: Path) -> dict[str, Any]:
    if not caminho.is_file():
        return {}
    return json.loads(caminho.read_text(encoding="utf-8"))


def atualizar_manifesto(diretorio: Path, dados: dict[str, Any]) -> dict[str, Any]:
    """Acumula no manifesto o que o congelamento exige: modelos, hashes, commits, datas."""
    caminho = diretorio / "manifesto.json"
    manifesto = ler_json(caminho)
    manifesto.update(dados)
    manifesto.setdefault("criado_em", datetime.now(UTC).isoformat())
    manifesto["atualizado_em"] = datetime.now(UTC).isoformat()
    escrever_json(caminho, manifesto)
    return manifesto
