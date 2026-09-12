"""
Movimento do estudante no turno anterior: entrada determinística da política de contingência.

A regra segue a contingência de Wood, Bruner e Ross (1976) na forma operacionalizada pela
dissertação: com edição de código, decide o compilador; sem edição, decide o texto; o pedido
explícito de resposta prevalece sobre as demais categorias.

Este classificador alimenta a **política** (o estrategista escala ou sustenta a dica). A
classificação usada na **análise** é a do protocolo de avaliação (casos de teste do item mais
juiz com validação humana) e é derivada do registro estruturado, não deste módulo.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal, TypedDict

StudentMovement = Literal[
    "PROGRESSO",
    "ESTAGNACAO",
    "REGRESSAO",
    "PEDIDO_EXPLICITO",
    "NENHUM",
]

MovementSource = Literal["codigo", "texto", "nenhum"]


class MovementResult(TypedDict):
    movement: StudentMovement
    source: MovementSource


#: Pedido explícito de resposta, correção ou código (H2). Exige marca imperativa/possessiva:
#: "o que está errado?" sozinho é pergunta legítima, "me fala o que está errado" é pedido.
_EXPLICIT_REQUEST_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        r"\bme (fala|diz|fale|diga|mostra|mostre|manda|mande|de|da|entrega)\b",
        r"\b(fala|diz|diga|fale) (logo|de uma vez|pra mim|para mim)\b",
        r"\bqual (e |eh )?(a )?resposta\b",
        r"\bqual (linha|a linha)\b.*\b(mudar|trocar|corrigir|alterar)\b",
        r"\b(manda|mande|escreve|escreva|posta|cola)\b.*\bcodigo\b",
        r"\bcodigo (certo|corrigido|arrumado|pronto|completo)\b",
        r"\b(arruma|arrume|conserta|conserte|corrige|corrija|resolve|resolva|faz|faca)\b"
        r".*\b(pra mim|para mim|isso|o codigo|meu codigo)\b",
        r"\bso (me )?(diz|diga|fala|fale|mostra|mostre)\b",
        r"\bmostra (como fica|a solucao|o codigo)\b",
        r"\b(da|de|passa|passe) a resposta\b",
        r"\bqual (e |eh )?(a )?(solucao|correcao)\b",
    )
)

#: Sinais textuais de estagnação: bloqueio declarado, ausência de conteúdo novo.
_STALL_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        r"\bnao (sei|entendi|entendo|consigo|faco ideia|sei nao)\b",
        r"\bsem ideia\b",
        r"\b(to|estou) (perdido|perdida|travado|travada|boiando)\b",
        r"\btravei\b",
        r"\bcontinua (igual|na mesma|o mesmo erro)\b",
        r"\bnao mudou nada\b",
        r"\bnenhuma ideia\b",
    )
)

#: Abaixo disto a mensagem não carrega conteúdo novo suficiente para contar como progresso.
_MIN_SUBSTANTIVE_CHARS = 12


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", stripped).strip()


def _user_turns(history: list[dict]) -> list[str]:
    return [
        str(item.get("content", ""))
        for item in history
        if isinstance(item, dict) and item.get("role") == "user"
    ]


def is_explicit_request(text: str) -> bool:
    """Pedido explícito de resposta, correção ou código (condição de H2)."""
    normalized = _normalize(text)
    return any(pattern.search(normalized) for pattern in _EXPLICIT_REQUEST_PATTERNS)


def _classify_by_text(user_turns: list[str]) -> StudentMovement:
    last = user_turns[-1]
    normalized = _normalize(last)
    if not normalized:
        return "ESTAGNACAO"
    if any(pattern.search(normalized) for pattern in _STALL_PATTERNS):
        return "ESTAGNACAO"
    if any(_normalize(previous) == normalized for previous in user_turns[:-1]):
        # Repete a própria fala: não há conteúdo novo.
        return "ESTAGNACAO"
    if len(normalized) < _MIN_SUBSTANTIVE_CHARS:
        return "ESTAGNACAO"
    # Hipótese (correta ou parcial) ou resposta com conteúdo novo. A regressão textual
    # ("hipótese incorreta afirmada") não é decidível sem julgamento e fica para o juiz.
    return "PROGRESSO"


def _classify_by_code(previous_errors: list[str], errors: list[str]) -> StudentMovement | None:
    before = [e for e in previous_errors if str(e).strip()]
    after = [e for e in errors if str(e).strip()]
    if before and not after:
        return "PROGRESSO"
    if after and not before:
        return "REGRESSAO"
    if len(after) < len(before):
        return "PROGRESSO"
    if len(after) > len(before):
        return "REGRESSAO"
    if before and set(map(str, before)) == set(map(str, after)):
        # Editou, e o compilador diz exatamente o mesmo: nada mudou.
        return "ESTAGNACAO"
    # Mesmo número de erros com conteúdo distinto, ou erro puramente lógico (sem erro de
    # compilação nos dois estados): o compilador não decide; devolve ao texto.
    return None


def classify_movement(
    *,
    code: str,
    history: list[dict],
    errors: list[str] | None = None,
    previous_code: str | None = None,
    previous_errors: list[str] | None = None,
) -> MovementResult:
    """
    Classifica o último turno do estudante.

    Precedência: pedido explícito > regra do código (quando houve edição e o compilador
    decide) > sinal do texto. Sem turno do estudante, ``NENHUM`` (abertura do diálogo, fora
    de H1).
    """
    user_turns = _user_turns(history)
    if not user_turns:
        return {"movement": "NENHUM", "source": "nenhum"}

    if is_explicit_request(user_turns[-1]):
        return {"movement": "PEDIDO_EXPLICITO", "source": "texto"}

    if previous_code is not None and previous_code != code:
        by_code = _classify_by_code(previous_errors or [], errors or [])
        if by_code is not None:
            return {"movement": by_code, "source": "codigo"}

    return {"movement": _classify_by_text(user_turns), "source": "texto"}
