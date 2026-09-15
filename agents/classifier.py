"""
Estimador do movimento do estudante: nó do grafo, entre o analista e o estrategista.

O movimento é a entrada da política de contingência, e a dissertação define-o em três valores —
progresso, estagnação, regressão. Dois deles um classificador determinístico alcança bem: o
pedido explícito, pela forma da fala, e a mudança objetiva do estado do código, pelo compilador.
O terceiro não: **decidir se a hipótese que o estudante afirmou está errada** é julgar conteúdo,
e nenhum padrão textual o faz. A regra textual de ``agents.movement`` lê "hipótese nova" como
progresso e, quando a hipótese é errada, mede o contrário do que a dissertação chama regressão.

É esse — e só esse — degrau que este módulo substitui. A precedência não muda: pedido explícito,
depois o compilador, depois o texto; o estimador entra no lugar do texto, e cai de novo na regra
determinística sempre que não devolve rótulo. Por isso o nó vem **depois do analista**: o
diagnóstico do estado corrente diz qual é o defeito, e sem saber qual é o defeito não se julga se
a hipótese do estudante aponta para ele.

Cada turno é estimado com o que existia até ele — nunca com o que veio depois. O contador é o da
dissertação e continua aritmético: soma em bloqueio, zera em progresso. Estima-se o rótulo, não
o acumulador.
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agents.llm import create_chat_client
from agents.movement import (
    StudentMovement,
    classify_movement,
    stagnation_streak,
    turnos_que_o_texto_decide,
)

logger = logging.getLogger(__name__)

CLASSIFIER_SYSTEM = """You are the Movement Classifier of a Socratic tutoring system. You never speak to the student and you never tutor. You read one debugging turn and output exactly one label for how the student moved in that turn.

- PROGRESSO — the turn advances the debugging: a hypothesis about the defect that is CORRECT, a new and relevant observation about the program's behaviour, a correct reading of the compiler error, or a productive narrowing of where the defect is.
- ESTAGNACAO — the turn adds nothing new: declared blockage ("não sei", "travei"), repetition of what the student already said, a vague complaint, a question that carries no hypothesis and no new observation, or an answer outside the focus of the task.
- REGRESSAO — the turn moves backwards: the student asserts a hypothesis that is WRONG about where or what the defect is, claims the program is correct while the defect is still there, or drops a correct line of reasoning for one that is not.

DECISIVE RULE. A confident, articulate, well-written hypothesis is PROGRESSO only when it is right about the actual defect in the code you are shown. When it points at the wrong line, the wrong variable or the wrong cause, it is REGRESSAO. Fluency is not progress and length is not progress: judge the claim against the code, not against how it is phrased.

A question with no hypothesis and no new observation is ESTAGNACAO, not PROGRESSO. Asking for confirmation of something already said is ESTAGNACAO.

Judge ONLY the last student turn, the one marked with `>>>`. The earlier turns are context, and serve to tell a new contribution from a repetition of what was already said. Do not judge the tutor."""


class MovementLabel(str, Enum):
    PROGRESSO = "PROGRESSO"
    ESTAGNACAO = "ESTAGNACAO"
    REGRESSAO = "REGRESSAO"


class MovementEstimate(BaseModel):
    movement: MovementLabel = Field(
        description="How the student moved in the turn marked >>>, judged against the code."
    )


def _create_classifier_llm():
    return create_chat_client(max_tokens=64, temperature=0.0)


def _numbered(code: str) -> str:
    lines = code.splitlines() or [""]
    width = len(str(len(lines)))
    return "\n".join(f"{i + 1:{width}} | {line}" for i, line in enumerate(lines))


def _defeito(diagnosis: Any) -> str:
    """O defeito segundo o analista, para julgar se a hipótese do estudante aponta para ele."""
    if not isinstance(diagnosis, dict):
        return ""
    partes = [
        f"- Error type: {diagnosis.get('errorType') or 'none'}",
        f"- Affected variable: {diagnosis.get('affectedVariable') or 'n/a'}",
        f"- Line: {diagnosis.get('errorLine') if diagnosis.get('errorLine') else 'n/a'}",
    ]
    descricao = str(diagnosis.get("errorDescription") or "").strip()
    if descricao:
        partes.append(f"- What is actually wrong: {descricao}")
    return "\n".join(partes)


def _payload(
    *,
    code: str,
    errors: list[str],
    problem_statement: str,
    defeito: str,
    dialogo: list[dict],
) -> str:
    partes: list[str] = []
    if problem_statement.strip():
        partes.append(f"<exercise>\n{problem_statement.strip()}\n</exercise>")
    partes.append(f"<learner_code>\n{_numbered(code)}\n</learner_code>")
    if errors:
        corpo = "\n".join(str(e) for e in errors[:12])
        partes.append(f"<compiler_errors>\n{corpo}\n</compiler_errors>")
    else:
        partes.append("<compiler_errors>\n(none — the program compiles)\n</compiler_errors>")
    if defeito:
        # Só entra quando o diagnóstico é do estado de código deste turno; ver ``_estimar_turno``.
        partes.append(f"<known_defect>\n{defeito}\n</known_defect>")

    linhas: list[str] = []
    for item in dialogo:
        papel = "STUDENT" if item.get("role") == "user" else "TUTOR"
        linhas.append(f"{papel}: {str(item.get('content', '')).strip()}")
    if linhas:
        linhas[-1] = f">>> {linhas[-1]}"
    partes.append("<dialogue>\n" + "\n".join(linhas) + "\n</dialogue>")
    return "\n\n".join(partes)


async def _estimar_turno(
    *,
    dialogo: list[dict],
    code: str,
    errors: list[str],
    problem_statement: str,
    defeito: str,
) -> StudentMovement | None:
    """Um rótulo para o último turno de ``dialogo``. ``None`` quando o modelo não responde."""
    try:
        structured = _create_classifier_llm().with_structured_output(MovementEstimate)
        mensagens = [
            SystemMessage(content=CLASSIFIER_SYSTEM),
            HumanMessage(
                content=_payload(
                    code=code,
                    errors=errors,
                    problem_statement=problem_statement,
                    defeito=defeito,
                    dialogo=dialogo,
                )
            ),
        ]
        resultado = await structured.ainvoke(mensagens)
    except Exception as exc:  # noqa: BLE001 — degradar para a regra determinística, nunca falhar o turno
        logger.warning("classificador de movimento: %s: %s", type(exc).__name__, exc)
        return None
    if not isinstance(resultado, MovementEstimate):
        return None
    return resultado.movement.value  # type: ignore[return-value]


class _Sonda:
    """Regista que turnos chegam ao degrau do texto, sem alterar a precedência."""

    def __init__(self) -> None:
        self.posicoes: set[int] = set()

    def __call__(self, user_turns: list[str], code: str) -> StudentMovement:
        self.posicoes.add(len(user_turns) - 1)
        return "ESTAGNACAO"


def _indices_de_estudante(history: list[dict]) -> list[int]:
    return [
        i
        for i, item in enumerate(history)
        if isinstance(item, dict) and item.get("role") == "user"
    ]


def _estado_do_turno(history: list[dict], indice: int, code: str, errors: list[str]) -> tuple[str, list[str]]:
    """Código e erros que acompanham o turno; o estado do pedido quando o turno não os traz."""
    turno = history[indice]
    codigo = turno.get("code")
    if not isinstance(codigo, str):
        return code, list(errors)
    erros = turno.get("errors")
    return codigo, [str(e) for e in erros] if isinstance(erros, list) else []


async def estimar_movimentos(state: dict[str, Any]) -> dict[int, StudentMovement]:
    """Rótulo estimado para cada turno do estudante em que o texto é quem decide.

    As chamadas são concorrentes, mas cada uma vê só o diálogo até ao seu turno: o rótulo do
    turno 2 não pode depender do que o estudante disse no turno 5, sob pena de o contador
    deixar de ser o que a política teria consumido naquele momento.
    """
    history = [h for h in (state.get("history") or []) if isinstance(h, dict)]
    code = str(state.get("code") or "")
    errors = [str(e) for e in (state.get("errors") or [])]

    posicoes = set(turnos_que_o_texto_decide(history))
    sonda = _Sonda()
    classify_movement(
        code=code,
        history=history,
        errors=errors,
        previous_code=state.get("previous_code") or None,
        previous_errors=[str(e) for e in (state.get("previous_errors") or [])],
        classificador_textual=sonda,
    )
    posicoes |= sonda.posicoes
    if not posicoes:
        return {}

    indices = _indices_de_estudante(history)
    problem_statement = str(state.get("problem_statement") or "")
    defeito_corrente = _defeito(state.get("diagnosis"))

    async def _um(posicao: int) -> tuple[int, StudentMovement | None]:
        if posicao < 0 or posicao >= len(indices):
            return posicao, None
        indice = indices[posicao]
        codigo_turno, erros_turno = _estado_do_turno(history, indice, code, errors)
        # O diagnóstico é do estado corrente: só vale como "defeito conhecido" no turno cujo
        # código é esse mesmo. Nos demais o modelo julga a hipótese contra o código do turno.
        defeito = defeito_corrente if codigo_turno == code else ""
        rotulo = await _estimar_turno(
            dialogo=history[: indice + 1],
            code=codigo_turno,
            errors=erros_turno,
            problem_statement=problem_statement,
            defeito=defeito,
        )
        return posicao, rotulo

    resultados = await asyncio.gather(*(_um(p) for p in sorted(posicoes)))
    return {posicao: rotulo for posicao, rotulo in resultados if rotulo is not None}


async def run_classifier(state: dict[str, Any]) -> dict[str, Any]:
    """Nó do grafo: reclassifica o movimento e re-deriva a estagnação acumulada."""
    history = [h for h in (state.get("history") or []) if isinstance(h, dict)]
    estimados = await estimar_movimentos(state)
    if not estimados:
        # Nada a estimar (ou o modelo falhou em tudo): fica o que o serviço já derivou.
        return {}

    def _estimador(user_turns: list[str], code: str) -> StudentMovement | None:
        return estimados.get(len(user_turns) - 1)

    movimento = classify_movement(
        code=str(state.get("code") or ""),
        history=history,
        errors=[str(e) for e in (state.get("errors") or [])],
        previous_code=state.get("previous_code") or None,
        previous_errors=[str(e) for e in (state.get("previous_errors") or [])],
        classificador_textual=_estimador,
    )
    streak = stagnation_streak(
        history,
        current_movement=movimento["movement"],
        classificador_textual=_estimador,
    )
    return {
        "student_movement": movimento["movement"],
        "movement_source": movimento["source"],
        "stagnation_streak": streak["streak"],
        "stagnation_source": streak["source"],
    }
