"""Agente Pedagogical Strategist: lógica, diagnóstico e chamadas a ferramentas da IDE (sem falar com o aluno)."""

import logging
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool

from agents.analyst import Diagnosis
from agents.problem_context import build_problem_content
from agents.config import evaluation_mode
from agents.llm import create_chat_client

logger = logging.getLogger(__name__)

# Fallbacks quando o modelo devolve tool_calls mas `content` vazio (plano interno ausente).
TOOL_ONLY_FALLBACK_MESSAGE_PT = (
    "Diretriz: guie o aluno a observar o foco marcado no editor e a relacioná-lo com a mensagem "
    "do compilador, sem dar a solução. Use uma pergunta socrática curta e específica ao erro."
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
        "scroll_to",
        "spotlight_block",
        "draw_data_flow",
        "activate_focus_mode",
        "deactivate_focus_mode",
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


def _diagnosis_specific_fallback_plan_pt(diagnosis: Diagnosis) -> str:
    error_type = str(diagnosis.get("errorType", "none"))
    line = diagnosis.get("errorLine")
    line_text = f"linha {line}" if isinstance(line, int) and line >= 1 else "linha indicada"
    variable = str(diagnosis.get("affectedVariable") or "").strip()

    if error_type == "type_mismatch":
        target = f"a variável `{variable}`" if variable else "a variável envolvida"
        return (
            f"Diretriz: foque {line_text} e peça ao aluno para comparar o tipo declarado de {target} "
            "com o tipo do valor atribuído. Não desvie para pistas de sintaxe estrutural."
        )
    if error_type == "undeclared_identifier":
        target = f"`{variable}`" if variable else "o identificador usado"
        return (
            f"Diretriz: foque {line_text} e peça ao aluno para localizar onde {target} foi declarado "
            "antes de ser usado. Não desvie para pistas de sintaxe estrutural."
        )
    if error_type == "syntax":
        return (
            f"Diretriz: foque {line_text} e peça ao aluno para comparar a estrutura/sintaxe daquele "
            "trecho com a mensagem do compilador, sem entregar a correção."
        )
    if error_type == "logic":
        return (
            "Diretriz: peça ao aluno para comparar a intenção do algoritmo com o comportamento observado "
            "no trecho destacado, sem reescrever o código."
        )
    return TOOL_ONLY_FALLBACK_MESSAGE_PT


def _fallback_plan_pt_for_tool_calls(tool_calls: object, diagnosis: Diagnosis | None = None) -> str:
    names = _tool_names_from_calls(tool_calls)
    if not names:
        return (
            _diagnosis_specific_fallback_plan_pt(diagnosis)
            if diagnosis is not None
            else TOOL_ONLY_FALLBACK_MESSAGE_PT
        )

    non_clear = [n for n in names if n != "clear_highlights"]
    if not non_clear:
        return TOOL_ONLY_FALLBACK_CLEAR_PT

    has_visual = bool(_TOOL_ONLY_VISUAL_TOOLS.intersection(non_clear))
    had_clear = any(n == "clear_highlights" for n in names)

    if has_visual and had_clear:
        return (
            _diagnosis_specific_fallback_plan_pt(diagnosis)
            if diagnosis is not None
            else TOOL_ONLY_FALLBACK_MIXED_CLEAR_AND_VISUAL_PT
        )
    if has_visual:
        return (
            _diagnosis_specific_fallback_plan_pt(diagnosis)
            if diagnosis is not None
            else TOOL_ONLY_FALLBACK_MESSAGE_PT
        )

    if set(non_clear) <= {"mark_bug_resolved"}:
        return (
            "Diretriz: celebrar a resolução pelo aluno; uma pergunta curta sobre o próximo passo "
            "(sem mencionar limpeza de destaques)."
        )
    if set(non_clear) <= {"pause_at_iteration"}:
        return (
            "Diretriz: execução pausada para observação; peça ao aluno que descreva o que mudou "
            "nas variáveis indicadas, sem dar a solução."
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
    """Insere no chat uma referência clicável à documentação do tópico e sinaliza ao Comunicador
    para explicar brevemente essa sintaxe (sem resolver o bug). Use quando o aluno não souber a
    sintaxe de algo básico (ex: 'vetores', 'escreva', 'leia'). Tópicos válidos: 'variaveis',
    'tipos', 'escreva', 'leia', 'se_senao', 'enquanto', 'para', 'vetores', 'matrizes'."""
    return "ok"


@tool
def scroll_to(line: int) -> str:
    """Centra o editor na linha 1-based indicada para guiar o olhar do aluno."""
    return "ok"


@tool
def spotlight_block(start_line: int, end_line: int) -> str:
    """Realça um bloco de linhas (holofote) e escurece o restante via modo foco da IDE."""
    return "ok"


@tool
def draw_data_flow(connections: list[dict]) -> str:
    """Desenha “cordas” de fluxo entre linhas. Cada item: from_line, from_var, to_line, to_var,
    status em {'ok','broken'} (1-based). Use para variável lida vs usada, laços, etc."""
    return "ok"


@tool
def activate_focus_mode(line: int = -1) -> str:
    """Ativa modo foco (dimming). Se line >= 1, também pulsa essa linha; use -1 só para escurecer."""
    return "ok"


@tool
def deactivate_focus_mode() -> str:
    """Desliga modo foco e pulso."""
    return "ok"


@tool
def pause_at_iteration(line: int, iteration_limit: int, variables: list[str]) -> str:
    """Pausa a execução para o aluno observar variáveis (playback didático)."""
    return "ok"


@tool
def set_concreteness_level(level: int) -> str:
    """Declara o nível de concretude deste turno (0 open, 1 focused, 2 conceptual). Uma vez por turno."""
    return "ok"


#: Nome da tool de nível: é dado para o grafo, não ação de IDE, e sai da lista antes de chegar à IDE.
CONCRETENESS_TOOL = "set_concreteness_level"

STRATEGIST_TOOLS = [
    set_concreteness_level,
    highlight_line,
    highlight_variable,
    clear_highlights,
    add_inline_comment,
    run_code_with_watch,
    mark_bug_resolved,
    escalate_to_direct_help,
    compare_lines,
    suggest_documentation,
    scroll_to,
    spotlight_block,
    draw_data_flow,
    activate_focus_mode,
    deactivate_focus_mode,
    pause_at_iteration,
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
- In EVERY turn you MUST call `set_concreteness_level` exactly once, with the concreteness level (0, 1 or 2) you chose for this turn by the ladder below. The Communicator receives this number and must speak at exactly that level, so the directive in `content` must be written for that level.
- If `active_tutor_decorations` > 0 and the topic changes or the bug is fixed, call `clear_highlights` before new highlights when stale marks would confuse.
- Prefer `compare_lines` for declaration vs usage; prefer `highlight_line` on the analyst focus line for first error turns.
- ABSOLUTE GUARDRAIL: Never output Portugol source code or full fixes in `content`. Do not paste learner code back as a solution. Use ONLY IDE tools (`scroll_to`, `spotlight_block`, `draw_data_flow`, `activate_focus_mode`, `highlight_line`, etc.) to guide visually.
- When hint_level is 3, you may be more concrete in the internal directive, but still forbid handing the final code patch.
- First debugging turn / auto-trigger must depend on `Error Type`; never use a generic "what is highlighted visually?" opening if a more specific line/concept is available.
- Error-type mapping for the Communicator angle:
  - `syntax`: focus on malformed syntax, missing structure, delimiters, quotes, or parser location. Use opening/closing metaphors only here, and only when the symptom is actually delimiters/quotes/brackets.
  - `type_mismatch`: focus on the assignment line and compare declared type vs assigned value type.
  - `undeclared_identifier`: focus on declaration before use; prefer comparing declaration and usage lines when both are visible.
  - `logic`: focus on the difference between intended behavior and observed state/data flow.
- If `syntax` has a short literal compiler excerpt in Internal Technical Description, carry that excerpt into `content` so the Communicator can quote it once and ask what part of the code it points to.
- Never mention "aberturas", "fechamentos", delimiters, brackets, or parentheses for `type_mismatch` or `undeclared_identifier`.
- If the learner's hypothesis points to the wrong element, the internal directive must acknowledge it as a possible investigation path but immediately redirect to the correct line/element before discussing the wrong element. Do not validate the wrong location as the source of the bug.
- During an unresolved debugging episode, keep the next question about the immediate fixable observation. Reserve "future prevention" or "what did you learn?" for turns after the error is resolved.
- Concreteness ladder of the directive (the Communicator inherits its level from you):
  - level 0 `open`: observation or question that points at no region and names no error.
  - level 1 `focused`: directs attention to the line, variable or construct of the defect, without saying what is wrong.
  - level 2 `conceptual`: names the nature of the error or the concept involved, without the concrete correction.
  - level 3 `revealing`: the concrete correction, in code or as an unambiguous edit instruction. FORBIDDEN in every turn. A question whose only possible answer is the correction ("isn't `i` missing an increment?") is level 3 too.
- CONTINGENCY RULE (this is the intervention policy; it outranks stylistic preference). Compare with the level of YOUR previous turn (`previous_concreteness_level` in <editor_state>; when it is `unknown`, infer it from the tutor's last message in the history):
  - `PROGRESSO`: keep or lower the level. Never escalate after the learner moves forward.
  - `ESTAGNACAO` or `REGRESSAO` with `stagnation_streak` <= 3: sustain the level and change the angle (another observation, another comparison). Do not escalate yet.
  - `ESTAGNACAO` or `REGRESSAO` with `stagnation_streak` >= 4: escalate exactly one step over your previous turn, never two.
  - The escalation trigger is `stagnation_streak`, NEVER `debug_user_turns`. The streak counts blocked turns since the last progress and resets to 0 the moment the learner progresses: after a progress the ladder starts over from the level you are at, however long the session has run. A long session in which the learner keeps moving forward is not a reason to escalate.
  - `PEDIDO_EXPLICITO`: whatever the turn number, go at most to level 2 (name the concept or the nature of the error) and ask what the learner will change. Never the correction, in code or in prose; do not treat insistence as a reason to reveal.
  - `NENHUM` (opening turn): start at level 0 or 1, as the `Error Type` allows.
- Escalation pace by `hint_level` (modulates the ladder above, never the level-3 ban):
  - hint_level 1 (`Mínimo`): stay at level 0-1 while `stagnation_streak` <= 3. Do not name the key concept early; under persistent blockage, introduce it when the streak reaches 4-5.
  - hint_level 2: normal pace, introducing the concept after repeated confusion.
  - hint_level 3: you may reach level 2 earlier, but still never the final code patch.

<diagnosis_context>
- Error Type: {error_type}
- Affected Variable: {affected_variable}
- Internal Technical Description: {error_description}
- Suggested Pedagogical Angle: {hint_angle}
- Severity: {severity}
- Analyst focus line (for highlights when relevant): {error_line_hint}
- Data flow note from analyst (optional): {data_flow_hint}
</diagnosis_context>

<editor_state>
- Active Tutor Highlights in IDE: {active_tutor_decorations}
- Hint level from UI (1=subtle questions … 3=more concrete guidance): {hint_level}
- Learner debugging turns in current session: {debug_user_turns}
- Blocked learner turns accumulated since the last progress: {stagnation_streak}
- Learner movement in the previous turn (PROGRESSO | ESTAGNACAO | REGRESSAO | PEDIDO_EXPLICITO | NENHUM): {student_movement}
- previous_concreteness_level (the LEVEL you chose in your previous turn, or `unknown`): {previous_concreteness_level}
- Cursor (1-based, if provided): line {cursor_line} column {cursor_column}
- AST/editor summary (optional): {ast_summary}
- Data flow context from IDE (optional, e.g. drawn links): {data_flow_context}
</editor_state>

<learner_code>
{numbered_code}
</learner_code>
"""


def active_strategist_tools() -> list:
    """Ferramentas do estrategista; sem ``suggest_documentation`` em ``EVALUATION_MODE``."""
    if evaluation_mode():
        return [t for t in STRATEGIST_TOOLS if t is not suggest_documentation]
    return list(STRATEGIST_TOOLS)


def _strategist_llm():
    return create_chat_client(max_tokens=400, temperature=0.3).bind_tools(
        active_strategist_tools()
    )


def _diagnosis_to_template_vars(diagnosis: Diagnosis, active_tutor_decorations: int) -> dict[str, str]:
    av = diagnosis.get("affectedVariable")
    el = diagnosis.get("errorLine")
    if isinstance(el, int) and el >= 1:
        error_line_hint = str(el)
    else:
        error_line_hint = "not identified"
    ad = max(0, active_tutor_decorations)
    dfh = str(diagnosis.get("dataFlowHint", "") or "")
    return {
        "error_type": str(diagnosis.get("errorType", "none")),
        "affected_variable": av if av is not None else "",
        "hint_angle": str(diagnosis.get("hintAngle", "")),
        "severity": str(diagnosis.get("severity", "low")),
        "error_line_hint": error_line_hint,
        "error_description": str(diagnosis.get("errorDescription", "")),
        "active_tutor_decorations": str(ad),
        "data_flow_hint": dfh.strip() if dfh.strip() else "(none)",
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


def _count_user_turns(history: list[dict]) -> int:
    return sum(1 for item in history if item.get("role") == "user")


#: Teto do nível que sai do estrategista: o nível 3 (``revealing``) é proibido em qualquer turno.
MAX_CONCRETENESS_LEVEL = 2

_LEVEL_LINE = re.compile(
    r"^\s*\**\s*LEVEL\s*[:=]\s*(\d)\b\**"
    r"(?:[ \t]*[(`]*(?:open|focused|conceptual|revealing)[)`]*)?[ \t.:;—–-]*\n?",
    re.IGNORECASE,
)


def split_concreteness_level(plan_text: str) -> tuple[int | None, str]:
    """Separa a linha ``LEVEL: n`` do plano: devolve ``(nível, diretriz sem a linha)``.

    O nível tem de chegar ao comunicador como número, e não diluído na prosa da diretriz: dito
    só em palavras, o comunicador o reescrevia como mais uma pergunta aberta e a escada nunca
    subia na fala, por mais que subisse no plano. Sem a linha, ``None`` e o plano intacto.
    Acima do teto, o nível é rebaixado ao teto: a proibição do nível 3 não depende do modelo.
    """
    match = _LEVEL_LINE.match(plan_text or "")
    if match is None:
        return None, plan_text
    level = min(int(match.group(1)), MAX_CONCRETENESS_LEVEL)
    return level, plan_text[match.end():].strip()


def pop_declared_level(actions: list[dict[str, Any]]) -> tuple[int | None, list[dict[str, Any]]]:
    """Tira das ações a chamada de ``set_concreteness_level``: devolve ``(nível declarado, ações de IDE)``.

    O nível declarado numa tool é um argumento tipado, coisa que o modelo cumpre; a linha
    ``LEVEL: n`` no texto do plano o ``gpt-4o-mini`` omitiu em 155 de 160 turnos (bancada,
    18/10/2026). Sem a chamada, ou com argumento que não seja inteiro de 0 a 3, ``None``.
    """
    level: int | None = None
    ide_actions: list[dict[str, Any]] = []
    for action in actions:
        if action.get("type") != CONCRETENESS_TOOL:
            ide_actions.append(action)
            continue
        raw = (action.get("payload") or {}).get("level")
        if isinstance(raw, str) and raw.strip().isdigit():
            raw = int(raw.strip())
        if isinstance(raw, int) and not isinstance(raw, bool) and 0 <= raw <= 3 and level is None:
            level = min(raw, MAX_CONCRETENESS_LEVEL)
    return level, ide_actions


_BLOCKED_MOVEMENTS = frozenset({"ESTAGNACAO", "REGRESSAO"})


def contingent_level(
    declared: int | None,
    previous: int | None,
    *,
    student_movement: str,
    stagnation_streak: int,
    hint_level: int = 1,
) -> int:
    """Aplica a regra de contingência ao nível declarado pelo estrategista e devolve o nível do turno.

    A regra está no prompt do estrategista, mas executada pelo LLM ela é tendência, não garantia
    (Seção 5.7 da dissertação). Aqui ela vira código, e o modelo só decide onde a regra o deixa:

    - bloqueio (``ESTAGNACAO``/``REGRESSAO``) com acumulado >= 4: um degrau acima do anterior;
    - bloqueio com acumulado <= 3: mantém o anterior (no nível de dica >= 2, pode subir um degrau);
    - ``PROGRESSO``: mantém ou baixa, nunca sobe;
    - ``PEDIDO_EXPLICITO`` e abertura: o declarado, dentro do teto.

    Sem nível anterior (primeiro turno, ou cliente que não devolve ``concretenessLevel``), vale o
    declarado; sem ele também, 2 sob bloqueio persistente e 1 no resto. O teto é sempre 2, e no
    nível de dica 1 o conceito (nível 2) espera o acumulado chegar a 4.
    """
    movement = (student_movement or "").strip().upper()
    blocked = movement in _BLOCKED_MOVEMENTS
    streak = max(0, int(stagnation_streak or 0))
    if declared is not None:
        declared = max(0, min(MAX_CONCRETENESS_LEVEL, declared))

    if previous is None:
        level = declared if declared is not None else (2 if blocked and streak >= 4 else 1)
        if movement == "NENHUM":
            level = min(level, 1)
    elif blocked and streak >= 4:
        level = previous + 1
    elif blocked:
        wanted = declared if declared is not None else previous
        level = previous if hint_level <= 1 else max(previous, min(wanted, previous + 1))
    elif movement == "PROGRESSO":
        level = previous if declared is None else min(declared, previous)
    else:
        level = declared if declared is not None else previous

    if hint_level <= 1 and not (blocked and streak >= 4) and movement != "PEDIDO_EXPLICITO":
        # Ritmo do nível de dica 1: o conceito só entra sob bloqueio persistente. Depois de um
        # progresso o nível já alcançado não é forçado para baixo (o PROGRESSO só o mantém ou baixa).
        if previous is None or level > previous:
            level = min(level, 1)
    return max(0, min(MAX_CONCRETENESS_LEVEL, level))


def previous_concreteness_level(history: list[dict]) -> int | None:
    """Nível do turno anterior do tutor, se a IDE o devolveu no histórico (``concretenessLevel``).

    A regra de contingência compara com o nível do turno anterior do estrategista, mas o histórico
    só traz a fala do comunicador. Inferir o nível dessa fala fecha o ciclo sobre o próprio erro:
    se a fala ficou aquém do plano, o estrategista lê o nível da fala e não o que decidiu.
    """
    for item in reversed(history):
        if not isinstance(item, dict) or item.get("role") != "assistant":
            continue
        raw = item.get("concretenessLevel")
        if isinstance(raw, bool) or not isinstance(raw, int):
            return None
        return max(0, min(MAX_CONCRETENESS_LEVEL, raw))
    return None


def _build_strategist_system_content(
    diagnosis: Diagnosis,
    code: str,
    active_tutor_decorations: int,
    documentation_context: list[str] | None = None,
    *,
    hint_level: int = 1,
    cursor_line: int | None = None,
    cursor_column: int | None = None,
    ast_summary: str = "",
    data_flow_context: str = "",
    debug_user_turns: int = 0,
    student_movement: str = "NENHUM",
    stagnation_streak: int = 0,
    previous_level: int | None = None,
) -> str:
    vars_map = _diagnosis_to_template_vars(diagnosis, active_tutor_decorations)
    vars_map["numbered_code"] = _numbered_code(code)
    vars_map["hint_level"] = str(max(1, min(3, hint_level)))
    vars_map["debug_user_turns"] = str(max(0, debug_user_turns))
    vars_map["stagnation_streak"] = str(max(0, stagnation_streak))
    vars_map["student_movement"] = student_movement.strip().upper() or "NENHUM"
    vars_map["previous_concreteness_level"] = (
        str(previous_level) if previous_level is not None else "unknown"
    )
    vars_map["cursor_line"] = str(cursor_line) if isinstance(cursor_line, int) and cursor_line >= 1 else "n/a"
    vars_map["cursor_column"] = (
        str(cursor_column) if isinstance(cursor_column, int) and cursor_column >= 1 else "n/a"
    )
    vars_map["ast_summary"] = ast_summary.strip() if ast_summary.strip() else "(none)"
    dfc = data_flow_context.strip() if data_flow_context.strip() else "(none)"
    vars_map["data_flow_context"] = dfc
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
    *,
    hint_level: int = 1,
    cursor_line: int | None = None,
    cursor_column: int | None = None,
    ast_summary: str = "",
    data_flow_context: str = "",
    student_movement: str = "NENHUM",
    stagnation_streak: int = 0,
    problem_statement: str = "",
) -> list[SystemMessage | HumanMessage | AIMessage]:
    lc_messages: list[SystemMessage | HumanMessage | AIMessage] = [
        SystemMessage(
            content=_build_strategist_system_content(
                diagnosis,
                code,
                active_tutor_decorations,
                documentation_context=documentation_context,
                hint_level=hint_level,
                cursor_line=cursor_line,
                cursor_column=cursor_column,
                ast_summary=ast_summary,
                data_flow_context=data_flow_context,
                debug_user_turns=_count_user_turns(history),
                stagnation_streak=stagnation_streak,
                student_movement=student_movement,
                previous_level=previous_concreteness_level(history),
            )
        ),
    ]
    if problem_statement:
        lc_messages.append(HumanMessage(content=build_problem_content(problem_statement)))
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


def suggested_doc_topics(actions: list[dict[str, Any]]) -> list[str]:
    """Tópicos das ações ``suggest_documentation`` (para o Comunicador explicar brevemente)."""
    topics: list[str] = []
    for action in actions:
        if isinstance(action, dict) and action.get("type") == "suggest_documentation":
            topic = (action.get("payload") or {}).get("topic")
            if isinstance(topic, str) and topic.strip():
                topics.append(topic.strip())
    return topics


async def run_strategist(
    diagnosis: Diagnosis,
    history: list[dict],
    code: str,
    active_tutor_decorations: int = 0,
    *,
    documentation_context: list[str] | None = None,
    hint_level: int = 1,
    cursor_line: int | None = None,
    cursor_column: int | None = None,
    ast_summary: str = "",
    data_flow_context: str = "",
    student_movement: str = "NENHUM",
    stagnation_streak: int = 0,
    problem_statement: str = "",
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
        hint_level=hint_level,
        cursor_line=cursor_line,
        cursor_column=cursor_column,
        ast_summary=ast_summary,
        data_flow_context=data_flow_context,
        student_movement=student_movement,
        stagnation_streak=stagnation_streak,
        problem_statement=problem_statement,
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
        plan_text = _fallback_plan_pt_for_tool_calls(tool_calls, diagnosis)
    return actions, plan_text
