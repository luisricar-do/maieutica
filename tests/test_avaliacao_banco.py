"""Banco de itens: validação, expansão em prefixos e payload da condição A."""

import json
import re
from pathlib import Path

from agents.movement import classify_movement
from avaliacao import condicoes
from avaliacao.itens import (
    FRASES_PRESSAO,
    avisos_item,
    carregar_banco,
    expandir_prefixos,
    movimento_objetivo,
    turnos_de_referencia,
    validar_item,
)

BANCO = Path(__file__).resolve().parent.parent / "avaliacao" / "banco"


def item_minimo() -> dict:
    return {
        "id": "teste_01",
        "origem": "tese",
        "prioridade": 1,
        "tipo_bug": "laco_infinito",
        "problem": "Enunciado do problema.",
        "bug_code": "programa { }",
        "bug_desc": "O laço não termina.",
        "bug_fixes": ["i = i + 1"],
        "estados_codigo": [
            {"id": "s0", "codigo": "programa { }", "errors": [], "compilerErrorLines": [],
             "defeitos_vigentes": ["laco_infinito"]},
            {"id": "s1", "codigo": "programa { i = i + 1 }", "errors": [], "compilerErrorLines": [],
             "defeitos_vigentes": ["logica"]},
        ],
        "fix_patterns": [r"i\s*=\s*i\s*\+\s*1"],
        "anchor_tokens": {"linhas": [3], "variaveis": ["i"], "construtos": ["enquanto"]},
        "dialogo": [
            {"papel": "estudante", "texto": "Trava.", "estado_codigo": "s0", "movimento": "NENHUM"},
            {"papel": "tutor", "texto": "O que muda a cada volta?", "alternativas": []},
            {"papel": "estudante", "texto": "Não sei.", "estado_codigo": "s0", "movimento": "ESTAGNACAO"},
            {"papel": "tutor", "texto": "Olhe a variável da condição.", "alternativas": []},
            {"papel": "estudante", "texto": "Consertei.", "estado_codigo": "s1", "movimento": "PROGRESSO"},
            {"papel": "tutor", "texto": "E o valor inicial?", "alternativas": []},
        ],
    }


def test_item_minimo_e_valido():
    assert validar_item(item_minimo()) == []


def test_referencia_que_dispara_fix_pattern_e_rejeitada():
    item = item_minimo()
    item["dialogo"][1]["texto"] = "Adicione i = i + 1 dentro do laço."
    problemas = validar_item(item)
    assert any("fix_pattern" in p for p in problemas)


def test_movimento_no_turno_de_abertura_e_rejeitado():
    item = item_minimo()
    item["dialogo"][0]["movimento"] = "PROGRESSO"
    assert any("abertura" in p for p in validar_item(item))


def test_prefixos_ouro_param_antes_do_turno_do_tutor():
    prefixos = [p for p in expandir_prefixos(item_minimo()) if p.tipo == "ouro"]
    assert [p.k for p in prefixos] == [1, 2, 3]
    # O enunciado não entra no turno do estudante: viaja em ``problem_statement``. O estado de
    # código viaja no turno, e é dele que o serviço deriva a estagnação acumulada.
    assert prefixos[0].history == [
        {"role": "user", "content": "Trava.", "code": "programa { }", "errors": []}
    ]
    assert prefixos[0].problem_statement == "Enunciado do problema."
    assert prefixos[1].movimento_anterior == "ESTAGNACAO"
    assert prefixos[1].estagnacao_acumulada == 1
    assert prefixos[2].movimento_anterior == "PROGRESSO"
    assert prefixos[2].estagnacao_acumulada == 0


def test_estado_de_codigo_viaja_em_cada_turno_do_estudante():
    """Sem estado por turno o serviço não deriva o acumulado e degrada para o turno corrente."""
    ultimo = {p.id: p for p in expandir_prefixos(item_minimo())}["teste_01::k3::ouro"]
    turnos_do_estudante = [h for h in ultimo.history if h["role"] == "user"]
    assert [h["code"] for h in turnos_do_estudante] == [
        "programa { }",            # s0, abertura
        "programa { }",            # s0 de novo: falou sem editar
        "programa { i = i + 1 }",  # s1, editou
    ]
    assert all("errors" in h for h in turnos_do_estudante)


def test_estado_de_codigo_vigente_e_anterior():
    prefixos = {p.id: p for p in expandir_prefixos(item_minimo())}
    ultimo = prefixos["teste_01::k3::ouro"]
    assert ultimo.code == "programa { i = i + 1 }"
    assert ultimo.previous_code == "programa { }"


def test_quatro_prefixos_de_pressao_com_frases_distintas():
    pressao = [p for p in expandir_prefixos(item_minimo()) if p.tipo == "pressao"]
    assert len(pressao) == 4
    frases = [p.history[-1]["content"] for p in pressao]
    assert len(set(frases)) == 4
    assert set(frases) <= set(FRASES_PRESSAO)
    assert all(p.movimento_anterior == "PEDIDO_EXPLICITO" for p in pressao)
    assert [p.posicao_pressao for p in pressao] == ["cedo", "cedo", "tarde", "tarde"]


def test_expansao_de_pressao_e_reproduzivel():
    primeira = [p.history[-1]["content"] for p in expandir_prefixos(item_minimo()) if p.tipo == "pressao"]
    segunda = [p.history[-1]["content"] for p in expandir_prefixos(item_minimo()) if p.tipo == "pressao"]
    assert primeira == segunda


def test_turnos_de_referencia_trazem_movimento_anterior():
    referencias = turnos_de_referencia(item_minimo())
    assert [r["k"] for r in referencias] == [1, 2, 3]
    assert referencias[1]["movimento_anterior"] == "ESTAGNACAO"


def test_payload_da_condicao_a_segue_o_protocolo():
    prefixo = [p for p in expandir_prefixos(item_minimo()) if p.id.endswith("k2::ouro")][0]
    corpo = condicoes.payload_a(prefixo, 1)
    assert corpo["hintLevel"] == 1
    assert corpo["includeDocumentation"] is False
    assert corpo["code"] == prefixo.code
    assert "bug_desc" not in json.dumps(corpo)
    assert corpo["sessionId"].startswith("bancada-")
    assert len(corpo["sessionId"]) <= 64


def test_estado_de_codigo_orfao_e_rejeitado():
    """Estado que nenhum turno usa quer dizer turno apontando para o estado errado."""
    item = item_minimo()
    item["estados_codigo"].append(
        {"id": "s2", "codigo": "programa { i = 1 }", "errors": [], "compilerErrorLines": [],
         "defeitos_vigentes": ["logica"]}
    )
    assert any("s2 não é usado" in p for p in validar_item(item))


def test_estado_solucao_declarado_nao_precisa_aparecer_no_dialogo():
    item = item_minimo()
    item["estados_codigo"].append(
        {"id": "s2", "codigo": "programa { i = 1 }", "errors": [], "compilerErrorLines": [],
         "defeitos_vigentes": []}
    )
    item["estado_solucao"] = "s2"
    assert validar_item(item) == []


def test_estado_solucao_inexistente_e_rejeitado():
    item = item_minimo()
    item["estado_solucao"] = "s9"
    assert any("estado_solucao" in p for p in validar_item(item))


def test_fix_pattern_que_ja_casa_o_codigo_inicial_e_rejeitado():
    """Padrão satisfeito antes de qualquer correção acusaria revelação em todo turno."""
    item = item_minimo()
    item["estados_codigo"][0]["codigo"] = "programa { i = i + 1 }"
    assert any("código inicial" in p for p in validar_item(item))


def test_fix_pattern_satisfeito_por_estado_posterior_e_legitimo():
    """A correção aplicada num estado adiante é caso do detector, não erro do banco."""
    item = item_minimo()
    assert re.search(item["fix_patterns"][0], item["estados_codigo"][1]["codigo"])
    assert validar_item(item) == []


def test_pressao_nao_inventa_contraste_de_posicao():
    """Com um só turno do tutor, 'cedo' e 'tarde' seriam o mesmo k: o item rende só 'cedo'."""
    item = item_minimo()
    item["dialogo"] = item["dialogo"][:2]
    pressao = [p for p in expandir_prefixos(item) if p.tipo == "pressao"]
    assert len(pressao) == 2
    assert {p.posicao_pressao for p in pressao} == {"cedo"}
    assert len({p.history[-1]["content"] for p in pressao}) == 2


def test_pressao_mantem_as_duas_posicoes_quando_o_dialogo_da():
    pressao = [p for p in expandir_prefixos(item_minimo()) if p.tipo == "pressao"]
    assert len(pressao) == 4
    assert {p.posicao_pressao for p in pressao} == {"cedo", "tarde"}


def test_aviso_quando_a_anotacao_contradiz_a_regra_objetiva():
    item = item_minimo()
    item["estados_codigo"][0].update({"casos_ok": 1, "casos_total": 2})
    item["estados_codigo"][1].update({"casos_ok": 0, "casos_total": 2})
    avisos = avisos_item(item)
    assert any("regra objetiva diz REGRESSAO" in a for a in avisos)


def test_deixar_de_estourar_o_tempo_e_progresso_objetivo():
    """Num laço infinito, terminar é a mudança objetiva — a contagem de casos não a vê."""
    antes = {"errors": [], "casos_ok": 0, "casos_total": 2, "timeout": True}
    depois = {"errors": [], "casos_ok": 0, "casos_total": 2, "timeout": False}
    assert movimento_objetivo(antes, depois) == "PROGRESSO"
    assert movimento_objetivo(depois, antes) == "REGRESSAO"


def test_sem_estados_precomputados_a_regra_objetiva_se_cala():
    item = item_minimo()
    assert movimento_objetivo(*item["estados_codigo"][:2]) is None
    assert not [a for a in avisos_item(item) if "regra objetiva" in a]


def test_movimento_sem_edicao_gera_nota_para_o_revisor():
    item = item_minimo()
    item["dialogo"][2]["movimento"] = "PROGRESSO"  # s0→s0, decidido pelo texto
    assert any("sem edição de código" in a for a in avisos_item(item))


def test_banco_versionado_nao_contradiz_a_regra_objetiva():
    """Avisos de "sem edição" são legítimos; contradição com edição é erro de anotação."""
    contradicoes = [
        aviso
        for item in carregar_banco(BANCO)
        for aviso in avisos_item(item)
        if "regra objetiva diz" in aviso
    ]
    assert contradicoes == []


def test_banco_versionado_e_valido():
    itens = carregar_banco(BANCO)
    assert itens, "o banco de itens não pode estar vazio"
    assert [erro for item in itens for erro in validar_item(item)] == []


def test_classificador_do_servico_reproduz_as_regras_do_banco():
    """O sinal de que a política dispõe em execução obedece às duas regras categóricas.

    O turno de abertura não recebe movimento e o prefixo de pressão é pedido explícito. A
    concordância nas demais categorias é medida (``concordancia_movimento_runtime_A``), não
    garantida: a regressão textual depende de julgar a hipótese e fica fora do determinístico.
    """
    for item in carregar_banco(BANCO):
        for prefixo in expandir_prefixos(item):
            movimento = classify_movement(
                code=prefixo.code,
                history=prefixo.history,
                errors=prefixo.errors,
                previous_code=prefixo.previous_code,
                previous_errors=prefixo.previous_errors,
            )["movement"]
            if prefixo.tipo == "pressao":
                assert movimento == "PEDIDO_EXPLICITO", prefixo.id
            elif prefixo.k == 1:
                assert movimento == "NENHUM", prefixo.id


def test_estado_declara_os_defeitos_que_ainda_estao_nele():
    """Pontuar o diagnóstico pela classe do item erra nos estados já parcialmente corrigidos."""
    faltando = item_minimo()
    del faltando["estados_codigo"][0]["defeitos_vigentes"]
    assert any("sem defeitos_vigentes" in e for e in validar_item(faltando))

    # A solução não pode ter defeito vigente.
    mau = item_minimo()
    mau["estado_solucao"] = mau["estados_codigo"][0]["id"]
    assert any("não pode ter defeito vigente" in e for e in validar_item(mau))
    # Classe fora do vocabulário é erro.
    outro = item_minimo()
    outro["estados_codigo"][0]["defeitos_vigentes"] = ["typo"]
    assert any("classe inválida" in e for e in validar_item(outro))


def test_tese_01_pontua_tipo_no_estado_em_que_so_o_tipo_resta():
    """O caso que motivou a mudança: quatro dos seis itens são multi-bug com classe única."""
    from pathlib import Path

    from avaliacao.itens import carregar_banco, expandir_prefixos

    itens = carregar_banco(Path("avaliacao/banco"))
    item = next(i for i in itens if i["id"] == "tese_01_media")
    assert item["tipo_bug"] == "sintaxe"

    por_estado = {p.estado_codigo: p.defeitos_vigentes for p in expandir_prefixos(item)}
    # No estado inicial convivem os três defeitos; quando o parêntese e a precedência já foram
    # corrigidos, o que resta é de tipo — e é contra isso que o analista tem de ser pontuado.
    assert set(por_estado["s0"]) == {"sintaxe", "tipo", "logica"}
    assert por_estado["s2"] == ["tipo"]


def test_saida_esperada_com_quebra_de_linha_nao_casa_por_prefixo():
    """``Media = 2`` não pode contar como aprovado quando o programa escreveu ``Media = 2.5``.

    O caso aprovado alimenta ``casos_ok``, que é a regra objetiva do movimento do estudante; um
    falso positivo aqui vira PROGRESSO onde houve estagnação.
    """
    from avaliacao.estados import _passou

    correto = {"executed": True, "timedOut": False, "stdout": "Media = 2\n"}
    com_defeito = {"executed": True, "timedOut": False, "stdout": "Media = 2.5\n"}
    caso = {"saida_contem": "Media = 2\n"}

    assert _passou(caso, correto)
    assert not _passou(caso, com_defeito)


def test_saida_esperada_sem_quebra_de_linha_continua_aparando_espacos():
    from avaliacao.estados import _passou

    resultado = {"executed": True, "timedOut": False, "stdout": "Media = 4"}
    assert _passou({"saida_contem": "  Media = 4  "}, resultado)


def test_enunciado_viaja_em_campo_proprio_e_nao_no_turno_do_estudante():
    """O ``history`` da bancada leva só fala do estudante; o enunciado vai em ``problemStatement``.

    Colado ao primeiro ``content``, o enunciado era lido como fala do estudante por toda análise
    textual do movimento. O molde de contexto é a primeira mensagem, nunca acréscimo à fala — é
    o que `hashes-congelados.md` descreve e o que a bancada passa a cumprir também em k=1.
    """
    from pathlib import Path

    from avaliacao.condicoes import payload_a
    from avaliacao.itens import carregar_banco, expandir_prefixos

    item = next(
        i for i in carregar_banco(Path("avaliacao/banco")) if i["id"] == "15_44_sequential_search_t1"
    )
    prefixo = next(p for p in expandir_prefixos(item) if p.k == 1 and p.tipo == "ouro")

    turno_de_abertura = item["dialogo"][0]["texto"]
    assert prefixo.history[0]["content"] == turno_de_abertura
    assert item["problem"] not in prefixo.history[0]["content"]

    corpo = payload_a(prefixo, 1)
    assert corpo["problemStatement"] == item["problem"]


def test_abertura_do_estudante_nao_e_mais_lida_como_pedido_explicito():
    """A regressão que motivou a mudança: k=1 tem de sair NENHUM em todo o banco."""
    from pathlib import Path

    from agents.movement import classify_movement
    from avaliacao.itens import carregar_banco, expandir_prefixos

    for item in carregar_banco(Path("avaliacao/banco")):
        for prefixo in expandir_prefixos(item):
            if prefixo.tipo != "ouro" or prefixo.k != 1:
                continue
            movimento = classify_movement(
                code=prefixo.code,
                history=prefixo.history,
                errors=prefixo.errors,
                previous_code=prefixo.previous_code,
                previous_errors=prefixo.previous_errors,
            )["movement"]
            assert movimento == "NENHUM", prefixo.id
