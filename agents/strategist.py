"""Agente Pedagogical Strategist: lógica, diagnóstico e chamadas a ferramentas da IDE (sem falar com o aluno)."""

import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool

from agents.analyst import Diagnosis
from agents.llm import create_chat_client

logger = logging.getLogger(__name__)

# Fallbacks quando o modelo devolve tool_calls mas `content` vazio (plano interno ausente).
TOOL_ONLY_FALLBACK_MESSAGE_PT = (
    "Diretriz: guie o aluno a observar os destaques visuais no editor e a descrever o que nota "
    "(sem dar a solução). Uma pergunta socrática curta sobre o que abre vs fecha ou declaração vs uso."
)
TOOL_ONLY_FALLBACK_CLEAR_PT = (
    "Diretriz: o foco mudou ou o bug foi resolvido; convide o aluno a dizer o que quer tentar a seguir, "
    "sem mencionar limpeza de destaques."
)
TOOL_ONLY_FALLBACK_MIXED_CLEAR_AND_VISUAL_PT = TOOL_ONLY_FALLBACK_MESSAGE_PT
_TOOL_ONLY_VISUAL_TOOLS = frozenset(
    {
        "highlight_line",
        "highlight_variable",
        "add_inline_comment",
        "run_code_with_watch",
        "compare_lines",
    },
)


def _tool_names_from_calls(tool_calls: object) -> list[str]:
    names: list[str] = []
    if not tool_calls:
        return names
    for tc in tool_calls:
        if isinstance(tc, dict):
            n = str(tc.get("name") or "")
        else:
            n = str(getattr(tc, "name", "") or "")
        if n:
            names.append(n)
    return names


def _fallback_plan_pt_for_tool_calls(tool_calls: object) -> str:
    names = _tool_names_from_calls(tool_calls)
    if not names:
        return TOOL_ONLY_FALLBACK_MESSAGE_PT

    non_clear = [n for n in names if n != "clear_highlights"]
    if not non_clear:
        return TOOL_ONLY_FALLBACK_CLEAR_PT

    has_visual = bool(_TOOL_ONLY_VISUAL_TOOLS.intersection(non_clear))
    had_clear = any(n == "clear_highlights" for n in names)

    if has_visual and had_clear:
        return TOOL_ONLY_FALLBACK_MIXED_CLEAR_AND_VISUAL_PT
    if has_visual:
        return TOOL_ONLY_FALLBACK_MESSAGE_PT

    if set(non_clear) <= {"mark_bug_resolved"}:
        return (
            "Diretriz: celebrar a resolução pelo aluno; uma pergunta curta sobre o próximo passo "
            "(sem mencionar limpeza de destaques)."
        )
    if "escalate_to_direct_help" in non_clear:
        return (
            "Diretriz: ser um pouco mais direto na próxima dica; pedir que diga em que ponto travou, "
            "sem dar a solução completa."
        )
    return (
        "Diretriz: confira se o ajuste no editor apareceu como esperado; uma pergunta socrática curta."
    )


@tool
def highlight_line(line: int, color: str) -> str:
    """WHEN to use: the learner must look at one specific line (syntax or logic     errors, `escreva`,
    declarations, loop headers) or says they cannot find where to edit ("onde?", "não acho").
    HOW: pass the 1-based line number from `<learner_code>` and `color`: use `warning` for bugs /
    errors and `info` for neutral pointers. If your Portuguese chat text says you highlighted a line,
    you MUST call this tool in the same assistant turn."""
    return "ok"


@tool
def highlight_variable(variable_name: str) -> str:
    """WHEN to use: the learner is confused about a variable (scope, initialization, or where it
    changes) and needs to see every occurrence at once. HOW: pass the exact identifier string from
    the learner code (e.g. `i`, `soma`). Pair with a short Portuguese question about what they
    notice across those places."""
    return "ok"


@tool
def clear_highlights() -> str:
    """WHEN to use: old tutor marks would confuse a new focus line, the topic changed, the bug is
    fixed, or `active_tutor_decorations` is greater than zero and you are closing the debugging arc.
    Call this **before** new highlights when stale marks hurt clarity. HOW: invoke with no arguments
    as the first tool in the turn when needed. Never tell the learner in chat that you removed
    highlights—this cleanup is silent."""
    return "ok"


@tool
def add_inline_comment(line: int, comment: str) -> str:
    """WHEN to use: you want a reflective **question** attached to one line inside the editor so the
    learner reads it next to the code. HOW: pass the 1-based line index from `<learner_code>` and
    `comment` written in **Portuguese** (never the answer). If chat mentions leaving a comment in the
    code, you MUST call this tool in the same turn."""
    return "ok"


@tool
def run_code_with_watch(variables: list[str]) -> str:
    """WHEN to use: the learner should **see** runtime values step by step (loops, conditions,
    accumulator variables) without you explaining the fix. HOW: pass a list of variable names to
    observe; rerun may open the watch UI in the IDE. Use together with one Portuguese question about
    what they notice."""
    return "ok"


@tool
def mark_bug_resolved() -> str:
    """WHEN to use: the learner fixed the problem on their own and you are celebrating closure.
    HOW: in the **same** turn, call `clear_highlights` first when tutor marks may still be visible,
    then call this tool. Chat stays celebratory in Portuguese; do not mention clearing highlights."""
    return "ok"


@tool
def escalate_to_direct_help(reason: str) -> str:
    """WHEN to use: about five or more back-and-forth turns with **no** progress and a softer hint is
    not working. HOW: pass a short `reason` for logs/UI; guidance may get more concrete but still
    must not give the full solution."""
    return "ok"


@tool
def compare_lines(line1: int, line2: int) -> str:
    """Destaca duas linhas de código simultaneamente para que o aluno compare ambas. Extremamente
    útil para problemas de escopo, variáveis não inicializadas ou delimitadores (ex: comparar a
    linha onde a variável foi declarada com a linha onde está sendo usada)."""
    return "ok"


@tool
def suggest_documentation(topic: str) -> str:
    """Abre o painel de documentação da IDE no tópico especificado. Use isso quando o aluno não
    souber a sintaxe de algo básico (ex: 'vetores', 'escreva', 'leia', 'laco_enquanto'). Tópicos
    válidos: 'variaveis', 'tipos', 'escreva', 'leia', 'se_senao', 'enquanto', 'para', 'vetores',
    'matrizes'."""
    return "ok"


STRATEGIST_TOOLS = [
    highlight_line,
    highlight_variable,
    clear_highlights,
    add_inline_comment,
    run_code_with_watch,
    mark_bug_resolved,
    escalate_to_direct_help,
    compare_lines,
    suggest_documentation,
]

# Alias para compatibilidade com código que referia TUTOR_TOOLS
TUTOR_TOOLS = STRATEGIST_TOOLS


def _documentation_context_block(chunks: list[str]) -> str:
    if not chunks:
        return ""
    body = "\n\n---\n\n".join(chunks)
    return (
        "\n<documentation_reference>\n"
        "Use only to align IDE tool choices and the internal plan with Portugol syntax and semantics; "
        "do not copy literal documentation blocks into the plan.\n\n"
        f"{body}\n"
        "</documentation_reference>\n"
    )


STRATEGIST_SYSTEM_TEMPLATE = """You are the Pedagogical Strategist. You DO NOT talk to the student.
Your job is to analyze the code and the diagnosis, invoke the necessary IDE tools (like highlight_line or compare_lines), and output a short internal message in the `content` field with the exact Socratic angle the Communicator Agent should use.

Rules:
- Never write learner-facing chat. The Communicator will speak to the student in Brazilian Portuguese.
- You MUST use `bind_tools` / tool calls for every IDE action needed (highlights, comments, compare, docs, watch, clear, mark resolved, escalate).
- The `content` field must be a concise internal directive in English or Portuguese (internal only): which lines were highlighted or compared, what single discovery question the Communicator should ask, and any constraint (no full solution).
- If `active_tutor_decorations` > 0 and the topic changes or the bug is fixed, call `clear_highlights` before new highlights when stale marks would confuse.
- Prefer `compare_lines` for declaration vs usage; prefer `highlight_line` on the analyst focus line for first error turns.

<diagnosis_context>
- Error Type: {error_type}
- Affected Variable: {affected_variable}
- Internal Technical Description: {error_description}
- Suggested Pedagogical Angle: {hint_angle}
- Severity: {severity}
- Analyst focus line (for highlights when relevant): {error_line_hint}
</diagnosis_context>

<editor_state>
- Active Tutor Highlights in IDE: {active_tutor_decorations}
</editor_state>

<learner_code>
{numbered_code}
</learner_code>
"""


def _strategist_llm():
    return create_chat_client(max_tokens=400, temperature=0.3).bind_tools(STRATEGIST_TOOLS)


def _diagnosis_to_template_vars(diagnosis: Diagnosis, active_tutor_decorations: int) -> dict[str, str]:
    av = diagnosis.get("affectedVariable")
    el = diagnosis.get("errorLine")
    if isinstance(el, int) and el >= 1:
        error_line_hint = str(el)
    else:
        error_line_hint = "not identified"
    ad = max(0, active_tutor_decorations)
    return {
        "error_type": str(diagnosis.get("errorType", "none")),
        "affected_variable": av if av is not None else "",
        "hint_angle": str(diagnosis.get("hintAngle", "")),
        "severity": str(diagnosis.get("severity", "low")),
        "error_line_hint": error_line_hint,
        "error_description": str(diagnosis.get("errorDescription", "")),
        "active_tutor_decorations": str(ad),
    }


def _numbered_code(code: str) -> str:
    """Code with 1-based line prefix, aligned with the learner editor."""
    lines = code.splitlines()
    if not lines and not code.strip():
        return "(empty code)"
    if not lines:
        return "1 | "
    width = len(str(len(lines)))
    return "\n".join(f"{i + 1:{width}} | {line}" for i, line in enumerate(lines))


def _build_strategist_system_content(
    diagnosis: Diagnosis,
    code: str,
    active_tutor_decorations: int,
    documentation_context: list[str] | None = None,
) -> str:
    vars_map = _diagnosis_to_template_vars(diagnosis, active_tutor_decorations)
    vars_map["numbered_code"] = _numbered_code(code)
    system_content = STRATEGIST_SYSTEM_TEMPLATE.format(**vars_map)
    return system_content + _documentation_context_block(documentation_context or [])


def _history_to_messages(history: list[dict]) -> list[HumanMessage | AIMessage]:
    messages: list[HumanMessage | AIMessage] = []
    for item in history:
        role = item.get("role", "")
        content = item.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=str(content)))
        elif role == "assistant":
            messages.append(AIMessage(content=str(content)))
        else:
            logger.warning("Unknown history role ignored: %s", role)
    return messages


def _strategist_lc_messages(
    diagnosis: Diagnosis,
    history: list[dict],
    code: str,
    active_tutor_decorations: int,
    documentation_context: list[str] | None = None,
) -> list[SystemMessage | HumanMessage | AIMessage]:
    lc_messages: list[SystemMessage | HumanMessage | AIMessage] = [
        SystemMessage(
            content=_build_strategist_system_content(
                diagnosis,
                code,
                active_tutor_decorations,
                documentation_context=documentation_context,
            )
        ),
    ]
    hist_msgs = _history_to_messages(history)
    if not hist_msgs:
        lc_messages.append(HumanMessage(content="Analyze and plan IDE tools for this help request."))
    else:
        lc_messages.extend(hist_msgs)
    return lc_messages


def _chunk_content_to_text(content: object) -> str:
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return str(content)


def _tool_call_to_action(tc: object) -> dict[str, Any] | None:
    if isinstance(tc, dict):
        name = tc.get("name") or ""
        args = tc.get("args")
        if args is None:
            args = {}
    else:
        name = getattr(tc, "name", "") or ""
        args = getattr(tc, "args", None)
        if args is None:
            args = {}
    if not name:
        return None
    return {"type": name, "payload": args}


async def run_strategist(
    diagnosis: Diagnosis,
    history: list[dict],
    code: str,
    active_tutor_decorations: int = 0,
    *,
    documentation_context: list[str] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """
    Executa o estrategista: devolve (ações IDE formatadas, plano interno para o comunicador).
    """
    llm = _strategist_llm()
    lc_messages = _strategist_lc_messages(
        diagnosis,
        history,
        code,
        active_tutor_decorations,
        documentation_context=documentation_context,
    )
    response = await llm.ainvoke(lc_messages)
    tool_calls = getattr(response, "tool_calls", None) or []
    actions: list[dict[str, Any]] = []
    for tc in tool_calls:
        action = _tool_call_to_action(tc)
        if action is not None:
            actions.append(action)

    plan_text = _chunk_content_to_text(response.content).strip()
    if not plan_text and tool_calls:
        logger.warning(
            "Strategist returned tool calls without plan text; using fallback (n_tools=%d)",
            len(tool_calls),
        )
        plan_text = _fallback_plan_pt_for_tool_calls(tool_calls)
    return actions, plan_text
