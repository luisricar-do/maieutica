import logging

from collections.abc import AsyncIterator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.analyst import Diagnosis
from agents.llm import create_chat_client

logger = logging.getLogger(__name__)

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

## Exemplos do que NÃO fazer
Aluno: "Me diz só o código certo"
ERRADO: "Claro! O código correto seria: enquanto (i < 10) {{"
CERTO: "Entendo a frustração! Você já chegou longe. Me diz: o que você queria que acontecesse com a variável '{affected_variable}' dentro do laço?"

Aluno: "Não entendo nada"
ERRADO: "O problema é que você esqueceu de incrementar o contador."
CERTO: "Tudo bem, vamos devagar. Em palavras normais, sem código: o que você queria que esse trecho do programa fizesse?"

## Tom
Caloroso, encorajador, como um monitor de laboratório experiente. Nunca condescendente. Use "você". Linguagem acessível."""


def _diagnosis_to_template_vars(diagnosis: Diagnosis) -> dict[str, str]:
    av = diagnosis.get("affectedVariable")
    return {
        "error_type": str(diagnosis.get("errorType", "none")),
        "affected_variable": av if av is not None else "",
        "hint_angle": str(diagnosis.get("hintAngle", "")),
        "severity": str(diagnosis.get("severity", "low")),
    }


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


def _tutor_lc_messages(diagnosis: Diagnosis, history: list[dict]) -> list[SystemMessage | HumanMessage | AIMessage]:
    system_content = TUTOR_SYSTEM_TEMPLATE.format(**_diagnosis_to_template_vars(diagnosis))
    lc_messages: list[SystemMessage | HumanMessage | AIMessage] = [
        SystemMessage(content=system_content),
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


async def run_tutor(diagnosis: Diagnosis, history: list[dict]) -> str:
    llm = create_chat_client(max_tokens=600, temperature=0.7)
    lc_messages = _tutor_lc_messages(diagnosis, history)
    response = await llm.ainvoke(lc_messages)
    return _chunk_content_to_text(response.content)


async def run_tutor_stream(diagnosis: Diagnosis, history: list[dict]) -> AsyncIterator[str]:
    """Emite trechos de texto conforme o modelo os gera (``llm.astream``)."""
    llm = create_chat_client(max_tokens=600, temperature=0.7)
    lc_messages = _tutor_lc_messages(diagnosis, history)
    async for chunk in llm.astream(lc_messages):
        text = _chunk_content_to_text(chunk.content)
        if text:
            yield text
