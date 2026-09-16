"""
Pedido de ajuda socrática: valida o payload, corre o grafo LangGraph e devolve o corpo JSON + código HTTP.
"""

import logging
import re
import time
from typing import Any, TypedDict, cast

from agents.graph import tutor_graph
from agents.llm import chat_model_name
from agents.movement import classify_movement, stagnation_streak
from agents.problem_context import parse_problem_statement
from agents.usage import TokenUsageCollector
from services import interaction_log

logger = logging.getLogger(__name__)

#: ``sessionId`` entra no caminho do blob do registro: só caracteres seguros.
_SAFE_SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def build_tutor_meta_from_actions(
    actions: Any,
    *,
    intent: str = "",
    student_movement: str = "",
    movement_source: str = "",
    stagnation_streak: int = 0,
    stagnation_source: str = "",
    movement_baseline: str = "",
    stagnation_streak_baseline: int = 0,
    hint_level: int = 0,
    model: str = "",
    usage: dict[str, int] | None = None,
    finish_reason: str = "",
) -> dict[str, Any]:
    """
    Metadados de política de conversa para o cliente (IDE) e para a avaliação.

    Quando o estrategista emite ``mark_bug_resolved``, a UI pode encerrar a conversa
    atual e iniciar uma nova (ex.: overlay imersivo). ``intent``, ``studentMovement`` e
    ``model`` acompanham o turno para o harness de bancada e para a análise: permitem
    contar o roteamento de cada prefixo e registrar a versão do modelo sem ler o log
    do serviço.
    """
    meta: dict[str, Any] = {"suggestedConversationEnd": False, "endReason": "none"}
    if isinstance(actions, list):
        for item in actions:
            if isinstance(item, dict) and item.get("type") == "mark_bug_resolved":
                meta = {"suggestedConversationEnd": True, "endReason": "bug_resolved"}
                break
    meta["intent"] = intent or "DEBUG"
    meta["studentMovement"] = student_movement or "NENHUM"
    # A estagnação acumulada é a variável independente de H1: vai no meta para que a
    # análise leia o que a política consumiu, e não só o que ela produziu. ``source``
    # distingue o contador derivado do histórico do degradado ao turno corrente.
    meta["stagnationStreak"] = max(0, int(stagnation_streak))
    meta["stagnationSource"] = stagnation_source or "nenhum"
    meta["movementSource"] = movement_source or "nenhum"
    # O que a regra determinística teria dito no mesmo turno. Não alimenta política nenhuma:
    # existe para que a comparação entre o estimador e a regex saia da própria corrida, sem a
    # repetir, e para que a queda do estimador para a regra apareça na apuração em vez de
    # desaparecer dentro de um rótulo igual aos outros.
    if movement_baseline:
        meta["movementBaseline"] = movement_baseline
        meta["stagnationStreakBaseline"] = max(0, int(stagnation_streak_baseline))
    # O nível de dica em vigor no turno. Modula o ritmo da escada de concretude e não o teto
    # (o nível 3 é proibido em qualquer valor), de modo que ler a diretividade de um turno sem
    # saber que ritmo estava em vigor é ler metade do dado. Na bancada ficou fixo em 1 e a
    # análise teve de ir buscá-lo à configuração; registrado aqui, sai do próprio turno.
    if hint_level:
        meta["hintLevel"] = max(1, min(3, int(hint_level)))
    meta["model"] = model or chat_model_name()
    if usage is not None:
        # Soma das chamadas do grafo no turno — roteador, analista, estrategista, comunicador.
        # É esse o custo que se compara com a chamada única das condições B e C. Ausente no
        # SSE, onde o uso não é recolhido: zeros permanentes seriam informação falsa.
        meta["usage"] = dict(usage)
    if finish_reason:
        # Motivo de parada do turno: "length" quando alguma etapa do grafo bateu no teto de
        # tokens. Sem ele a verificação de truncamento da bancada ficava cega para a condição A.
        meta["finishReason"] = finish_reason
    return meta


class TutorHelpState(TypedDict):
    code: str
    errors: list[str]
    history: list[dict]
    active_tutor_decorations: int
    include_documentation: bool
    diagnosis: dict
    documentation_context: list[str]
    strategist_plan: str
    tutor_response: str
    actions: list[dict]
    intent: str
    hint_level: int
    student_name: str
    cursor_line: int | None
    cursor_column: int | None
    compiler_error_lines: list[int]
    ast_summary: str
    data_flow_context: str
    previous_code: str
    previous_errors: list[str]
    student_movement: str
    movement_source: str
    stagnation_streak: int
    stagnation_source: str
    session_id: str
    problem_statement: str


def _parse_session_id(raw: object) -> str:
    """Identificador de sessão gerado pela IDE; vazio quando ausente ou malformado."""
    if not isinstance(raw, str):
        return ""
    value = raw.strip()
    return value if _SAFE_SESSION_ID.match(value) else ""


def _parse_optional_code(raw: object) -> str | None:
    """Estado anterior do código; ``None`` quando o cliente não o envia."""
    if not isinstance(raw, str):
        return None
    return raw


def _parse_include_documentation(raw: object) -> bool:
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    return False


def _parse_hint_level(raw: object) -> int:
    if raw is None:
        return 1
    if isinstance(raw, bool):
        return 1
    if isinstance(raw, int):
        return max(1, min(3, raw))
    if isinstance(raw, float) and raw.is_integer():
        return max(1, min(3, int(raw)))
    if isinstance(raw, str) and raw.strip() != "":
        try:
            return max(1, min(3, int(raw.strip(), 10)))
        except ValueError:
            return 1
    return 1


def _parse_optional_positive_int(raw: object) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int) and raw >= 1:
        return raw
    if isinstance(raw, float) and raw.is_integer():
        iv = int(raw)
        return iv if iv >= 1 else None
    if isinstance(raw, str) and raw.strip() != "":
        try:
            iv = int(raw.strip(), 10)
            return iv if iv >= 1 else None
        except ValueError:
            return None
    return None


def _parse_positive_int_list(raw: object) -> list[int]:
    if not isinstance(raw, list):
        return []
    out: set[int] = set()
    for item in raw:
        parsed = _parse_optional_positive_int(item)
        if parsed is not None:
            out.add(parsed)
    return sorted(out)


def _parse_student_name(raw: object) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw.strip()[:80]
    return str(raw).strip()[:80]


def _parse_ast_summary(raw: object) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw.strip()[:2000]
    return str(raw).strip()[:2000]


def _parse_active_tutor_decorations(raw: object) -> int:
    if raw is None:
        return 0
    if isinstance(raw, bool):
        return 0
    if isinstance(raw, int):
        return max(0, raw)
    if isinstance(raw, float):
        return max(0, int(raw)) if raw.is_integer() else 0
    if isinstance(raw, str) and raw.strip() != "":
        try:
            return max(0, int(raw, 10))
        except ValueError:
            return 0
    return 0


def parse_help_payload(
    payload: Any,
) -> tuple[TutorHelpState | None, dict[str, Any] | None, int]:
    """
    Valida o body JSON já desserializado.

    Em caso de sucesso devolve ``(initial_state, None, 200)``.
    Em caso de erro devolve ``(None, {error: ...}, código_http)``.
    """
    if not isinstance(payload, dict):
        return None, {"error": "O corpo JSON deve ser um objeto."}, 400

    code = payload.get("code", "")
    errors = payload.get("errors", [])
    history = payload.get("history", [])

    if not isinstance(code, str) or not code.strip():
        return (
            None,
            {"error": "O campo 'code' é obrigatório e não pode estar vazio."},
            400,
        )

    if not isinstance(errors, list):
        return None, {"error": "O campo 'errors' deve ser uma lista."}, 400

    if not isinstance(history, list):
        return None, {"error": "O campo 'history' deve ser uma lista."}, 400

    errors_str = [str(e) for e in errors]
    history_dicts = [h for h in history if isinstance(h, dict)]
    active_tutor_decorations = _parse_active_tutor_decorations(
        payload.get("activeTutorDecorations")
    )
    include_documentation = _parse_include_documentation(
        payload.get("includeDocumentation")
    )
    hint_level = _parse_hint_level(payload.get("hintLevel"))
    student_name = _parse_student_name(payload.get("studentName"))
    cursor_line = _parse_optional_positive_int(payload.get("cursorLine"))
    cursor_column = _parse_optional_positive_int(payload.get("cursorColumn"))
    compiler_error_lines = _parse_positive_int_list(payload.get("compilerErrorLines"))
    ast_summary = _parse_ast_summary(payload.get("astSummary"))
    problem_statement = parse_problem_statement(payload.get("problemStatement"))
    data_flow_context = _parse_ast_summary(payload.get("dataFlowContext"))
    session_id = _parse_session_id(payload.get("sessionId"))
    previous_code = _parse_optional_code(payload.get("previousCode"))
    raw_previous_errors = payload.get("previousErrors")
    previous_errors = (
        [str(e) for e in raw_previous_errors] if isinstance(raw_previous_errors, list) else []
    )
    movement = classify_movement(
        code=code,
        history=history_dicts,
        errors=errors_str,
        previous_code=previous_code,
        previous_errors=previous_errors,
    )
    # Estagnação acumulada desde o último progresso: a variável que a política de escalonamento
    # consome (H1). Derivada do histórico quando o cliente anexa o estado de código de cada
    # turno; degradada ao turno corrente quando não anexa, com a origem declarada na telemetria.
    streak = stagnation_streak(history_dicts, current_movement=movement["movement"])

    initial_state: TutorHelpState = {
        "problem_statement": problem_statement,
        "code": code,
        "errors": errors_str,
        "history": history_dicts,
        "active_tutor_decorations": active_tutor_decorations,
        "include_documentation": include_documentation,
        "diagnosis": {},
        "documentation_context": [],
        "strategist_plan": "",
        "tutor_response": "",
        "actions": [],
        "intent": "",
        "hint_level": hint_level,
        "student_name": student_name,
        "cursor_line": cursor_line,
        "cursor_column": cursor_column,
        "compiler_error_lines": compiler_error_lines,
        "ast_summary": ast_summary,
        "data_flow_context": data_flow_context,
        "previous_code": previous_code or "",
        "previous_errors": previous_errors,
        "student_movement": movement["movement"],
        "movement_source": movement["source"],
        "stagnation_streak": streak["streak"],
        "stagnation_source": streak["source"],
        "session_id": session_id,
    }
    return initial_state, None, 200


#: Campos de movimento que o nó ``classifier`` pode reescrever durante o grafo.
CAMPOS_DE_MOVIMENTO = (
    "student_movement",
    "movement_source",
    "stagnation_streak",
    "stagnation_source",
)


def estado_pos_grafo(initial_state: TutorHelpState, result: Any) -> TutorHelpState:
    """Estado com o movimento que a política **consumiu**, e não o que o serviço adivinhou.

    O serviço classifica pela regra determinística antes do grafo — é o que vale para as
    intenções que não passam pelo estrategista e é a queda quando o estimador não responde. O nó
    ``classifier``, quando corre, reescreve esses campos, e é essa versão que vai à telemetria e
    ao ``tutorMeta``: registrar a outra seria registrar uma variável que ninguém leu.
    """
    if not isinstance(result, dict):
        return initial_state
    final = dict(initial_state)
    for campo in CAMPOS_DE_MOVIMENTO:
        if campo in result and result[campo] not in (None, ""):
            final[campo] = result[campo]
    return cast(TutorHelpState, final)


async def log_turn(
    payload: Any,
    state: TutorHelpState,
    *,
    response: dict[str, Any],
    intent: str,
    started: float,
    endpoint: str = "/api/help",
    error: str | None = None,
) -> None:
    """Uma linha do registro estruturado por turno (ver ``services.interaction_log``)."""
    if not interaction_log.is_enabled():
        return
    record = interaction_log.build_record(
        payload,
        endpoint=endpoint,
        session_id=state["session_id"],
        response=response,
        intent=intent,
        student_movement=state["student_movement"],
        stagnation_streak=state["stagnation_streak"],
        stagnation_source=state["stagnation_source"],
        movement_source=state["movement_source"],
        model=chat_model_name(),
        latency_ms=int((time.monotonic() - started) * 1000),
        error=error,
    )
    await interaction_log.log_interaction(record)


async def process_help_request(payload: Any) -> tuple[dict[str, Any], int]:
    """
    Processa o body JSON já desserializado.

    Devolve ``(corpo_dict, status_http)``.
    """
    initial_state, err_body, status = parse_help_payload(payload)
    if initial_state is None:
        assert err_body is not None
        return err_body, status

    started = time.monotonic()
    usage = TokenUsageCollector()
    try:
        result = await tutor_graph.ainvoke(initial_state, config={"callbacks": [usage]})
    except Exception as exc:
        logger.exception("Falha ao executar o grafo do tutor (process_help_request)")
        await log_turn(
            payload,
            initial_state,
            response={},
            intent="",
            started=started,
            error=f"{type(exc).__name__}: {exc}",
        )
        raise

    actions = result.get("actions") or []
    if not isinstance(actions, list):
        actions = []

    final_state = estado_pos_grafo(initial_state, result)
    body = {
        "message": result.get("tutor_response", ""),
        "diagnosis": result.get("diagnosis", {}),
        "actions": actions,
        "tutorMeta": build_tutor_meta_from_actions(
            actions,
            intent=str(result.get("intent") or ""),
            student_movement=final_state["student_movement"],
            movement_source=final_state["movement_source"],
            stagnation_streak=final_state["stagnation_streak"],
            stagnation_source=final_state["stagnation_source"],
            movement_baseline=initial_state["student_movement"],
            stagnation_streak_baseline=initial_state["stagnation_streak"],
            hint_level=final_state["hint_level"],
            usage=usage.as_dict(),
            finish_reason=usage.finish_reason,
        ),
    }
    await log_turn(
        payload,
        final_state,
        response=body,
        intent=str(result.get("intent") or ""),
        started=started,
    )
    return body, 200
