from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.tutor_help import process_help_request


@pytest.mark.asyncio
async def test_process_help_rejects_empty_code() -> None:
    body, status = await process_help_request(
        {"code": "   ", "errors": [], "history": []}
    )
    assert status == 400
    assert "code" in body.get("error", "").lower()


@pytest.mark.asyncio
async def test_process_help_rejects_non_dict_payload() -> None:
    body, status = await process_help_request([])
    assert status == 400
    assert "error" in body


@pytest.mark.asyncio
async def test_process_help_success() -> None:
    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(
        return_value={
            "tutor_response": "Pergunta?",
            "diagnosis": {"errorType": "none"},
            "actions": [],
        }
    )
    with patch("services.tutor_help.tutor_graph", mock_graph):
        body, status = await process_help_request(
            {"code": "escreva(1)", "errors": [], "history": []}
        )
    assert status == 200
    assert body["message"] == "Pergunta?"
    assert body["diagnosis"]["errorType"] == "none"
    assert body["actions"] == []
    assert body["tutorMeta"]["suggestedConversationEnd"] is False
    assert body["tutorMeta"]["endReason"] == "none"
    mock_graph.ainvoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_help_passes_include_documentation_to_graph() -> None:
    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(
        return_value={
            "tutor_response": "ok",
            "diagnosis": {"errorType": "none"},
            "actions": [],
        }
    )
    with patch("services.tutor_help.tutor_graph", mock_graph):
        await process_help_request(
            {
                "code": "escreva(1)",
                "errors": [],
                "history": [],
                "includeDocumentation": True,
            }
        )
    call_args = mock_graph.ainvoke.await_args
    state = call_args[0][0]
    assert state["include_documentation"] is True
    assert state["documentation_context"] == []
    assert state["strategist_plan"] == ""
    assert state["intent"] == ""
    assert state["hint_level"] == 1
    assert state["student_name"] == ""


@pytest.mark.asyncio
async def test_process_help_includes_tutor_meta_bug_resolved() -> None:
    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(
        return_value={
            "tutor_response": "Parabéns!",
            "diagnosis": {"errorType": "none"},
            "actions": [{"type": "mark_bug_resolved", "payload": {}}],
        }
    )
    with patch("services.tutor_help.tutor_graph", mock_graph):
        body, status = await process_help_request(
            {"code": "escreva(1)", "errors": [], "history": []}
        )
    assert status == 200
    assert body["tutorMeta"]["suggestedConversationEnd"] is True
    assert body["tutorMeta"]["endReason"] == "bug_resolved"
    assert len(body["actions"]) == 1
