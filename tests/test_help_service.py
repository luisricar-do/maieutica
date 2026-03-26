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
        }
    )
    with patch("services.tutor_help.tutor_graph", mock_graph):
        body, status = await process_help_request(
            {"code": "escreva(1)", "errors": [], "history": []}
        )
    assert status == 200
    assert body["message"] == "Pergunta?"
    assert body["diagnosis"]["errorType"] == "none"
    mock_graph.ainvoke.assert_awaited_once()
