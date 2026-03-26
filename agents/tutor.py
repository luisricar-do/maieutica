import logging

from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage
from langchain_core.tools import tool

from agents.analyst import Diagnosis
from agents.llm import create_chat_client

logger = logging.getLogger(__name__)


@tool
def highlight_line(line: int, color: str) -> str:
    """Destaca uma linha específica no editor do aluno para chamar atenção sem revelar o erro.
    Use color='warning' para erros, 'info' para observações neutras."""
    return "ok"


@tool
def highlight_variable(variable_name: str) -> str:
    """Marca todas as ocorrências de uma variável no código do aluno.
    Útil para mostrar onde uma variável é usada ou modificada."""
    return "ok"


@tool
def clear_highlights() -> str:
    """Remove todos os destaques visuais do editor.
    Use quando o aluno resolver o problema ou mudar de contexto."""
    return "ok"


@tool
def add_inline_comment(line: int, comment: str) -> str:
    """Adiciona uma pergunta de reflexão como comentário inline no editor na linha indicada.
    O comentário deve ser uma pergunta, nunca a resposta."""
    return "ok"


@tool
def run_code_with_watch(variables: list[str]) -> str:
    """Executa o código abrindo painel de watch com os valores das variáveis indicadas a cada passo.
    Use para tornar o estado do programa visível sem explicar o erro."""
    return "ok"


@tool
def mark_bug_resolved() -> str:
    """Indica que o aluno encontrou e corrigiu o erro com autonomia.
    Dispara celebração no frontend e registra a resolução nos logs de pesquisa."""
    return "ok"


@tool
def escalate_to_direct_help(reason: str) -> str:
    """Escala para ajuda mais direta após 5+ trocas sem progresso.
    Ainda não entrega a resposta — apenas reduz o nível de abstração da dica."""
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

## Uso de Tools de Editor
Você tem acesso a tools que interagem com o editor do aluno.
Use-as de forma pedagógica — nunca para revelar a resposta.

### Numeração de linhas
- Mais abaixo há o **código atual com números de linha**. Use **esses** números em `highlight_line` e `add_inline_comment` (não invente; conte no bloco numerado).
- Se o analista indicou uma linha de foco, prefira destacar essa região quando for orientar sobre o erro.

### Uso proativo (importante)
- NÃO espere o aluno pedir para "usar o editor" ou "destacar". **Decida você** quando uma tool ajuda.
- Sempre que estiver a orientar sobre **código concreto**, prefira **combinar** texto curto + pelo menos uma tool (destaque, variável ou comentário inline), sempre que fizer sentido pedagógico.
- Quanto mais o aluno estiver preso ou confuso, **mais** deve recorrer a tools para tornar o código **visível** (onde olhar, onde a variável aparece, pergunta no contexto da linha).
- Pode e deve usar **várias tools na mesma resposta** (ex.: highlight_line + add_inline_comment; highlight_variable + run_code_with_watch) quando isso clarificar o raciocínio.
- Se mudar de assunto ou recomeçar o foco, use clear_highlights antes de novos destaques.

### Referência rápida das tools
- highlight_line: direcione o olhar para uma região sem dizer o que está errado
- highlight_variable: mostre onde uma variável aparece no código
- add_inline_comment: faça uma pergunta diretamente no contexto do código
- run_code_with_watch: torne o estado do programa visível para o aluno
- mark_bug_resolved: use APENAS quando o aluno corrigir o erro de forma autônoma
- escalate_to_direct_help: use APENAS após 5+ trocas sem nenhum progresso
- clear_highlights: use ao iniciar novo tópico ou após resolução

NUNCA use tools como substituto para a pergunta socrática — use **texto + tools** juntos.
"""

TUTOR_SYSTEM_TEMPLATE = """Você é ARIA (Assistente de Raciocínio Inteligente e Adaptativo), tutora de lógica de programação integrada ao Portugol Webstudio.

## Sua Filosofia Central
Você acredita que aprender a depurar código é tão importante quanto escrever código. Você NUNCA entrega a resposta pronta. Você guia. Você pergunta. Você celebra descobertas.

## Regras Invioláveis
1. NUNCA escreva código correto como sugestão direta.
2. NUNCA diga "o erro está na linha X, mude para Y".
3. Se o aluno pedir a resposta diretamente, responda com empatia e redirecione com uma pergunta.
4. Faça UMA pergunta por vez. Nunca faça múltiplas perguntas seguidas.
5. Adapte o tom: se o aluno está frustrado, seja mais empático antes de perguntar.
6. Respostas curtas e diretas. Sem textão.

## Seu Fluxo de Tutoria
1. ACOLHIMENTO: Reconheça o esforço (1 frase curta).
2. FOCO: Direcione para a área problemática SEM revelar o erro.
3. PERGUNTA SOCRÁTICA: Faça UMA pergunta que leve à descoberta.

## Diagnóstico Interno (NÃO mencione esses dados explicitamente ao aluno)
- Tipo de erro detectado: {error_type}
- Variável afetada: {affected_variable}
- Ângulo de abordagem sugerido: {hint_angle}
- Severidade: {severity}
- Linha de foco sugerida pelo analista (use em highlight_line / add_inline_comment quando fizer sentido): {error_line_hint}
- Descrição técnica (interno, não leia em voz alta): {error_description}

## Exemplos do que NÃO fazer
Aluno: "Me diz só o código certo"
ERRADO: "Claro! O código correto seria: enquanto (i < 10) {{"
CERTO: "Entendo a frustração! Você já chegou longe. Me diz: o que você queria que acontecesse com a variável '{affected_variable}' dentro do laço?"

Aluno: "Não entendo nada"
ERRADO: "O problema é que você esqueceu de incrementar o contador."
CERTO: "Tudo bem, vamos devagar. Em palavras normais, sem código: o que você queria que esse trecho do programa fizesse?"

## Tom
Caloroso, encorajador, como um monitor de laboratório experiente. Nunca condescendente. Use "você". Linguagem acessível."""


def _tutor_llm():
    return create_chat_client(max_tokens=600, temperature=0.7).bind_tools(TUTOR_TOOLS)


def _diagnosis_to_template_vars(diagnosis: Diagnosis) -> dict[str, str]:
    av = diagnosis.get("affectedVariable")
    el = diagnosis.get("errorLine")
    if isinstance(el, int) and el >= 1:
        error_line_hint = str(el)
    else:
        error_line_hint = "não identificada"
    return {
        "error_type": str(diagnosis.get("errorType", "none")),
        "affected_variable": av if av is not None else "",
        "hint_angle": str(diagnosis.get("hintAngle", "")),
        "severity": str(diagnosis.get("severity", "low")),
        "error_line_hint": error_line_hint,
        "error_description": str(diagnosis.get("errorDescription", "")),
    }


def _numbered_code(code: str) -> str:
    """Código com prefixo de número de linha (1-based), alinhado ao editor do aluno."""
    lines = code.splitlines()
    if not lines and not code.strip():
        return "(código vazio)"
    if not lines:
        return "1 | "
    width = len(str(len(lines)))
    return "\n".join(f"{i + 1:{width}} | {line}" for i, line in enumerate(lines))


def _build_tutor_system_content(diagnosis: Diagnosis, code: str) -> str:
    system_content = TUTOR_SYSTEM_TEMPLATE.format(**_diagnosis_to_template_vars(diagnosis))
    return (
        system_content
        + TUTOR_TOOLS_EDITOR_SECTION
        + "\n## Código atual do aluno (referência para números de linha nas tools)\n"
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
            logger.warning("Papel de histórico desconhecido ignorado: %s", role)
    return messages


def _tutor_lc_messages(diagnosis: Diagnosis, history: list[dict], code: str) -> list[SystemMessage | HumanMessage | AIMessage]:
    lc_messages: list[SystemMessage | HumanMessage | AIMessage] = [
        SystemMessage(content=_build_tutor_system_content(diagnosis, code)),
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


async def run_tutor(diagnosis: Diagnosis, history: list[dict], code: str) -> str:
    llm = _tutor_llm()
    lc_messages = _tutor_lc_messages(diagnosis, history, code)
    response = await llm.ainvoke(lc_messages)
    return _chunk_content_to_text(response.content)


async def run_tutor_stream(diagnosis: Diagnosis, history: list[dict], code: str) -> AsyncIterator[str | dict[str, Any]]:
    """Emite trechos de texto (``str``) e, após o stream, ações de editor (``dict`` com type/payload)."""
    llm = _tutor_llm()
    lc_messages = _tutor_lc_messages(diagnosis, history, code)
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
        for tc in tool_calls:
            action = _tool_call_to_action(tc)
            if action is not None:
                yield action
