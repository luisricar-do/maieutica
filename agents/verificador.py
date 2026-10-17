"""Verificador de nível (v1.2): confere a mensagem do comunicador contra o nível-alvo antes da saída.

Na v1.1 o nível-alvo calculado em código chegava ao estrategista e ao comunicador como instrução, e
o comunicador seguia-o como tendência (``h1foco``: 251 de 652 turnos no alvo). Aqui a mensagem é
classificada antes de ir para o estudante; fora do alvo, ou com a correção, o comunicador reescreve
com o motivo, no máximo ``TENTATIVAS_EXTRA`` vezes. O verificador lê o plano e a mensagem, nunca o
código nem o diagnóstico: a separação de papéis do comunicador fica como estava.

Ligado por ``VERIFICADOR_DE_NIVEL=1``; desligado, o comportamento é o da v1.1.
"""

from __future__ import annotations

import json
import logging
import os
import re

from langchain_core.messages import HumanMessage, SystemMessage

from agents.escalada import DESCRICOES, NOMES
from agents.llm import create_chat_client

logger = logging.getLogger(__name__)

VERIFICADOR_ENV = "VERIFICADOR_DE_NIVEL"
TENTATIVAS_EXTRA = 2
_TRUTHY = frozenset({"1", "true", "yes", "on", "sim"})

VERIFICADOR_SYSTEM = """You classify ONE message that a Socratic programming tutor is about to send to a novice.
Concreteness ladder:
- 0 open: an observation or question that points at no region of the code and names no error.
- 1 focused: directs attention to the line, variable or construct of the defect, without saying what is wrong.
- 2 conceptual: names the nature of the error or the concept involved, without the concrete correction.
- 3 revealing: the concrete correction, in code or as an unambiguous edit instruction. A question whose only possible answer is the correction ("isn't `i` missing an increment?", "what if you used `>=`?") is level 3 too.
Answer only with JSON: {"nivel": <0-3>, "motivo": "<one short sentence>"}"""


def verificador_ligado() -> bool:
    return (os.getenv(VERIFICADOR_ENV) or "").strip().casefold() in _TRUTHY


def _verificador_llm():
    return create_chat_client(max_tokens=120, temperature=0)


def _ler_nivel(texto: str) -> tuple[int | None, str]:
    bruto = texto.strip()
    bruto = re.sub(r"^```(?:json)?|```$", "", bruto, flags=re.MULTILINE).strip()
    try:
        dados = json.loads(bruto)
        nivel = int(dados.get("nivel"))
        return (nivel if 0 <= nivel <= 3 else None), str(dados.get("motivo") or "")
    except (ValueError, TypeError, AttributeError):
        return None, ""


async def classificar(plano: str, mensagem: str) -> tuple[int | None, str]:
    resposta = await _verificador_llm().ainvoke(
        [
            SystemMessage(content=VERIFICADOR_SYSTEM),
            HumanMessage(content=f"<internal_plan>\n{plano}\n</internal_plan>\n\n<message>\n{mensagem}\n</message>"),
        ]
    )
    return _ler_nivel(str(resposta.content))


def instrucao_de_reescrita(nivel_alvo: int, rascunho: str, nivel_lido: int, motivo: str) -> str:
    """Bloco acrescentado ao prompt do comunicador quando o rascunho saiu fora do alvo."""
    return (
        "\n<rewrite_required>\n"
        f"Your previous draft was level {nivel_lido}, but this message must be level {nivel_alvo} "
        f"({NOMES[nivel_alvo]}). Reviewer note: {motivo}\n"
        f"Previous draft: {rascunho}\n"
        f"Rewrite it at level {nivel_alvo}: {DESCRICOES[nivel_alvo]} Level 3 is forbidden.\n"
        "</rewrite_required>\n"
    )


def escolher(candidatos: list[tuple[str, int | None]], nivel_alvo: int) -> tuple[str, int | None]:
    """O rascunho no alvo; senão o mais próximo dele que não revele; senão o último."""
    seguros = [(m, n) for m, n in candidatos if n is not None and n < 3]
    for mensagem, nivel in seguros:
        if nivel == nivel_alvo:
            return mensagem, nivel
    if seguros:
        return min(seguros, key=lambda c: abs(c[1] - nivel_alvo))
    return candidatos[-1]
