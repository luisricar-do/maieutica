"""Escada de concretude decidida em código (política de escalada ``programatica``).

Na versão avaliada em bancada (``1e7e5cd``) a regra de contingência estava só no prompt do
estrategista, e o modelo seguia-a como tendência: começava no nível conceitual antes do quarto
turno bloqueado e não subia depois dele. Aqui o nível-alvo de cada turno de depuração é calculado
a partir do estado que o serviço já mede — movimento, acumulado de bloqueio e nível de dica — e
chega ao estrategista e ao comunicador como um valor único, em vez de uma regra a aplicar sobre o
histórico. O nível 3 (revelação) continua proibido em qualquer estado.
"""

from __future__ import annotations

from agents.config import politica_de_escalada

NIVEL_FOCADO = 1
NIVEL_CONCEITUAL = 2

#: Acumulado de bloqueio a partir do qual o turno sobe ao nível conceitual, por nível de dica.
#: Nível de dica 1 é o da regra de ritmo da dissertação: focado até o terceiro turno bloqueado,
#: conceitual a partir do quarto.
LIMIAR_CONCEITUAL = {1: 4, 2: 2, 3: 0}

NOMES = {NIVEL_FOCADO: "focused", NIVEL_CONCEITUAL: "conceptual"}

DESCRICOES = {
    NIVEL_FOCADO: (
        "Direct the learner's attention to the specific line, variable or construct involved, "
        "and ask what they observe there. Do NOT say what is wrong, do NOT name the error type "
        "or the concept behind it, and do NOT hint at the fix."
    ),
    NIVEL_CONCEITUAL: (
        "Name the nature of the error or the programming concept involved (for example the "
        "stopping condition of a loop, the type of a variable, the order of the operations), "
        "and ask how it applies to the learner's code. Do NOT give the concrete correction: no "
        "code, no exact edit, no value to change, and no question whose only answer is the "
        "correction."
    ),
}


def nivel_alvo(stagnation_streak: int, hint_level: int = 1) -> int:
    """Nível de concretude do turno: focado abaixo do limiar de bloqueio, conceitual a partir dele.

    O progresso zera o acumulado e, com ele, devolve o turno ao nível focado; o pedido explícito
    transporta o acumulado sem o alterar, e por isso não sobe o nível sozinho.
    """
    limiar = LIMIAR_CONCEITUAL[max(1, min(3, int(hint_level)))]
    return NIVEL_CONCEITUAL if max(0, int(stagnation_streak)) >= limiar else NIVEL_FOCADO


def nivel_do_turno(intent: str, stagnation_streak: int, hint_level: int = 1) -> int | None:
    """Nível-alvo do turno, ou ``None`` fora de depuração ou com a política ``prompt``."""
    if (intent or "DEBUG") != "DEBUG" or politica_de_escalada() != "programatica":
        return None
    return nivel_alvo(stagnation_streak, hint_level)


def bloco_estrategista(nivel: int) -> str:
    return (
        "\n<directive_level>\n"
        f"SYSTEM-COMPUTED DIRECTIVE LEVEL FOR THIS TURN: {nivel} ({NOMES[nivel]}). The system computed "
        "it from student_movement, stagnation_streak and hint_level; it replaces the CONTINGENCY RULE "
        "and the escalation pace above. Write the directive for the Communicator at exactly this level: "
        f"{DESCRICOES[nivel]} Level 3 remains forbidden.\n"
        "</directive_level>\n"
    )


#: Forma da mensagem por nível. No conceitual, a pergunta sozinha puxa o turno de volta ao focado
#: (``v12dev``: o comunicador reescrevia o conceito do plano como pergunta de passo pequeno); a
#: frase afirmativa que nomeia o conceito vem antes da pergunta.
FORMA = {
    NIVEL_FOCADO: "Write only a question.",
    NIVEL_CONCEITUAL: (
        "Write exactly two sentences: first ONE short declarative sentence (not a question) that "
        "names the concept or the nature of the error taken from the plan, e.g. 'Aqui o ponto é o "
        "resto da divisão por 2.'; then ONE question about how it applies to the learner's code. "
        "This overrides 'ask questions only' for this message."
    ),
}


def bloco_comunicador(nivel: int) -> str:
    return (
        "\n<directive_level>\n"
        f"Concreteness level of this message: {nivel} ({NOMES[nivel]}). {DESCRICOES[nivel]} "
        f"{FORMA[nivel]} If the plan is more concrete than this level, stay at this level.\n"
        "</directive_level>\n"
    )
