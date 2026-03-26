import logging
from typing import Any

import azure.functions as func
from dotenv import load_dotenv

load_dotenv()

# HTTP v2 / FastAPI: Request + tipos de resposta têm de vir da extensão.
from azurefunctions.extensions.http.fastapi import (  # noqa: E402
    JSONResponse,
    Request,
    StreamingResponse,
)

from agents.rag.graph import COMPILED_RAG_GRAPH
from services.ping import ping_response
from services.tutor_help import process_help_request
from services.tutor_help_stream import format_sse, iter_help_sse

logger = logging.getLogger(__name__)

app = func.FunctionApp()


def _json_response(body: dict[str, Any], status: int = 200) -> JSONResponse:
    return JSONResponse(content=body, status_code=status)


@app.route(
    route="ping",
    methods=(func.HttpMethod.GET,),
    auth_level=func.AuthLevel.ANONYMOUS,
)
async def ping_endpoint(req: Request) -> JSONResponse:
    # Com a extensão HTTP/FastAPI carregada, ``req`` deve ser o Request da extensão.
    _ = req
    return _json_response(ping_response(), status=200)


@app.route(
    route="help",
    methods=(func.HttpMethod.POST,),
    auth_level=func.AuthLevel.ANONYMOUS,
)
async def help_endpoint(req: Request) -> JSONResponse:
    if req.method.upper() != "POST":
        return _json_response(
            {"error": "Use o método POST para enviar o pedido de ajuda."},
            status=405,
        )

    try:
        try:
            payload = await req.json()
        except Exception:
            return _json_response(
                {"error": "Corpo da requisição deve ser JSON válido."},
                status=400,
            )

        body, status = await process_help_request(payload)
        return _json_response(body, status=status)

    except Exception:
        logger.exception("Erro ao processar /api/help")
        return _json_response(
            {"error": "Erro interno ao processar a solicitação."},
            status=500,
        )


def _sse_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }


@app.route(
    route="help/stream",
    methods=(func.HttpMethod.POST,),
    auth_level=func.AuthLevel.ANONYMOUS,
)
async def help_stream_endpoint(req: Request) -> StreamingResponse:
    """Mesmo body que ``/help``, resposta ``text/event-stream`` (SSE)."""
    try:
        payload = await req.json()
    except Exception:
        payload = None

    async def body():
        if payload is None:
            yield format_sse(
                "error",
                {
                    "status": 400,
                    "error": "Corpo da requisição deve ser JSON válido.",
                },
            )
            return
        async for chunk in iter_help_sse(payload):
            yield chunk

    return StreamingResponse(
        body(),
        media_type="text/event-stream; charset=utf-8",
        headers=_sse_headers(),
    )


@app.route(
    route="portugol/ask",
    methods=(func.HttpMethod.POST,),
    auth_level=func.AuthLevel.ANONYMOUS,
)
async def portugol_ask(req: Request) -> JSONResponse:
    """RAG sobre `docs/portugol_referencia.md` (corpo JSON: `{\"question\": \"...\"}`)."""
    try:
        try:
            payload = await req.json()
        except Exception:
            return _json_response(
                {"error": "Corpo da requisição deve ser JSON válido."},
                status=400,
            )

        if not isinstance(payload, dict):
            return _json_response({"error": "JSON deve ser um objeto."}, status=400)

        question = payload.get("question")
        if question is None or (isinstance(question, str) and not question.strip()):
            return _json_response(
                {"error": "Campo \"question\" é obrigatório e não pode estar vazio."},
                status=400,
            )
        if not isinstance(question, str):
            return _json_response(
                {"error": "Campo \"question\" deve ser uma string."},
                status=400,
            )

        result = COMPILED_RAG_GRAPH.invoke(
            {"question": question.strip(), "context": [], "answer": ""}
        )
        return _json_response({"answer": result["answer"]}, status=200)

    except Exception:
        logger.exception("Erro ao processar /api/portugol/ask")
        return _json_response(
            {"error": "Erro interno ao processar a solicitação."},
            status=500,
        )
