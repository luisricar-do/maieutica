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


def test_turno_de_abertura_nao_recebe_movimento() -> None:
    """O primeiro turno do estudante não tem turno anterior contra o qual comparar."""
    result = classify_movement(
        code="programa {}",
        history=_history(("user", "O programa nao roda e eu nao entendi o erro que aparece.")),
        errors=["Linha 8: código incompleto"],
    )
    assert result == {"movement": "NENHUM", "source": "nenhum"}


def test_pedido_explicito_na_abertura_prevalece_sobre_nenhum() -> None:
    result = classify_movement(
        code="programa {}",
        history=_history(("user", "Nem tentei ainda, me manda o código certo.")),
    )
    assert result["movement"] == "PEDIDO_EXPLICITO"


def test_fala_longa_fora_do_foco_e_estagnacao() -> None:
    """Comprimento não é progresso: sem hipótese e sem âncora no código, é estagnação."""
    result = classify_movement(
        code="programa { inteiro media }",
        history=_history(
            ("user", "meu programa nao roda"),
            ("assistant", "o que o compilador aponta?"),
            ("user", "professor, isso aqui e muito dificil, ninguem consegue fazer essa materia"),
        ),
        errors=["Linha 8: código incompleto"],
        previous_code="programa { inteiro media }",
    )
    assert result == {"movement": "ESTAGNACAO", "source": "texto"}


def test_repeticao_aproximada_e_estagnacao() -> None:
    """Dizer o mesmo com outras palavras é repetição, não conteúdo novo."""
    result = classify_movement(
        code="igual",
        history=_history(
            ("user", "o programa nao imprime a media certa dos tres numeros"),
            ("assistant", "o que você espera para a entrada 3?"),
            ("user", "o programa nao imprime a media certa dos tres valores"),
        ),
        errors=[],
        previous_code="igual",
    )
    assert result == {"movement": "ESTAGNACAO", "source": "texto"}


def test_mencao_ao_simbolo_do_codigo_e_progresso() -> None:
    """Sem marca de hipótese, mas ancorada no programa: está no foco da tarefa."""
    result = classify_movement(
        code="programa { inteiro media\n media = a + b + c / 3 }",
        history=_history(
            ("user", "nao roda"),
            ("assistant", "o que o compilador aponta?"),
            ("user", "a variavel media guarda so a parte sem virgula do resultado"),
        ),
        errors=[],
        previous_code="programa { inteiro media\n media = a + b + c / 3 }",
    )
    assert result == {"movement": "PROGRESSO", "source": "texto"}


def _bloqueio(fala: str) -> dict:
    """Fala de bloqueio no 3.º turno, sem edição de código, sobre um programa com `se/entao`."""
    codigo = (
        'algoritmo "aprovacao"\n'
        "var nota: real\n"
        "inicio\n"
        "  leia(nota)\n"
        "  se (nota > 6.0) entao\n"
        '    escreva("Aprovado")\n'
        "  senao\n"
        '    escreva("Reprovado")\n'
        "  fimse\n"
        "fimalgoritmo"
    )
    return classify_movement(
        code=codigo,
        history=_history(
            ("user", "meu programa classifica errado"),
            ("assistant", "o que observaste?"),
            ("user", fala),
        ),
        errors=[],
    )


def test_conectivo_sozinho_nao_e_hipotese() -> None:
    """O defeito que derruba H1: fala de bloqueio contada como progresso, e o tutor não escala.

    "então", "pois", "ou seja", "por que" e "logo" são conectivos de discurso — aparecem tanto
    em raciocínio como em queixa. Só o causal "porque", que introduz uma razão, marca hipótese.
    """
    for fala in (
        "entao o que eu faco agora",
        "pois e, complicado isso",
        "ou seja, me perdi de vez",
        "e logo depois disso o que acontece",
        "por que isso nao funciona?",
    ):
        assert _bloqueio(fala)["movement"] == "ESTAGNACAO", fala

    assert _bloqueio("porque a comparacao usa maior e nao maior ou igual")["movement"] == "PROGRESSO"


def test_palavra_chave_do_portugol_nao_serve_de_ancora() -> None:
    """`entao` está em todo programa com `se`: ancorar nela faria qualquer fala parecer no foco."""
    assert _bloqueio("entao eu nao sei mais o que fazer aqui")["movement"] == "ESTAGNACAO"
    # Símbolo do domínio do problema continua a ancorar.
    assert _bloqueio("a nota 6 esta caindo no lado errado")["movement"] == "PROGRESSO"


def test_verbo_de_desfecho_negado_e_queixa_nao_observacao() -> None:
    assert _bloqueio("isso nao funciona de jeito nenhum")["movement"] == "ESTAGNACAO"
    assert _bloqueio("agora funciona certo")["movement"] == "PROGRESSO"
    # Com ação declarada, o relato vale mesmo que o desfecho seja negativo.
    assert _bloqueio("testei e nao deu certo")["movement"] == "PROGRESSO"


def test_afirmar_que_esta_certo_sem_edicao_e_regressao() -> None:
    """A ``REGRESSAO`` textual na única forma que uma regra determinística alcança.

    O episódio está aberto por construção — o estudante trouxe um defeito e não mexeu no código.
    Endossar o comportamento atual é adotar um modelo errado, e isso decide-se pela forma da
    fala, não por julgar o conteúdo da hipótese.
    """
    resultado = classify_movement(
        code="se (nota > 6.0) entao",
        history=_history(
            ("user", "meu programa classifica errado quem tira exatamente 6"),
            ("assistant", "o que aconteceu quando testaste com 6?"),
            (
                "user",
                "Testei com 6 e escreveu Reprovado. Mas eu acho que esta certo, "
                "porque 6 nao e maior que 6.",
            ),
        ),
        errors=[],
    )
    assert resultado["movement"] == "REGRESSAO"
    assert resultado["source"] == "texto"


def test_duvida_sobre_estar_certo_nao_e_regressao() -> None:
    """Perguntar ou hesitar não é afirmar: a regra exige asserção."""
    for fala, esperado in (
        ("Sera que esta certo assim?", "ESTAGNACAO"),
        ("Nao sei se esta certo ou nao.", "ESTAGNACAO"),
        ("Voce acha que esta certo?", "ESTAGNACAO"),
    ):
        resultado = classify_movement(
            code="se (nota > 6.0) entao",
            history=_history(
                ("user", "meu programa classifica errado"),
                ("assistant", "o que observaste?"),
                ("user", fala),
            ),
            errors=[],
        )
        assert resultado["movement"] == esperado, fala


def test_afirmar_que_esta_certo_apos_edicao_deixa_o_codigo_decidir() -> None:
    """Com edição, "agora está certo" é relato de correção — quem decide é o compilador."""
    resultado = classify_movement(
        code="novo codigo corrigido",
        history=_history(
            ("user", "nao compila"),
            ("assistant", "o que o compilador aponta?"),
            ("user", "Mexi na linha e agora esta certo, parou de acusar erro."),
        ),
        errors=[],
        previous_code="codigo antigo",
        previous_errors=["Linha 3, coluna 1: erro"],
    )
    assert resultado["movement"] == "PROGRESSO"
    assert resultado["source"] == "codigo"


def test_enunciado_colado_a_fala_nao_vira_pedido_explicito():
    """O "corrija" do enunciado não pode ser lido como pedido do estudante.

    O ``content`` que chega ao classificador traz o enunciado do exercício colado à fala, e
    ``_normalize`` colapsa a quebra de linha entre os dois. Com um ``.*`` entre as duas metades
    do padrão, "Localize e corrija" (enunciado) casava com "o meu código" (estudante) como se
    fossem um pedido só — inflando o denominador de H2 e fazendo a política endurecer contra uma
    exigência que nunca houve.
    """
    from agents.movement import is_explicit_request

    enunciado = "O programa contem um defeito. Localize e corrija."
    fala = "Oi! O meu codigo passa em todos os casos de teste menos no primeiro. Voce pode ajudar?"

    assert not is_explicit_request(f"{enunciado}\n\n{fala}")
    assert not is_explicit_request(fala)


# A guarda que prende esta regra às frases de pressão da bancada — as de H2 — mudou-se para o
# repositório `maieutica-avaliacoes` (`tests/test_frases_de_pressao.py`), junto das frases. Mexer
# no padrão acima sem correr aquela suíte pode desarmá-las em silêncio, e H2 passa a medir uma
# exigência que nunca houve.
