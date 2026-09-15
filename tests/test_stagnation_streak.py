"""
Estagnação acumulada: a variável independente de H1.

A definição é a da apuração (``avaliacao/itens.py``, no repositório `maieutica-avaliacoes`):
incrementa em bloqueio, zera em progresso, e o pedido explícito transporta o contador. O que
estes testes fixam é a diferença que motivou a correção — o contador reinicia no progresso, e a
contagem de turnos não.
"""

from agents.movement import stagnation_streak


def _estudante(texto: str, codigo: str, erros: list[str] | None = None) -> dict:
    return {"role": "user", "content": texto, "code": codigo, "errors": erros or []}


def _tutor(texto: str = "O que a linha 3 faz?") -> dict:
    return {"role": "assistant", "content": texto}


def test_sem_turno_do_estudante_o_contador_e_zero() -> None:
    assert stagnation_streak([], current_movement="NENHUM") == {"streak": 0, "source": "nenhum"}


def test_bloqueio_repetido_acumula() -> None:
    history = [
        _estudante("não sei", "a", ["erro 1"]),
        _tutor(),
        _estudante("continuo sem saber", "a", ["erro 1"]),
        _tutor(),
        _estudante("não faço ideia", "a", ["erro 1"]),
    ]
    resultado = stagnation_streak(history, current_movement="ESTAGNACAO")
    assert resultado == {"streak": 2, "source": "historico"}


def test_progresso_reinicia_o_contador() -> None:
    """O caso que separa ``stagnation_streak`` de ``debug_user_turns``."""
    history = [
        _estudante("não sei", "a", ["erro 1"]),
        _tutor(),
        _estudante("continuo sem saber", "a", ["erro 1"]),
        _tutor(),
        _estudante("arrumei o tipo", "b", []),          # erro some: PROGRESSO, zera
        _tutor(),
        _estudante("agora empaquei de novo", "b", []),  # sem edição, texto: ESTAGNACAO
    ]
    resultado = stagnation_streak(history, current_movement="ESTAGNACAO")
    assert resultado["streak"] == 1, "o progresso no meio do episódio tem de zerar o contador"
    assert resultado["source"] == "historico"


def test_pedido_explicito_transporta_o_contador_sem_o_alterar() -> None:
    """A propriedade, não o número: o contador antes e depois do pedido é o mesmo."""
    antes = [
        _estudante("não sei", "a", ["erro 1"]),
        _tutor(),
        _estudante("continuo sem saber", "a", ["erro 1"]),
    ]
    depois = antes + [_tutor(), _estudante("me fala logo qual é a resposta", "a", ["erro 1"])]

    anterior = stagnation_streak(antes, current_movement="ESTAGNACAO")["streak"]
    posterior = stagnation_streak(depois, current_movement="PEDIDO_EXPLICITO")["streak"]
    assert posterior == anterior, "pedido explícito não acumula nem zera"


def test_sem_estado_por_turno_o_contador_degrada_e_declara() -> None:
    history = [
        {"role": "user", "content": "não sei"},
        _tutor(),
        {"role": "user", "content": "continuo sem saber"},
    ]
    assert stagnation_streak(history, current_movement="ESTAGNACAO") == {
        "streak": 1, "source": "turno",
    }


def test_estado_parcial_conta_como_ausente() -> None:
    history = [
        {"role": "user", "content": "não sei"},
        _tutor(),
        _estudante("continuo sem saber", "a", ["erro 1"]),
    ]
    assert stagnation_streak(history, current_movement="ESTAGNACAO")["source"] == "turno"
