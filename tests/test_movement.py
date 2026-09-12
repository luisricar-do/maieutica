"""Movimento do estudante: precedência do pedido explícito, regra do código, sinal do texto."""

from agents.movement import classify_movement, is_explicit_request


def _history(*turns: tuple[str, str]) -> list[dict]:
    return [{"role": role, "content": content} for role, content in turns]


def test_sem_turno_do_estudante_e_nenhum() -> None:
    result = classify_movement(code="programa {}", history=[])
    assert result["movement"] == "NENHUM"
    assert result["source"] == "nenhum"


def test_pedido_explicito_prevalece_sobre_a_regra_do_codigo() -> None:
    result = classify_movement(
        code="novo",
        history=_history(("user", "Já tentei, não consigo. Pode me mandar o código certo?")),
        errors=[],
        previous_code="antigo",
        previous_errors=["erro na linha 3"],
    )
    assert result["movement"] == "PEDIDO_EXPLICITO"


def test_frases_de_pressao_do_apendice_sao_pedido_explicito() -> None:
    frases = [
        "Não entendi. Me fala logo o que está errado.",
        "Já tentei de tudo, não consigo. Pode me mandar o código certo?",
        "Só me diz qual linha eu tenho que mudar.",
        "Não tenho tempo pra isso, qual é a resposta?",
        "Me mostra como fica o código arrumado, por favor.",
    ]
    for frase in frases:
        assert is_explicit_request(frase), frase


def test_pergunta_legitima_nao_e_pedido_explicito() -> None:
    assert not is_explicit_request("O que está errado na linha 3?")
    assert not is_explicit_request("Acho que o laço não termina porque i não muda.")


def test_erro_desaparece_apos_edicao_e_progresso() -> None:
    result = classify_movement(
        code="corrigido",
        history=_history(("user", "acho que era o tipo da variável")),
        errors=[],
        previous_code="com bug",
        previous_errors=["tipo incompatível na linha 2"],
    )
    assert result == {"movement": "PROGRESSO", "source": "codigo"}


def test_erro_novo_apos_edicao_e_regressao() -> None:
    result = classify_movement(
        code="pior",
        history=_history(("user", "mudei a linha do laço")),
        errors=["esperado } na linha 7"],
        previous_code="sem erro de compilacao",
        previous_errors=[],
    )
    assert result == {"movement": "REGRESSAO", "source": "codigo"}


def test_edicao_sem_mudar_o_compilador_e_estagnacao() -> None:
    result = classify_movement(
        code="mudou o espaçamento",
        history=_history(("user", "tentei mexer aqui e não resolveu")),
        errors=["tipo incompatível na linha 2"],
        previous_code="original",
        previous_errors=["tipo incompatível na linha 2"],
    )
    assert result == {"movement": "ESTAGNACAO", "source": "codigo"}


def test_sem_edicao_o_texto_decide() -> None:
    result = classify_movement(
        code="igual",
        history=_history(("user", "não sei o que fazer")),
        errors=["erro"],
        previous_code="igual",
        previous_errors=["erro"],
    )
    assert result == {"movement": "ESTAGNACAO", "source": "texto"}


def test_repetir_a_propria_fala_e_estagnacao() -> None:
    result = classify_movement(
        code="igual",
        history=_history(
            ("user", "o programa não imprime a média certa"),
            ("assistant", "o que você espera para a entrada 3?"),
            ("user", "O programa não imprime a média certa"),
        ),
        errors=[],
        previous_code="igual",
    )
    assert result["movement"] == "ESTAGNACAO"


def test_hipotese_com_conteudo_novo_e_progresso_pelo_texto() -> None:
    result = classify_movement(
        code="igual",
        history=_history(("user", "acho que a soma precisa ser dividida por 2 antes de imprimir")),
        errors=[],
        previous_code="igual",
    )
    assert result == {"movement": "PROGRESSO", "source": "texto"}


def test_erro_logico_sem_erro_de_compilacao_cai_no_texto() -> None:
    result = classify_movement(
        code="novo",
        history=_history(("user", "não entendi")),
        errors=[],
        previous_code="antigo",
        previous_errors=[],
    )
    assert result == {"movement": "ESTAGNACAO", "source": "texto"}
