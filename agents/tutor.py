"""Comunicador ADA: traduz o plano do estrategista em texto empático (sem ferramentas)."""

import logging
from collections.abc import AsyncIterator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.llm import create_chat_client

logger = logging.getLogger(__name__)

COMMUNICATOR_DEBUG_TEMPLATE = """You are ADA, a Socratic programming logic tutor for Portugol.
Do not solve the problem for the student.
You receive a <strategist_plan> from the internal pedagogical engine.
Your ONLY job is to translate that strategy into 1 or 2 concise sentences in Brazilian Portuguese that invite reflection.

Debugging / error context — tone rules:
- Be direct and logical; avoid generic social greetings ("Oi", "Olá", "Tudo bem", small talk, or openings whose only purpose is politeness).
- Do not start with chit-chat; begin from the observation or question implied by the plan.
- If {student_name} is non-empty, you may use the first name once only when it fits naturally in a pedagogical sentence; never force a greeting.

If the strategy mentions highlighted lines, your message MUST reflect that smoothly (without inventing line numbers).
Never invent line numbers. Rely entirely on the <strategist_plan>.
Never output Portugol code blocks or complete fixes; ask questions only.

<learner_context>
Student display name (optional): {student_name}
Hint level from UI (1=subtle … 3=more concrete): {hint_level}
Cursor (if known): line {cursor_line} column {cursor_column}
AST/editor summary: {ast_summary}
Data flow from IDE (optional): {data_flow_context}
</learner_context>

<strategist_plan>
{strategist_plan}
</strategist_plan>
"""

COMMUNICATOR_CASUAL_TEMPLATE = """You are ADA, a warm programming tutor persona for Portugol.
The student is not asking for debugging right now (greeting, thanks, or chat).
Respond briefly in Brazilian Portuguese with warmth and encouragement. Do not analyze code or errors unless they explicitly ask.
Keep it to 1–3 short sentences.

<internal_hint>
{strategist_plan}
</internal_hint>
"""

COMMUNICATOR_THEORY_TEMPLATE = """You are ADA, a warm Portugol tutor. The student asked a conceptual question.
Use the documentation excerpts below as your main factual basis. Do not dump the docs; explain clearly in Brazilian Portuguese.
Keep the Socratic method: after a short explanation, end with one thoughtful question that connects the idea to their practice (e.g. their current program), without solving tasks for them.

<documentation>
{documentation}
</documentation>
"""


def _communicator_llm():
    return create_chat_client(max_tokens=300, temperature=0.7)


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


def _build_system_content(
    strategist_plan: str,
    intent: str,
    documentation_context: list[str],
    *,
    student_name: str = "",
    hint_level: int = 1,
    cursor_line: int | None = None,
    cursor_column: int | None = None,
    ast_summary: str = "",
    data_flow_context: str = "",
) -> str:
    if intent == "CASUAL":
        return COMMUNICATOR_CASUAL_TEMPLATE.format(strategist_plan=strategist_plan)
    if intent == "THEORY":
        docs_text = "\n\n---\n\n".join(documentation_context) if documentation_context else "(Nenhum trecho recuperado; responda com cuidado e uma pergunta socrática.)"
        return COMMUNICATOR_THEORY_TEMPLATE.format(documentation=docs_text)
    name = student_name.strip()
    hl = max(1, min(3, int(hint_level)))
    cl = str(cursor_line) if isinstance(cursor_line, int) and cursor_line >= 1 else "n/a"
    cc = str(cursor_column) if isinstance(cursor_column, int) and cursor_column >= 1 else "n/a"
    ast = ast_summary.strip() if ast_summary.strip() else "(none)"
    dfc = data_flow_context.strip() if data_flow_context.strip() else "(none)"
    return COMMUNICATOR_DEBUG_TEMPLATE.format(
        strategist_plan=strategist_plan,
        student_name=name if name else "(none)",
        hint_level=str(hl),
        cursor_line=cl,
        cursor_column=cc,
        ast_summary=ast,
        data_flow_context=dfc,
    )


def _communicator_lc_messages(
    strategist_plan: str,
    history: list[dict],
    *,
    intent: str = "DEBUG",
    documentation_context: list[str] | None = None,
    student_name: str = "",
    hint_level: int = 1,
    cursor_line: int | None = None,
    cursor_column: int | None = None,
    ast_summary: str = "",
    data_flow_context: str = "",
) -> list[SystemMessage | HumanMessage | AIMessage]:
    docs = documentation_context if documentation_context is not None else []
    lc_messages: list[SystemMessage | HumanMessage | AIMessage] = [
        SystemMessage(
            content=_build_system_content(
                strategist_plan,
                intent,
                docs,
                student_name=student_name,
                hint_level=hint_level,
                cursor_line=cursor_line,
                cursor_column=cursor_column,
                ast_summary=ast_summary,
                data_flow_context=data_flow_context,
            ),
        ),
    ]
    hist_msgs = _history_to_messages(history)
    if not hist_msgs:
        lc_messages.append(HumanMessage(content="Preciso de ajuda com meu código."))
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


async def run_communicator(
    strategist_plan: str,
    history: list[dict],
    *,
    intent: str = "DEBUG",
    documentation_context: list[str] | None = None,
    student_name: str = "",
    hint_level: int = 1,
    cursor_line: int | None = None,
    cursor_column: int | None = None,
    ast_summary: str = "",
    data_flow_context: str = "",
) -> str:
    """Gera a mensagem final da ADA a partir do plano interno do estrategista."""
    llm = _communicator_llm()
    lc_messages = _communicator_lc_messages(
        strategist_plan,
        history,
        intent=intent,
        documentation_context=documentation_context,
        student_name=student_name,
        hint_level=hint_level,
        cursor_line=cursor_line,
        cursor_column=cursor_column,
        ast_summary=ast_summary,
        data_flow_context=data_flow_context,
    )
    response = await llm.ainvoke(lc_messages)
    return _chunk_content_to_text(response.content).strip()


async def run_communicator_stream(
    strategist_plan: str,
    history: list[dict],
    *,
    intent: str = "DEBUG",
    documentation_context: list[str] | None = None,
    student_name: str = "",
    hint_level: int = 1,
    cursor_line: int | None = None,
    cursor_column: int | None = None,
    ast_summary: str = "",
    data_flow_context: str = "",
) -> AsyncIterator[str]:
    """Stream de tokens do comunicador (apenas texto, sem ferramentas)."""
    llm = _communicator_llm()
    lc_messages = _communicator_lc_messages(
        strategist_plan,
        history,
        intent=intent,
        documentation_context=documentation_context,
        student_name=student_name,
        hint_level=hint_level,
        cursor_line=cursor_line,
        cursor_column=cursor_column,
        ast_summary=ast_summary,
        data_flow_context=data_flow_context,
    )
    async for chunk in llm.astream(lc_messages):
        text = _chunk_content_to_text(chunk.content)
        if text:
            yield text
