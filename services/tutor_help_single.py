"""
Chamada única ao modelo, sem grafo: condições B (ablação) e C (referência neutra) da bancada.

A condição A da avaliação é o grafo completo, em ``POST /api/help``. Esta rota serve as outras
duas condições **pelo mesmo serviço**, com o mesmo contrato de entrada, o mesmo registro por
turno e o mesmo proxy, para que a comparação entre condições não seja confundida por diferença
de infraestrutura.

O que **não** corre aqui: roteador, analista, estrategista, comunicador, ferramentas de IDE, RAG
e ``suggest_documentation``. Não há memória entre chamadas — todo o contexto vem do corpo do
pedido. Não há heurística, pós-processamento nem filtro na saída: o que o modelo responde é o
dado da ablação. Não há recurso ao grafo em caso de falha — falha devolve erro HTTP e o harness
reexecuta.

Os dois prompts de sistema são literais congelados (``SYSTEM_PROMPTS``); o SHA-256 é calculado no
arranque, registrado no log e devolvido em ``tutorMeta.promptSha256``. Mudar o texto muda o hash
e a corrida deixa de ser comparável com as anteriores — é o que o harness verifica em
``GET /api/help/single/prompts`` antes de cada corrida.
"""

import hashlib
import logging
import time
from typing import Any

from agents.problem_context import (
    PROBLEM_SHA256,
    PROBLEM_TEMPLATE,
    build_problem_content,
    parse_problem_statement,
)
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.llm import chat_model_name

# Cliente de chat do comunicador: a fala do tutor comparada na condição A sai daqui, com estes
# parâmetros (modelo, temperatura, max_tokens). Importa-se a fábrica do cliente — nenhum prompt
# nem lógica do agente — para que B e C corram na configuração de produção sem constantes novas.
from agents.tutor import _communicator_llm
from services import interaction_log
from services.tutor_help import parse_help_payload

logger = logging.getLogger(__name__)

ENDPOINT = "/api/help/single"

#: Condição B — recorte de ``STRATEGIST_SYSTEM_TEMPLATE`` + ``COMMUNICATOR_DEBUG_TEMPLATE`` sem
#: as regras que pressupõem ferramentas, plano interno ou estado. Literal congelado: não
#: interpolar, não reformatar, não parametrizar por ambiente.
SOCRATIC_SYSTEM_PROMPT = """\
You are ADA, a Socratic programming logic tutor for Portugol.
Do not solve the problem for the student.
Reply with 1 or 2 concise sentences in Brazilian Portuguese that
invite reflection.

- Never output Portugol source code or complete fixes; ask questions
  only.
- Never hand the final code patch, even if the student insists or
  says they have no time.
- Escalation pace: keep the first 3 learner turns at observation or
  micro-comparison, and introduce the key concept only around turns
  4-5 if the learner is still blocked.
- Error-type focus: syntax focuses on malformed syntax;
  type_mismatch compares declared type vs assigned value type;
  undeclared_identifier focuses on declaration before use; logic
  focuses on intended behavior vs observed data flow.
- Be direct and logical; do not open with greetings or small talk.
- Never invent line numbers."""

#: Condição C — instrução única, sem qualquer orientação pedagógica. Literal congelado.
NEUTRAL_SYSTEM_PROMPT = """\
Você é um assistente de programação que ajuda estudantes com código Portugol."""

SYSTEM_PROMPTS: dict[str, str] = {
    "socratic": SOCRATIC_SYSTEM_PROMPT,
    "neutral": NEUTRAL_SYSTEM_PROMPT,
}

PROMPT_VARIANTS: tuple[str, ...] = ("socratic", "neutral")

#: Molde do contexto de código, comum às três condições da bancada. Congelado e versionado como
#: os prompts: a numeração das linhas determina o que o modelo consegue citar, logo determina o
#: resultado — não é detalhe de implementação. O SHA-256 acompanha cada turno.
CONTEXT_TEMPLATE = """\
Portugol code with 1-based line numbers:
```
{numbered_code}
```

Compiler error messages:
{errors_block}

Compiler error lines:
{compiler_lines_block}"""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


#: Identidade dos prompts na corrida: entra em ``tutorMeta`` e no registro por turno.
PROMPT_SHA256: dict[str, str] = {
    variant: _sha256(text) for variant, text in SYSTEM_PROMPTS.items()
}

#: Identidade do molde de contexto na corrida: entra em ``tutorMeta`` e no registro por turno.
CONTEXT_SHA256: str = _sha256(CONTEXT_TEMPLATE)

for _variant in PROMPT_VARIANTS:
    logger.info(
        "help/single: prompt congelado variant=%s sha256=%s",
        _variant,
        PROMPT_SHA256[_variant],
    )
logger.info("help/single: molde de contexto sha256=%s", CONTEXT_SHA256)


def _numbered_code(code: str) -> str:
    """Código com prefixo de linha 1-based, como o grafo o entrega ao modelo."""
    lines = code.splitlines()
    if not lines and not code.strip():
        return "(empty code)"
    if not lines:
        return "1 | "
    width = len(str(len(lines)))
    return "\n".join(f"{i + 1:{width}} | {line}" for i, line in enumerate(lines))


def build_context_content(
    code: str, errors: list[str], compiler_error_lines: list[int]
) -> str:
    """
    Contexto de código: preenche ``CONTEXT_TEMPLATE``. Igual nas três condições — entre B e C só
    muda o prompt de sistema. Nenhuma delas recebe descrição do defeito.
    """
    errors_block = (
        "\n".join(f"- {e}" for e in errors) if errors else "(no compiler error messages)"
    )
    compiler_lines_block = (
        ", ".join(str(n) for n in compiler_error_lines)
        if compiler_error_lines
        else "(no compiler error lines)"
    )
    return CONTEXT_TEMPLATE.format(
        numbered_code=_numbered_code(code),
        errors_block=errors_block,
        compiler_lines_block=compiler_lines_block,
    )


def _history_to_messages(history: list[dict]) -> list[HumanMessage | AIMessage]:
    """Mesma conversão que os agentes fazem na condição A (``agents.tutor``)."""
    messages: list[HumanMessage | AIMessage] = []
    for item in history:
        role = item.get("role", "")
        content = item.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=str(content)))
        elif role == "assistant":
            messages.append(AIMessage(content=str(content)))
        else:
            logger.warning("Papel de histórico ignorado: %s", role)
    return messages


def build_messages(
    variant: str,
    *,
    code: str,
    errors: list[str],
    compiler_error_lines: list[int],
    history: list[dict],
    problem_statement: str = "",
) -> list[SystemMessage | HumanMessage | AIMessage]:
    """
    ``[system(prompt congelado), user(contexto de código), *histórico]``.

    O histórico vai como mensagens de papel ``user``/``assistant``, a forma nativa da API de chat
    e a mesma que a condição A usa — a última mensagem é sempre o turno mais recente do
    estudante, que é o que o modelo está a responder. Sem histórico fica só o contexto; não se
    injeta turno sintético (a condição A injeta um, mas aqui seria inventar conteúdo que não veio
    do banco de itens).

    Fora do prompt por desenho: ``hintLevel`` (saída da decisão do estrategista), ``previousCode``
    e ``previousErrors`` (entradas do classificador de movimento) e ``studentName``. São entradas
    da política programática — dá-las a B devolveria à ablação a peça que se quer retirar.
    """
    mensagens: list[SystemMessage | HumanMessage | AIMessage] = [
        SystemMessage(content=SYSTEM_PROMPTS[variant]),
        HumanMessage(
            content=build_context_content(code, errors, compiler_error_lines)
        ),
    ]
    if problem_statement:
        mensagens.append(HumanMessage(content=build_problem_content(problem_statement)))
    mensagens.extend(_history_to_messages(history))
    return mensagens


def parse_prompt_variant(payload: Any) -> tuple[str | None, dict[str, Any] | None]:
    """``promptVariant`` é obrigatório: sem ele não há condição definida para o turno."""
    if not isinstance(payload, dict):
        return None, {"error": "O corpo JSON deve ser um objeto."}
    raw = payload.get("promptVariant")
    if isinstance(raw, str) and raw in SYSTEM_PROMPTS:
        return raw, None
    return None, {
        "error": (
            "O campo 'promptVariant' é obrigatório e deve ser "
            f"{' ou '.join(repr(v) for v in PROMPT_VARIANTS)}."
        )
    }


def _chunk_content_to_text(content: object) -> str:
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return str(content)


def _finish_reason(response: Any) -> str:
    """Motivo de paragem do modelo. ``length`` marca turno cortado no limite de tokens: em A o
    comunicador só traduz um plano interno, em B a mesma chamada tem de analisar, decidir e
    falar — um turno cortado seria classificado com diretividade errada, e o viés cairia todo
    de um lado da comparação. Mede-se; não se corrige o limite aqui."""
    meta = getattr(response, "response_metadata", None) or {}
    return str(meta.get("finish_reason") or "")


def _usage(response: Any) -> dict[str, int]:
    """Tokens do turno, como o proxy os reporta; zeros quando não vêm na resposta."""
    meta = getattr(response, "usage_metadata", None)
    if isinstance(meta, dict) and meta:
        return {
            "promptTokens": int(meta.get("input_tokens") or 0),
            "completionTokens": int(meta.get("output_tokens") or 0),
            "totalTokens": int(meta.get("total_tokens") or 0),
        }
    token_usage = (getattr(response, "response_metadata", None) or {}).get(
        "token_usage"
    ) or {}
    return {
        "promptTokens": int(token_usage.get("prompt_tokens") or 0),
        "completionTokens": int(token_usage.get("completion_tokens") or 0),
        "totalTokens": int(token_usage.get("total_tokens") or 0),
    }


async def _log_turn(
    payload: Any,
    *,
    session_id: str,
    variant: str,
    response: dict[str, Any],
    latency_ms: int,
    finish_reason: str = "",
    error: str | None = None,
) -> None:
    """Mesma linha NDJSON de ``/api/help``, mais ``promptVariant`` e ``promptSha256``.

    ``intent``, ``studentMovement`` e ``movementSource`` ficam vazios por desenho: não há
    roteamento nem política de contingência nesta rota.
    """
    if not interaction_log.is_enabled():
        return
    record = interaction_log.build_record(
        payload,
        endpoint=ENDPOINT,
        session_id=session_id,
        response=response,
        model=chat_model_name(),
        latency_ms=latency_ms,
        error=error,
        prompt_variant=variant,
        prompt_sha256=PROMPT_SHA256[variant],
        context_sha256=CONTEXT_SHA256,
        finish_reason=finish_reason,
    )
    await interaction_log.log_interaction(record)


def prompts_response() -> dict[str, Any]:
    """Prompts congelados e os seus hashes, para reprodutibilidade e conferência do harness."""
    return {
        "prompts": {
            variant: {
                "text": SYSTEM_PROMPTS[variant],
                "sha256": PROMPT_SHA256[variant],
            }
            for variant in PROMPT_VARIANTS
        },
        "context": {"text": CONTEXT_TEMPLATE, "sha256": CONTEXT_SHA256},
        "problem": {"text": PROBLEM_TEMPLATE, "sha256": PROBLEM_SHA256},
    }


async def process_help_single_request(payload: Any) -> tuple[dict[str, Any], int]:
    """
    Uma chamada ao modelo com o prompt da variante pedida. Devolve ``(corpo_dict, status_http)``.

    Validação idêntica à de ``/api/help``: o mesmo corpo é aceito pelas duas rotas. O movimento
    que ``parse_help_payload`` classifica é descartado — alimenta a política de contingência do
    grafo, que não corre aqui.
    """
    variant, err_body = parse_prompt_variant(payload)
    if variant is None:
        assert err_body is not None
        return err_body, 400

    state, err_body, status = parse_help_payload(payload)
    if state is None:
        assert err_body is not None
        return err_body, status

    messages = build_messages(
        variant,
        code=state["code"],
        errors=state["errors"],
        compiler_error_lines=state["compiler_error_lines"],
        history=state["history"],
        problem_statement=state.get("problem_statement", ""),
    )

    started = time.monotonic()
    try:
        response = await _communicator_llm().ainvoke(messages)
    except Exception as exc:
        logger.exception("Falha na chamada única (%s, variant=%s)", ENDPOINT, variant)
        await _log_turn(
            payload,
            session_id=state["session_id"],
            variant=variant,
            response={},
            latency_ms=int((time.monotonic() - started) * 1000),
            error=f"{type(exc).__name__}: {exc}",
        )
        raise

    latency_ms = int((time.monotonic() - started) * 1000)
    finish_reason = _finish_reason(response)
    body = {
        "message": _chunk_content_to_text(response.content).strip(),
        "actions": [],
        "tutorMeta": {
            "model": chat_model_name(),
            "promptVariant": variant,
            "promptSha256": PROMPT_SHA256[variant],
            "contextSha256": CONTEXT_SHA256,
            "problemSha256": PROBLEM_SHA256,
            "usage": _usage(response),
            "finishReason": finish_reason,
            "latencyMs": latency_ms,
        },
    }
    await _log_turn(
        payload,
        session_id=state["session_id"],
        variant=variant,
        response=body,
        latency_ms=latency_ms,
        finish_reason=finish_reason,
    )
    return body, 200
