import logging
from typing import Any

import azure.functions as func
from dotenv import load_dotenv

load_dotenv()

# HTTP v2 / FastAPI: Request + tipos de resposta têm de vir da extensão.
from azurefunctions.extensions.http.fastapi import (  # noqa: E402
    HTMLResponse,
    JSONResponse,
    Request,
    Response,
    StreamingResponse,
)

from agents.config import verificar_configuracao
from agents.rag.graph import get_compiled_rag_graph
from services.coletas_service import (
    coleta_action,
    export_coleta,
    session_action,
    session_conversation,
)
from services.painel_service import (
    commands_for_ide,
    create_command,
    list_sessions,
    painel_html,
)
from services.ping import ping_response
from services.telemetry import process_telemetry_request
from services.tutor_help import process_help_request
from services.tutor_help_single import (
    process_help_single_request,
    prompts_response,
)
from services.tutor_help_stream import format_sse, iter_help_sse

logger = logging.getLogger(__name__)

# As chaves de política são lidas aqui, no carregamento do worker: uma App Setting inválida
# derruba o arranque em vez de degradar em silêncio para o padrão e produzir uma coleta que
# contradiz o que §4.3 declara.
verificar_configuracao()

app = func.FunctionApp()


def _client_ip(req: Request) -> str:
    """IP de quem chama; atrás do ingress do Container App vem em ``X-Forwarded-For``."""
    forwarded = (req.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    return forwarded or (req.client.host if req.client else "")


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


@app.route(
    route="help/single",
    methods=(func.HttpMethod.POST,),
    auth_level=func.AuthLevel.ANONYMOUS,
)
async def help_single_endpoint(req: Request) -> JSONResponse:
    """
    Uma chamada ao modelo, sem grafo: condições B e C da bancada (Capítulo 4).

    Mesmo corpo de ``/api/help``, mais ``promptVariant`` (``socratic`` | ``neutral``).
    Sem ``/stream``: a bancada é síncrona. Falha devolve erro HTTP — não há recurso ao grafo.
    """
    try:
        try:
            payload = await req.json()
        except Exception:
            return _json_response(
                {"error": "Corpo da requisição deve ser JSON válido."},
                status=400,
            )

        body, status = await process_help_single_request(payload)
        return _json_response(body, status=status)

    except Exception:
        logger.exception("Erro ao processar /api/help/single")
        return _json_response(
            {"error": "Erro interno ao processar a solicitação."},
            status=500,
        )


@app.route(
    route="help/single/prompts",
    methods=(func.HttpMethod.GET,),
    auth_level=func.AuthLevel.ANONYMOUS,
)
async def help_single_prompts_endpoint(req: Request) -> JSONResponse:
    """Prompts congelados de B e C e os seus SHA-256 (reprodutibilidade e conferência)."""
    _ = req
    return _json_response(prompts_response(), status=200)


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
    route="telemetry",
    methods=(func.HttpMethod.POST,),
    auth_level=func.AuthLevel.ANONYMOUS,
)
async def telemetry_endpoint(req: Request) -> JSONResponse:
    """
    Recebe lotes de eventos da IDE e grava NDJSON no Blob Storage.

    Em 503 (sem armazenamento configurado) ou 500, o cliente deve manter o lote
    localmente e repetir mais tarde.
    """
    try:
        try:
            payload = await req.json()
        except Exception:
            return _json_response(
                {"error": "Corpo da requisição deve ser JSON válido."},
                status=400,
            )

        body, status = await process_telemetry_request(payload)
        return _json_response(body, status=status)

    except Exception:
        logger.exception("Erro ao processar /api/telemetry")
        return _json_response(
            {"error": "Erro interno ao processar a solicitação."},
            status=500,
        )


# --- Painel do condutor da coleta e canal de comandos para a IDE -------------------------
# Prefixo ``painel``: rotas ``admin/...`` conflitam com as embutidas do host do Functions.


@app.route(
    route="painel",
    methods=(func.HttpMethod.GET,),
    auth_level=func.AuthLevel.ANONYMOUS,
)
async def painel_page_endpoint(req: Request) -> HTMLResponse:
    """Página do condutor (sem dados; o token é pedido no navegador)."""
    _ = req
    try:
        return HTMLResponse(
            content=painel_html(),
            headers={"Cache-Control": "no-store"},
        )
    except Exception:
        logger.exception("Erro ao servir /api/painel")
        return HTMLResponse(content="Erro interno.", status_code=500)


@app.route(
    route="painel/sessoes",
    methods=(func.HttpMethod.GET,),
    auth_level=func.AuthLevel.ANONYMOUS,
)
async def painel_sessions_endpoint(req: Request) -> JSONResponse:
    """Resumo das sessões recentes (``Authorization: Bearer <STUDY_ADMIN_TOKEN>``)."""
    try:
        body, status = await list_sessions(
            req.headers.get("authorization"), req.query_params, _client_ip(req)
        )
        return _json_response(body, status=status)
    except Exception:
        logger.exception("Erro ao processar /api/painel/sessoes")
        return _json_response(
            {"error": "Erro interno ao processar a solicitação."},
            status=500,
        )


@app.route(
    route="painel/comandos",
    methods=(func.HttpMethod.POST,),
    auth_level=func.AuthLevel.ANONYMOUS,
)
async def painel_commands_endpoint(req: Request) -> JSONResponse:
    """Grava um comando do condutor para a IDE de uma sessão (ou uma nota de incidente)."""
    try:
        try:
            payload = await req.json()
        except Exception:
            # Corpo inválido vira 400 na validação, depois da autenticação (401 primeiro).
            payload = None
        body, status = await create_command(
            req.headers.get("authorization"), payload, _client_ip(req)
        )
        return _json_response(body, status=status)
    except Exception:
        logger.exception("Erro ao processar /api/painel/comandos")
        return _json_response(
            {"error": "Erro interno ao processar a solicitação."},
            status=500,
        )


async def _json_body(req: Request) -> Any:
    """Corpo JSON ou ``None``: corpo inválido vira 400 na validação, depois da autenticação."""
    try:
        return await req.json()
    except Exception:
        return None


@app.route(
    route="painel/coletas",
    methods=(func.HttpMethod.POST,),
    auth_level=func.AuthLevel.ANONYMOUS,
)
async def painel_coletas_endpoint(req: Request) -> JSONResponse:
    """Cria, abre, encerra, edita ou exclui uma coleta (``{"acao": ...}``)."""
    try:
        body, status = await coleta_action(
            req.headers.get("authorization"), await _json_body(req), _client_ip(req)
        )
        return _json_response(body, status=status)
    except Exception:
        logger.exception("Erro ao processar /api/painel/coletas")
        return _json_response(
            {"error": "Erro interno ao processar a solicitação."},
            status=500,
        )


@app.route(
    route="painel/sessoes/acoes",
    methods=(func.HttpMethod.POST,),
    auth_level=func.AuthLevel.ANONYMOUS,
)
async def painel_session_actions_endpoint(req: Request) -> JSONResponse:
    """Move sessões de coleta, descarta, restaura ou apaga de vez (só da lixeira)."""
    try:
        body, status = await session_action(
            req.headers.get("authorization"), await _json_body(req), _client_ip(req)
        )
        return _json_response(body, status=status)
    except Exception:
        logger.exception("Erro ao processar /api/painel/sessoes/acoes")
        return _json_response(
            {"error": "Erro interno ao processar a solicitação."},
            status=500,
        )


@app.route(
    route="painel/exportar",
    methods=(func.HttpMethod.GET,),
    auth_level=func.AuthLevel.ANONYMOUS,
)
async def painel_export_endpoint(req: Request) -> Response:
    """Arquivo de uma coleta: ``?coleta=<id>&formato=eventos|interacoes|resumo``."""
    try:
        body, status, media_type, filename = await export_coleta(
            req.headers.get("authorization"), req.query_params, _client_ip(req)
        )
        if isinstance(body, dict):
            return _json_response(body, status=status)
        return Response(
            content=body,
            status_code=status,
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
            },
        )
    except Exception:
        logger.exception("Erro ao processar /api/painel/exportar")
        return _json_response(
            {"error": "Erro interno ao processar a solicitação."},
            status=500,
        )


@app.route(
    route="painel/conversa",
    methods=(func.HttpMethod.GET,),
    auth_level=func.AuthLevel.ANONYMOUS,
)
async def painel_conversation_endpoint(req: Request) -> JSONResponse:
    """Turnos do tutor de uma sessão (``?sessao=<sessionId>``), para ler no painel."""
    try:
        body, status = await session_conversation(
            req.headers.get("authorization"), req.query_params, _client_ip(req)
        )
        return _json_response(body, status=status)
    except Exception:
        logger.exception("Erro ao processar /api/painel/conversa")
        return _json_response(
            {"error": "Erro interno ao processar a solicitação."},
            status=500,
        )


@app.route(
    route="coleta/comandos",
    methods=(func.HttpMethod.GET,),
    auth_level=func.AuthLevel.ANONYMOUS,
)
async def coleta_commands_endpoint(req: Request) -> JSONResponse:
    """Polling da IDE do aluno: comandos da sua sessão com ``id > after``."""
    try:
        body, status = await commands_for_ide(req.query_params)
        return _json_response(body, status=status)
    except Exception:
        logger.exception("Erro ao processar /api/coleta/comandos")
        return _json_response(
            {"error": "Erro interno ao processar a solicitação."},
            status=500,
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

        result = get_compiled_rag_graph().invoke(
            {"question": question.strip(), "context": [], "answer": ""}
        )
        return _json_response({"answer": result["answer"]}, status=200)

    except Exception:
        logger.exception("Erro ao processar /api/portugol/ask")
        return _json_response(
            {"error": "Erro interno ao processar a solicitação."},
            status=500,
        )
