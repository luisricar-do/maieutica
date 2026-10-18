"""Comunicador ADA: traduz o plano do estrategista em texto empático (sem ferramentas)."""

import logging
from collections.abc import AsyncIterator

from agents.problem_context import build_problem_content
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.llm import create_chat_client

logger = logging.getLogger(__name__)

COMMUNICATOR_DEBUG_TEMPLATE = """You are ADA, a Socratic programming logic tutor for Portugol.
Do not solve the problem for the student.
You receive a <strategist_plan> from the internal pedagogical engine.
Your ONLY job is to translate that strategy into 1 to 3 concise sentences in Brazilian Portuguese, at the concreteness level given at the end of these instructions.

Debugging / error context — tone rules:
- Be direct and logical; avoid generic social greetings ("Oi", "Olá", "Tudo bem", small talk, or openings whose only purpose is politeness).
- Do not start with chit-chat; begin from the observation or question implied by the plan.
- If {student_name} is non-empty, you may use the first name once only when it fits naturally in a pedagogical sentence; never force a greeting.
- If the latest student message shows frustration or impatience (e.g. "chega", "cansado", "não entendo", "me diz logo", "desisto"), first acknowledge it with one short empathetic sentence, then ask for one very small next observation. Do not moralize about learning, effort, reflection, or future prevention.
- During unresolved debugging, never ask what the student can do "no futuro" or "para não acontecer novamente"; keep the question on the immediate problem.
- If the student suggested the wrong location/cause and the plan redirects them, acknowledge the attempt briefly but do not reinforce the wrong location as the source of the error.

If the strategy mentions highlighted lines, your message MUST reflect that smoothly (without inventing line numbers).
Never invent line numbers. Take lines, highlights and the angle from the <strategist_plan>.
Never output Portugol code blocks or complete fixes. End with a question.
Never suggest the edit itself, not even as a question: no "e se você mover X para depois do laço?", no "que tal usar o operador `e`?", no "você pode adicionar um `escreva`...", no question whose only answer is the correction. The learner must decide the edit.
Avoid generic visual templates like "Quais partes do seu código estão destacadas visualmente...". Prefer the concrete concept from the strategy (type comparison, declaration before use, syntax structure, or data flow).
Never mention "aberturas", "fechamentos", delimiters, brackets, or parentheses unless the strategy is explicitly about syntax/delimiters/quotes.
If the strategy includes a short literal compiler excerpt, quote that excerpt once in Portuguese and ask the learner to connect it to the highlighted syntax location. Do not quote long blocks.
{documentation_hint}
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
{concreteness_block}"""

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

Example policy:
- If the student asks for an "example", give only generic documentation-style fragments or syntax sketches.
- Never provide a complete functional program, full exercise solution, or copy-paste-ready code block, even if the student calls it "just an example".
- Prefer plain-language structure (e.g. "um laço tem inicialização, condição e atualização") and at most a tiny non-complete fragment when needed.
- Do not use fenced code blocks for examples.

<documentation>
{documentation}
</documentation>
"""

OUT_OF_SCOPE_RESPONSE = (
    "Posso te ajudar com Portugol, lógica de programação e com o código que está aberto. "
    "Que dúvida do seu programa você quer investigar agora?"
)

# Nomes legíveis dos slugs de documentação (alinhados à tool `suggest_documentation`).
_DOC_TOPIC_LABELS = {
    "variaveis": "variáveis",
    "tipos": "tipos de dados",
    "escreva": "comando escreva (saída)",
    "leia": "comando leia (entrada)",
    "se_senao": "condicional se/senão",
    "enquanto": "laço enquanto",
    "para": "laço para",
    "vetores": "vetores",
    "matrizes": "matrizes",
}


def _documentation_hint(topics: list[str] | None) -> str:
    """Instrução adicional (só quando há tópico sugerido): a ADA explica brevemente a sintaxe e
    aponta para a referência clicável, sem entregar a solução do bug. Vazio caso contrário."""
    if not topics:
        return ""
    labels = [_DOC_TOPIC_LABELS.get(t, t.replace("_", " ")) for t in topics]
    topics_text = ", ".join(dict.fromkeys(labels))
    return (
        "\nDOCUMENTATION AID (this turn only): the strategist detected the student likely does not "
        f"know the basic syntax of: {topics_text}. In addition to your guiding question, you MAY add "
        "ONE short factual sentence, in plain Brazilian Portuguese, describing what that syntax is or "
        "does in Portugol. Never write the solution to their specific bug and never output a complete "
        "code block. Mention naturally that you left a reference in the chat (a documentação) they can "
        "open to see the details. Keep the whole message to at most 2-3 short sentences.\n"
    )


_CONCRETENESS_LADDER = """Concreteness ladder:
  - level 0 `open`: an observation or question that points at no region and names no error.
  - level 1 `focused`: directs attention to the line, variable or construct of the defect, without saying what is wrong.
  - level 2 `conceptual`: names the nature of the error or the concept involved (e.g. "o tipo declarado não aceita texto", "a variável é usada antes de ser declarada"), without the concrete correction.
  - level 3 `revealing`: the concrete correction, in code or as an unambiguous edit instruction. FORBIDDEN."""


_LEVEL_SHAPES = {
    0: (
        "Shape for level 0: one open question about what the program should do versus what it "
        "does. Point at no line, variable or construct, and name no error."
    ),
    1: (
        "Shape for level 1: point at the line, variable or construct from the plan and ask about "
        "it. Do not say what is wrong with it."
    ),
    2: (
        "Shape for level 2, in this order: (a) one AFFIRMATIVE sentence that states what is wrong, "
        "naming the nature of the error or the concept involved in the learner's own construct "
        "(e.g. \"A variável que acumula o total volta a zero a cada repetição do laço.\", "
        "\"A leitura acontece uma vez só, antes do laço, e o laço repete sempre o mesmo valor.\"); "
        "then (b) one question "
        "asking what the learner will change. Sentence (a) is a statement, never a question, and it "
        "says WHAT is wrong, never HOW to fix it: no operator, value, statement, or code to write, "
        "and no place to move code to. A message whose only content is a question about where to "
        "look is level 1, not level 2: it does not meet the target."
    ),
}


def error_nature_text(diagnosis: dict | None) -> str:
    """A natureza do erro, do diagnóstico do analista, para o comunicador nomear no nível 2.

    Sem ela o comunicador só tinha o plano, e o plano muitas vezes é o de reserva, genérico
    («guie o aluno a observar o foco marcado»): pedido o nível 2, não havia conceito a nomear e a
    fala saía como mais uma pergunta de foco. Vazio quando não há diagnóstico de erro.
    """
    if not isinstance(diagnosis, dict):
        return ""
    error_type = str(diagnosis.get("errorType") or "none")
    if error_type == "none":
        return ""
    parts = [f"Error type: {error_type}."]
    for key, label in (("errorDescription", "Analyst description"), ("hintAngle", "Concept angle")):
        value = str(diagnosis.get(key) or "").strip()
        if value:
            parts.append(f"{label}: {value}")
    return " ".join(parts)


def _concreteness_block(level: int | None, error_nature: str = "") -> str:
    """Nível de concretude que o estrategista escolheu, dito ao comunicador como número e forma.

    Sem isto o comunicador só conhecia o ``hint_level`` da UI, fixo na sessão, e lia as próprias
    falas anteriores no histórico: reproduzia o nível delas e a escada não subia na fala, por
    mais que subisse no plano. Vai no fim do prompt, depois do plano, e traz a forma da fala em
    cada nível: só o número não bastava, porque o modelo o lia e voltava à pergunta de foco.
    Sem nível (plano de reserva, ou modelo que omitiu a linha), vale o que o plano disser.
    """
    if level is None:
        return ""
    nature = ""
    if level >= 2 and error_nature:
        nature = (
            "\n<error_nature>\n"
            f"{error_nature}\n"
            "</error_nature>\n"
            "Use <error_nature> to know which concept to name in sentence (a). It is internal: "
            "say the nature of the error in plain words about the learner's code, and never turn it "
            "into the corrected code or an edit instruction.\n"
        )
    return (
        f"\nTARGET CONCRETENESS LEVEL FOR THIS TURN: {level} (decided by the strategist; it "
        "outranks the Socratic style above).\n"
        f"{_CONCRETENESS_LADDER}\n"
        f"{_LEVEL_SHAPES[level]}\n"
        "Your message MUST sit exactly at the target level: not below it, not above it. "
        "Your earlier messages in the conversation may sit at a lower level; do not copy their "
        "concreteness or their wording. Never reach level 3.\n"
        f"{nature}"
    )


def _communicator_llm():
    # 800 e um teto que nao morde nenhuma das tres condicoes: A observou no maximo 271 (quem
    # a mantem curta e o prompt, nao o teto) e B mediana 34. Em 300, metade dos turnos da
    # condicao C saia cortada a meio da frase, e a diretividade media sobre texto mutilado
    # enviesava a comparacao toda de um lado. O parametro continua identico nas tres.
    return create_chat_client(max_tokens=800, temperature=0.7)


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
    concreteness_level: int | None = None,
    error_nature: str = "",
    cursor_line: int | None = None,
    cursor_column: int | None = None,
    ast_summary: str = "",
    data_flow_context: str = "",
    suggested_doc_topics: list[str] | None = None,
) -> str:
    if intent == "CASUAL":
        return COMMUNICATOR_CASUAL_TEMPLATE.format(strategist_plan=strategist_plan)
    if intent == "OUT_OF_SCOPE":
        return (
            "You are ADA, a Portugol programming tutor. The latest request is outside your scope. "
            "Do not answer it. Redirect briefly in Brazilian Portuguese to Portugol, programming logic, "
            "or the open code."
        )
    if intent == "THEORY":
        docs_text = (
            "\n\n---\n\n".join(documentation_context)
            if documentation_context
            else "(Nenhum trecho recuperado; responda com cuidado e uma pergunta socrática.)"
        )
        return COMMUNICATOR_THEORY_TEMPLATE.format(documentation=docs_text)
    name = student_name.strip()
    hl = max(1, min(3, int(hint_level)))
    cl = (
        str(cursor_line) if isinstance(cursor_line, int) and cursor_line >= 1 else "n/a"
    )
    cc = (
        str(cursor_column)
        if isinstance(cursor_column, int) and cursor_column >= 1
        else "n/a"
    )
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
        documentation_hint=_documentation_hint(suggested_doc_topics),
        concreteness_block=_concreteness_block(concreteness_level, error_nature),
    )


def _communicator_lc_messages(
    strategist_plan: str,
    history: list[dict],
    *,
    intent: str = "DEBUG",
    documentation_context: list[str] | None = None,
    student_name: str = "",
    hint_level: int = 1,
    concreteness_level: int | None = None,
    error_nature: str = "",
    cursor_line: int | None = None,
    cursor_column: int | None = None,
    ast_summary: str = "",
    data_flow_context: str = "",
    suggested_doc_topics: list[str] | None = None,
    problem_statement: str = "",
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
                concreteness_level=concreteness_level,
                error_nature=error_nature,
                cursor_line=cursor_line,
                cursor_column=cursor_column,
                ast_summary=ast_summary,
                data_flow_context=data_flow_context,
                suggested_doc_topics=suggested_doc_topics,
            ),
        ),
    ]
    if problem_statement:
        lc_messages.append(HumanMessage(content=build_problem_content(problem_statement)))
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
    concreteness_level: int | None = None,
    error_nature: str = "",
    cursor_line: int | None = None,
    cursor_column: int | None = None,
    ast_summary: str = "",
    data_flow_context: str = "",
    suggested_doc_topics: list[str] | None = None,
    problem_statement: str = "",
) -> str:
    """Gera a mensagem final da ADA a partir do plano interno do estrategista."""
    if intent == "OUT_OF_SCOPE":
        return OUT_OF_SCOPE_RESPONSE

    llm = _communicator_llm()
    lc_messages = _communicator_lc_messages(
        strategist_plan,
        history,
        intent=intent,
        documentation_context=documentation_context,
        student_name=student_name,
        hint_level=hint_level,
        concreteness_level=concreteness_level,
        error_nature=error_nature,
        cursor_line=cursor_line,
        cursor_column=cursor_column,
        ast_summary=ast_summary,
        data_flow_context=data_flow_context,
        suggested_doc_topics=suggested_doc_topics,
        problem_statement=problem_statement,
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
    concreteness_level: int | None = None,
    error_nature: str = "",
    cursor_line: int | None = None,
    cursor_column: int | None = None,
    ast_summary: str = "",
    data_flow_context: str = "",
    suggested_doc_topics: list[str] | None = None,
    problem_statement: str = "",
) -> AsyncIterator[str]:
    """Stream de tokens do comunicador (apenas texto, sem ferramentas)."""
    if intent == "OUT_OF_SCOPE":
        yield OUT_OF_SCOPE_RESPONSE
        return

    llm = _communicator_llm()
    lc_messages = _communicator_lc_messages(
        strategist_plan,
        history,
        intent=intent,
        documentation_context=documentation_context,
        student_name=student_name,
        hint_level=hint_level,
        concreteness_level=concreteness_level,
        error_nature=error_nature,
        cursor_line=cursor_line,
        cursor_column=cursor_column,
        ast_summary=ast_summary,
        data_flow_context=data_flow_context,
        suggested_doc_topics=suggested_doc_topics,
        problem_statement=problem_statement,
    )
    async for chunk in llm.astream(lc_messages):
        text = _chunk_content_to_text(chunk.content)
        if text:
            yield text
