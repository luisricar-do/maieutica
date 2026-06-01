"""
Pedido de ajuda socrática: valida o payload, corre o grafo LangGraph e devolve o corpo JSON + código HTTP.
"""

import logging
from typing import Any, TypedDict

from agents.graph import tutor_graph

logger = logging.getLogger(__name__)


def build_tutor_meta_from_actions(actions: Any) -> dict[str, Any]:
    """
    Metadados de política de conversa para o cliente (IDE).

    Quando o estrategista emite ``mark_bug_resolved``, a UI pode encerrar a conversa
    atual e iniciar uma nova (ex.: overlay imersivo).
    """
    if not isinstance(actions, list):
        return {"suggestedConversationEnd": False, "endReason": "none"}
    for item in actions:
        if isinstance(item, dict) and item.get("type") == "mark_bug_resolved":
            return {
                "suggestedConversationEnd": True,
                "endReason": "bug_resolved",
            }
    return {"suggestedConversationEnd": False, "endReason": "none"}


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
    data_flow_context = _parse_ast_summary(payload.get("dataFlowContext"))

    initial_state: TutorHelpState = {
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
    }
    return initial_state, None, 200


async def process_help_request(payload: Any) -> tuple[dict[str, Any], int]:
    """
    Processa o body JSON já desserializado.

    Devolve ``(corpo_dict, status_http)``.
    """
    initial_state, err_body, status = parse_help_payload(payload)
    if initial_state is None:
        assert err_body is not None
        return err_body, status

    try:
        result = await tutor_graph.ainvoke(initial_state)
    except Exception:
        logger.exception("Falha ao executar o grafo do tutor (process_help_request)")
        raise

    actions = result.get("actions") or []
    if not isinstance(actions, list):
        actions = []

    return (
        {
            "message": result.get("tutor_response", ""),
            "diagnosis": result.get("diagnosis", {}),
            "actions": actions,
            "tutorMeta": build_tutor_meta_from_actions(actions),
        },
        200,
    )
