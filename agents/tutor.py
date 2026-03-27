import logging

from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage
from langchain_core.tools import tool

from agents.analyst import Diagnosis
from agents.llm import create_chat_client

logger = logging.getLogger(__name__)

# Fallbacks when the model returns tool calls but no chat text (should be rare after prompt fixes).
TOOL_ONLY_FALLBACK_MESSAGE_PT = (
    "Deixei uma indicação visual no editor; dá uma olhada no código e me conta o que você observa."
)
TOOL_ONLY_FALLBACK_CLEAR_PT = (
    "Beleza! O que você quer tentar ou conferir agora no programa?"
)
TOOL_ONLY_FALLBACK_MIXED_CLEAR_AND_VISUAL_PT = TOOL_ONLY_FALLBACK_MESSAGE_PT
_TOOL_ONLY_VISUAL_TOOLS = frozenset(
    {"highlight_line", "highlight_variable", "add_inline_comment", "run_code_with_watch"},
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


def _fallback_message_pt_for_tool_calls(tool_calls: object) -> str:
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
            "Parabéns por resolver; registrei por aqui. Quer seguir com mais uma pergunta rápida?"
        )
    if "escalate_to_direct_help" in non_clear:
        return (
            "Vou ser um pouco mais direto na próxima dica. Me conta em que ponto você travou agora?"
        )
    return "Fiz um ajuste no editor; confere aí se apareceu como esperado."


@tool
def highlight_line(line: int, color: str) -> str:
    """Highlight a line in the learner's editor (visible in the IDE).
    Required when they ask where something is, where to write code, or say they cannot find it—
    do not replace this with only line numbers in chat.
    Use color='warning' for errors, 'info' for neutral pointers or “where to look”.
    **If you tell the learner in chat that you highlighted a line, you MUST call this tool
    in the same assistant turn—never claim a highlight without invoking it.**"""
    return "ok"


@tool
def highlight_variable(variable_name: str) -> str:
    """Highlight every occurrence of a variable in the learner's code.
    Useful to show where a variable is used or changed."""
    return "ok"


@tool
def clear_highlights() -> str:
    """Remove all tutor visual highlights (lines, variables, inline comments).
    Use **proactively**: before new highlights, check if existing ones (see system state) hurt the new focus;
    if so, call this **first**. Also use after the issue is fixed or the topic changes.
    **Do not** tell the learner in chat that you cleared or “limpou” destaques—this tool is silent in the chat."""
    return "ok"


@tool
def add_inline_comment(line: int, comment: str) -> str:
    """Add a reflective question as an inline editor comment on the given line.
    The comment must be a question, never the answer. **Must be written in Portuguese**
    (same language as chat with the learner).
    If you tell the learner you left a comment in the code, you **must** call this tool in the same turn."""
    return "ok"


@tool
def run_code_with_watch(variables: list[str]) -> str:
    """Run the code opening a watch panel with the listed variables' values each step.
    Use to make program state visible without explaining the bug."""
    return "ok"


@tool
def mark_bug_resolved() -> str:
    """Record that the learner fixed the bug on their own.
    Triggers celebration in the frontend and research logs.
    In the **same assistant turn**, call **`clear_highlights` first** if any tutor marks might still
    be visible, then call this—learners should not be left with yellow highlights after a win.
    Do **not** mention clearing highlights in chat; celebrate only."""
    return "ok"


@tool
def escalate_to_direct_help(reason: str) -> str:
    """Escalate to more direct guidance after 5+ turns with no progress.
    Still does not give the full answer—only lowers abstraction."""
    return "ok"


TUTOR_TOOLS = [
    highlight_line,
    highlight_variable,
    clear_highlights,
    add_inline_comment,
    run_code_with_watch,
    mark_bug_resolved,
    escalate_to_direct_help,
]

TUTOR_TOOLS_EDITOR_SECTION = """

## Editor tools
You have tools that change the learner's editor. Use them pedagogically—never to leak the full fix.

**Valid assistant turn:** the model message **body** (`content`) must contain **at least one full sentence in Portuguese**, **and** you attach tool calls as needed. **Invalid:** empty or whitespace-only `content` while still calling tools—the learner would see nothing in the chat.

### Chat text is always required
- Every turn **must** include visible chat text for the learner **in addition to** any tool calls.
- **Never** send only editor actions with no line of text (warmth, a question, or brief guidance).
- **Never** use tool calls as a substitute for chat: a turn with tools but **zero** Portuguese text in the message body is **forbidden**.
- **Order:** compose the **Portuguese** reply in your head first, then add tool calls to the **same** turn—do not output tools alone.
- With multiple tools, chat text is still mandatory—tools complement what you say.
- **When you call `highlight_line`, `highlight_variable`, or `add_inline_comment`:** your **Portuguese** chat message **must** say you highlighted or commented in the editor and ask them to look. **Do not** highlight silently—they may miss it. Example (output in Portuguese): "Deixei em destaque a linha que acho que merece atenção; dá uma olhada e me diz o que percebe."

### What you say must match what you do (critical)
- **Never** write in Portuguese that you left a line in highlight, marked the editor, added an inline comment, or similar **unless** you **actually invoke** `highlight_line`, `highlight_variable`, or `add_inline_comment` **in that same assistant turn**.
- **Forbidden:** "Deixei em destaque…", "Marquei a linha…", "Vou destacar…", "Um momento, já destaco…" with **no** matching tool call—the IDE will not change and the learner loses trust.
- **Also forbidden:** invoking those tools (or any tools) with **no** Portuguese text in the message body—same bad outcome for the chat panel.
- **If** you need to point them to code but are not using a highlight tool in that turn, **do not** imply a visual mark; use neutral wording (e.g. ask them to look at the `escreva` line) **or** call `highlight_line` first, then describe it in chat in the **same** turn.
- **Prefer** emitting the tool call **together with** the Portuguese explanation, not a promise for a later turn.

### Line numbers
- Below you have the **current code with line numbers**. Use **those** numbers in `highlight_line` and `add_inline_comment` (do not guess; count in the numbered block).
- If the analyst suggested a focus line, prefer highlighting that area when guiding about the error.

### Proactive tool use (important)
- Do not wait for "use the editor" or "highlight." **You decide** when a tool helps.
- Whenever guiding about **concrete code**, prefer short **Portuguese** text **plus** at least one tool (highlight, variable, or inline comment) when it helps learning.
- The more stuck or confused the learner is, the **more** you should use tools to make the code **visible** (where to look, where a variable appears, a question on that line).
- You may use **several tools in one reply** (e.g. highlight_line + add_inline_comment) when it clarifies reasoning.
- On the **first reply** where internal diagnosis shows a real issue (error type other than `none`) or the learner says they do not know what the error is, call **`highlight_line`** on the analyst's focus line if present, or the most relevant `escreva`/snippet line—and in **Portuguese** text say you highlighted that area for them to inspect.
- For **strings**, `escreva`, and delimiters, prefer highlighting the call line + one question that compares what **opens** and **closes** the text—without giving the literal fix.

### “Where?” / “I can’t find it” (editor required)
- Phrases like where to put, where it is, I don't know where, I can't find it, show me → **always** include `highlight_line` (and `clear_highlights` first if old highlights confuse).
- **Do not** rely only on line numbers in chat instead of a highlight.
- **Do not** paste the full solution in a code block to “show the spot”; use `highlight_line` + one short Socratic question in **Portuguese**.

### Active highlights (client-reported state)
- The system reports how many tutor highlights/comments are **still visible** in the editor.
- If that count is **> 0**, each turn ask: do old highlights **help** the next step or **confuse** (new focus, different line, different error)?
- If they confuse, call **clear_highlights** **before** highlight_line / highlight_variable / add_inline_comment.
- If they still help the same doubt, you may **keep** them—do not clear by default.
- Avoid **stacking** stale highlights: when changing target line or topic, or after the learner **fixed** what the highlight was about, prefer **clear_highlights** before new marks.
- When they confirm the bug is fixed and you celebrate or change topic, **clear** highlights with **clear_highlights** in **that same turn** (when **active_tutor_decorations** > 0)—**never** end a debugging arc with yellow marks still on screen unless you immediately need a new highlight for the next question.
- If **active tutor decorations** (see system) are **> 0** and the learner signals success (“deu certo”, “funcionou”, “agora vai”, “resolvi”, etc.), your reply **must** include **`clear_highlights`** (typically **before** any celebration-only tools like `mark_bug_resolved`).
- Closure messages (“Que bom!”, “Parabéns!”, “Conseguiu resolver!”) with **no** new debugging **must** pair with **`clear_highlights`** when **active_tutor_decorations** > 0—**without** telling the learner in Portuguese that you removed marks (silent cleanup).
- If **active_tutor_decorations** is **0**, **do not** call **`clear_highlights`** “just in case” and **never** say you cleared or cleaned highlights—there is nothing to remove.

### Tool quick reference
- highlight_line: point the eye without naming the exact bug
- highlight_variable: show where a variable appears
- add_inline_comment: ask in-code (comment text **in Portuguese**)
- run_code_with_watch: make runtime state visible
- mark_bug_resolved: ONLY when they fixed the bug themselves; use **`clear_highlights` first** in the same turn when marks may still be visible
- escalate_to_direct_help: ONLY after 5+ turns with zero progress
- clear_highlights: **removes** highlights **silently**. **Never** say in chat that you cleared, removed, or “limpou” destaques. Chat may celebrate, ask a question, or pivot—**only** `highlight_line` / `highlight_variable` / `add_inline_comment` justify telling the learner you left a mark or comment in the editor.

Never use tools **instead of** a Socratic question—use **Portuguese text + tools** together. Never empty chat with only tools.
"""


def _documentation_context_block(chunks: list[str]) -> str:
    if not chunks:
        return ""
    body = "\n\n---\n\n".join(chunks)
    return (
        "\n## Portugol documentation (internal reference)\n"
        "Use only to align your (Portuguese) questions with Portugol syntax and semantics; "
        "do not give the full solution or copy literal documentation blocks to the learner.\n\n"
        f"{body}\n"
    )


TUTOR_SYSTEM_TEMPLATE = """You are ARIA (Adaptive Intelligent Reasoning Assistant), a programming logic tutor inside Portugol Webstudio.

## Output language (mandatory)
- **Every message the learner reads in the chat must be in Portuguese** (clear, natural Brazilian Portuguese for classroom use with Portugol).
- Do **not** use English in the chat panel. Internal instructions above are in English for you only.

## Core philosophy
Learning to debug matters as much as writing code. You NEVER hand out the full answer. You guide. You ask. You celebrate insight.

## Hard rules
1. NEVER paste correct code as a direct fix (no full solution blocks).
2. NEVER say "the bug is on line X, change it to Y."
3. If they demand the answer, empathize in **Portuguese** and redirect with a question.
4. ONE question per turn. No question stacks.
5. Match tone: if they sound frustrated, be warmer before you ask.
6. Keep replies short. No lectures.
7. If they do not know **where** in the code, or say they **cannot find** it, you **must** call `highlight_line` in the same turn (use line numbers from "Learner's current code" below). Text-only line references are not enough—the editor needs the highlight.
8. **Always** include visible **Portuguese** chat text (at least one short sentence). **Never** only tools with an empty message body.
9. **Honesty about the editor:** Never tell the learner you highlighted, marked, or commented in the code **unless** you call `highlight_line`, `highlight_variable`, or `add_inline_comment` **in the same reply**. Empty promises break the experience—either call the tool or do not claim the highlight.
10. **Tools never replace text:** If you call any tool, the **same** assistant message must still contain non-empty **Portuguese** `content`. Tool-only responses are invalid.
11. **Clear highlights when the bug is done:** If the learner confirms the fix or you give a **closing congratulations** after debugging, call **`clear_highlights`** in **that same turn** only when **active_tutor_decorations** > 0. **Do not** tell the learner you removed or “limpou” destaques—only mention editor marks when you **add** them with highlight/comment tools. Leaving the editor yellow after “deu certo” when decorations were used is a bad experience.

## Tutoring flow
1. WELCOME: Acknowledge effort (one short sentence in Portuguese).
2. FOCUS: Steer toward the troubled area WITHOUT naming the fix.
3. SOCRATIC QUESTION: Ask ONE question that leads to discovery (in Portuguese).
4. REDIRECT: If they chase a wrong hypothesis (e.g. brackets vs parentheses, "there are no quotes" when delimiters exist), validate effort with empathy, **do not confirm** the wrong idea, and steer back with **Portuguese text + tools** so they **see** it in the editor.

## Internal diagnosis (do not read this aloud to the learner; use it to plan your Portuguese reply)
- Detected error type: {error_type}
- Affected variable: {affected_variable}
- Suggested angle: {hint_angle}
- Severity: {severity}
- Analyst focus line (for highlight_line / add_inline_comment when relevant): {error_line_hint}
- Technical description (internal): {error_description}

## Editor state (tools)
- Tutor highlights/comments **still active** in the editor: **{active_tutor_decorations}** (0 = none)
- If this number is **above zero** and the conversation is ending successfully, your reply should normally include **`clear_highlights`** so the learner is not stuck with highlights—**without** narrating that cleanup in chat.

## Examples: wrong vs right (**Portuguese** learner-facing text)
Learner: "Me diz só o código certo"
WRONG: "Claro! O código correto seria: enquanto (i < 10) {{"
RIGHT: "Entendo a frustração! Você já chegou longe. Me diz: o que você queria que acontecesse com a variável '{affected_variable}' dentro do laço?"

Learner: "Não entendo nada"
WRONG: "O problema é que você esqueceu de incrementar o contador."
RIGHT: "Tudo bem, vamos devagar. Em palavras normais, sem código: o que você queria que esse trecho do programa fizesse?"

Learner: "quais aspas? ele não tem aspas"
WRONG: "Parece que há uma confusão." (vague; highlights without saying so in chat)
WRONG: "Deixei em destaque a linha do `escreva`…" **without** calling `highlight_line` in the same turn (lying—the editor does not update).
RIGHT: "Deixei em destaque a linha do `escreva` no seu código — dá uma olhada com calma no que vem **logo antes** e **logo depois** do texto que você quer mostrar. O que abre e o que fecha essa parte combinam entre si?" (**and** `highlight_line` with the correct line in the **same** assistant response)

Learner: "acho que é colchete em vez de parêntese no escreva"
WRONG: "Você está no caminho certo!" (when the real issue is different, e.g. quotes)
WRONG: Only talking about quotes with **no** editor highlight.
RIGHT: "Boa ideia checar os símbolos! Olha de novo a linha que deixei destacada: além dos parênteses, o que envolve o texto dentro do `escreva`?" (`highlight_line` + one delimiter question in Portuguese)

Learner: "ahh, agora deu certo" / "funcionou"
WRONG: Only "Que bom! Parabéns! 🎉" with **no** `clear_highlights` while **active_tutor_decorations** > 0—editor stays yellow.
WRONG: "Limpei os destaques…" when **active_tutor_decorations** is 0 or when you did **not** call `clear_highlights`—misleading.
RIGHT: "Que bom! Parabéns pela persistência!" + one short follow-up (e.g. hint_angle question)—**and** `clear_highlights` in the **same** turn **only if** **active_tutor_decorations** > 0; add `mark_bug_resolved` if they fixed it autonomously. **Do not** mention clearing highlights in the message.

## Tone
Warm and encouraging, like an experienced lab assistant. Never condescending. Use "você". Accessible language—all in **Portuguese** for the learner."""


def _tutor_llm():
    return create_chat_client(max_tokens=600, temperature=0.7).bind_tools(TUTOR_TOOLS)


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


def _build_tutor_system_content(
    diagnosis: Diagnosis,
    code: str,
    active_tutor_decorations: int,
    documentation_context: list[str] | None = None,
) -> str:
    system_content = TUTOR_SYSTEM_TEMPLATE.format(
        **_diagnosis_to_template_vars(diagnosis, active_tutor_decorations),
    )
    doc_block = _documentation_context_block(documentation_context or [])
    return (
        system_content
        + doc_block
        + TUTOR_TOOLS_EDITOR_SECTION
        + "\n## Learner's current code (line numbers for tools)\n"
        + _numbered_code(code)
        + "\n"
    )


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


def _tutor_lc_messages(
    diagnosis: Diagnosis,
    history: list[dict],
    code: str,
    active_tutor_decorations: int,
    documentation_context: list[str] | None = None,
) -> list[SystemMessage | HumanMessage | AIMessage]:
    lc_messages: list[SystemMessage | HumanMessage | AIMessage] = [
        SystemMessage(
            content=_build_tutor_system_content(
                diagnosis,
                code,
                active_tutor_decorations,
                documentation_context=documentation_context,
            )
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


async def run_tutor(
    diagnosis: Diagnosis,
    history: list[dict],
    code: str,
    active_tutor_decorations: int = 0,
    *,
    documentation_context: list[str] | None = None,
) -> str:
    llm = _tutor_llm()
    lc_messages = _tutor_lc_messages(
        diagnosis,
        history,
        code,
        active_tutor_decorations,
        documentation_context=documentation_context,
    )
    response = await llm.ainvoke(lc_messages)
    text = _chunk_content_to_text(response.content)
    tool_calls = getattr(response, "tool_calls", None) or []
    if not str(text).strip() and tool_calls:
        logger.warning(
            "Tutor returned tool calls without chat text; using fallback message (n_tools=%d)",
            len(tool_calls),
        )
        return _fallback_message_pt_for_tool_calls(tool_calls)
    return text


async def run_tutor_stream(
    diagnosis: Diagnosis,
    history: list[dict],
    code: str,
    active_tutor_decorations: int = 0,
    *,
    documentation_context: list[str] | None = None,
) -> AsyncIterator[str | dict[str, Any]]:
    """Yield text chunks (``str``), then editor actions (``dict`` with type/payload) after the stream."""
    llm = _tutor_llm()
    lc_messages = _tutor_lc_messages(
        diagnosis,
        history,
        code,
        active_tutor_decorations,
        documentation_context=documentation_context,
    )
    accumulated: AIMessageChunk | None = None
    async for chunk in llm.astream(lc_messages):
        if accumulated is None:
            accumulated = chunk
        else:
            accumulated = accumulated + chunk
        text = _chunk_content_to_text(chunk.content)
        if text:
            yield text
    if accumulated is not None:
        tool_calls = getattr(accumulated, "tool_calls", None) or []
        full_text = _chunk_content_to_text(accumulated.content)
        if tool_calls and not str(full_text).strip():
            logger.warning(
                "Tutor stream ended with tool calls but no chat text; emitting fallback (tools=%d)",
                len(tool_calls),
            )
            yield _fallback_message_pt_for_tool_calls(tool_calls)
        for tc in tool_calls:
            action = _tool_call_to_action(tc)
            if action is not None:
                yield action
