"""
Pedido de ajuda socrática: valida o payload, corre o grafo LangGraph e devolve o corpo JSON + código HTTP.
"""

import logging
from typing import Any, TypedDict

from agents.graph import tutor_graph

logger = logging.getLogger(__name__)


class TutorHelpState(TypedDict):
    code: str
    errors: list[str]
    history: list[dict]
    diagnosis: dict
    tutor_response: str


def parse_help_payload(payload: Any) -> tuple[TutorHelpState | None, dict[str, Any] | None, int]:
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

    initial_state: TutorHelpState = {
        "code": code,
        "errors": errors_str,
        "history": history_dicts,
        "diagnosis": {},
        "tutor_response": "",
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

    return (
        {
            "message": result.get("tutor_response", ""),
            "diagnosis": result.get("diagnosis", {}),
        },
        200,
    )
