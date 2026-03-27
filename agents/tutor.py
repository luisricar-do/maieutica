"""Comunicador ARIA: traduz o plano do estrategista em texto empático (sem ferramentas)."""

import logging
from collections.abc import AsyncIterator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.llm import create_chat_client

logger = logging.getLogger(__name__)

COMMUNICATOR_DEBUG_TEMPLATE = """You are ARIA, a warm and empathetic programming logic tutor for Portugol.
Do not solve the problem for the student.
You will receive a <strategist_plan> from the internal pedagogical engine.
Your ONLY job is to translate that strategy into 1 or 2 warm, encouraging sentences in Brazilian Portuguese.
If the strategy says 'We highlighted lines 3 and 5 to compare quotes', your message MUST smoothly mention that you highlighted the code for them to look at.
Never invent line numbers. Rely entirely on the <strategist_plan>.

<strategist_plan>
{strategist_plan}
</strategist_plan>
"""

COMMUNICATOR_CASUAL_TEMPLATE = """You are ARIA, a warm programming tutor persona for Portugol.
The student is not asking for debugging right now (greeting, thanks, or chat).
Respond briefly in Brazilian Portuguese with warmth and encouragement. Do not analyze code or errors unless they explicitly ask.
Keep it to 1–3 short sentences.

<internal_hint>
{strategist_plan}
</internal_hint>
"""

COMMUNICATOR_THEORY_TEMPLATE = """You are ARIA, a warm Portugol tutor. The student asked a conceptual question.
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
) -> str:
    if intent == "CASUAL":
        return COMMUNICATOR_CASUAL_TEMPLATE.format(strategist_plan=strategist_plan)
    if intent == "THEORY":
        docs_text = "\n\n---\n\n".join(documentation_context) if documentation_context else "(Nenhum trecho recuperado; responda com cuidado e uma pergunta socrática.)"
        return COMMUNICATOR_THEORY_TEMPLATE.format(documentation=docs_text)
    return COMMUNICATOR_DEBUG_TEMPLATE.format(strategist_plan=strategist_plan)


def _communicator_lc_messages(
    strategist_plan: str,
    history: list[dict],
    *,
    intent: str = "DEBUG",
    documentation_context: list[str] | None = None,
) -> list[SystemMessage | HumanMessage | AIMessage]:
    docs = documentation_context if documentation_context is not None else []
    lc_messages: list[SystemMessage | HumanMessage | AIMessage] = [
        SystemMessage(
            content=_build_system_content(strategist_plan, intent, docs),
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
) -> str:
    """Gera a mensagem final da ARIA a partir do plano interno do estrategista."""
    llm = _communicator_llm()
    lc_messages = _communicator_lc_messages(
        strategist_plan,
        history,
        intent=intent,
        documentation_context=documentation_context,
    )
    response = await llm.ainvoke(lc_messages)
    return _chunk_content_to_text(response.content).strip()


async def run_communicator_stream(
    strategist_plan: str,
    history: list[dict],
    *,
    intent: str = "DEBUG",
    documentation_context: list[str] | None = None,
) -> AsyncIterator[str]:
    """Stream de tokens do comunicador (apenas texto, sem ferramentas)."""
    llm = _communicator_llm()
    lc_messages = _communicator_lc_messages(
        strategist_plan,
        history,
        intent=intent,
        documentation_context=documentation_context,
    )
    async for chunk in llm.astream(lc_messages):
        text = _chunk_content_to_text(chunk.content)
        if text:
            yield text
