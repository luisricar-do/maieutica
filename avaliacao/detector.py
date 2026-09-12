"""Detecção objetiva da revelação (nível 3 em código), sem juiz.

Regra do Apêndice de diretividade: quando a mensagem contém trecho de código, em bloco ou em
linha, que case algum dos padrões de correção do item — padrões derivados das correções aceitas
e validados contra as alternativas de referência —, o turno é nível 3 sem intervenção do juiz.
A revelação em prosa fica para o juiz.

O teste é relativo ao **código vigente do prefixo**: um padrão que o código do estudante já
satisfaz corresponde a uma correção já aplicada e não pode contar como revelação — senão
qualquer turno que cite a linha corrente do estudante viraria nível 3.

Sobre a condição A registram-se ainda, como descritivos, ``add_inline_comment`` que case um
padrão de correção e o disparo de ``escalate_to_direct_help``; a diretividade, essa, é sempre
julgada pelo texto produzido.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

_BLOCO = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.DOTALL)
_INLINE = re.compile(r"`([^`\n]+)`")

#: Linhas soltas com cara de código Portugol (atribuição, chamada ou construto de controle).
_LINHA_CODIGO = re.compile(
    r"^\s*(?:"
    r"[A-Za-z_]\w*\s*(?:=|\+\+|--)\s*\S.*"
    r"|(?:escreva|leia|limpa)\s*\(.*"
    r"|(?:se|senao|enquanto|para|faca|funcao|programa)\b.*[\(\{].*"
    r"|(?:inteiro|real|logico|caracter|cadeia|vetor)\s+[A-Za-z_]\w*.*"
    r")$"
)


@dataclass(frozen=True)
class Deteccao:
    """Veredito objetivo sobre um turno."""

    revelacao_codigo: bool = False
    padroes: list[str] = field(default_factory=list)
    trechos: list[str] = field(default_factory=list)
    comentario_revela: bool = False
    escalou_ajuda_direta: bool = False
    padroes_ignorados: list[str] = field(default_factory=list)

    def para_dict(self) -> dict[str, Any]:
        return {
            "revelacao_codigo": self.revelacao_codigo,
            "padroes_disparados": self.padroes,
            "trechos": self.trechos,
            "comentario_revela": self.comentario_revela,
            "escalou_ajuda_direta": self.escalou_ajuda_direta,
            "padroes_ignorados": self.padroes_ignorados,
        }


def trechos_de_codigo(mensagem: str) -> list[str]:
    """Blocos cercados, trechos entre crases e linhas soltas com forma de comando."""
    trechos = [t.strip() for t in _BLOCO.findall(mensagem or "")]
    restante = _BLOCO.sub(" ", mensagem or "")
    trechos.extend(t.strip() for t in _INLINE.findall(restante))
    sem_inline = _INLINE.sub(" ", restante)
    trechos.extend(
        linha.strip() for linha in sem_inline.splitlines() if _LINHA_CODIGO.match(linha.strip())
    )
    return [t for t in trechos if t]


def detectar(
    mensagem: str,
    fix_patterns: Iterable[str],
    acoes: list[dict[str, Any]] | None = None,
    codigo_vigente: str = "",
) -> Deteccao:
    """Veredito objetivo sobre um turno, dado o código que o estudante já tem à frente.

    Um padrão de correção **já satisfeito pelo código vigente** não é revelação: naquele
    prefixo a correção correspondente já foi aplicada, e citar a linha corrente do estudante é
    o que um tutor faz para ancorar a pergunta. Esses padrões saem do teste e ficam registrados
    em ``padroes_ignorados``.
    """
    compilados = [re.compile(p, re.IGNORECASE) for p in fix_patterns]
    ignorados = [p for p in compilados if codigo_vigente and p.search(codigo_vigente)]
    ativos = [p for p in compilados if p not in ignorados]
    trechos = trechos_de_codigo(mensagem)

    disparados: list[str] = []
    casados: list[str] = []
    for padrao in ativos:
        for trecho in trechos:
            if padrao.search(trecho):
                disparados.append(padrao.pattern)
                casados.append(trecho)
                break

    comentario = False
    escalou = False
    for acao in acoes or []:
        tipo = acao.get("type")
        if tipo == "escalate_to_direct_help":
            escalou = True
        if tipo == "add_inline_comment":
            texto = " ".join(str(v) for v in (acao.get("payload") or {}).values())
            comentario = comentario or any(p.search(texto) for p in ativos)

    return Deteccao(
        revelacao_codigo=bool(disparados),
        padroes=disparados,
        trechos=casados,
        comentario_revela=comentario,
        escalou_ajuda_direta=escalou,
        padroes_ignorados=[p.pattern for p in ignorados],
    )
