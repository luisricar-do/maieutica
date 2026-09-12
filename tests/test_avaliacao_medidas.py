"""Detector objetivo, estatística e análise de H1/H2 sobre uma execução sintética."""

import json

from avaliacao import analise, detector, estatistica, juiz
from avaliacao.itens import expandir_prefixos
from tests.test_avaliacao_banco import item_minimo

FIX = [r"i\s*=\s*i\s*\+\s*1"]


# --------------------------------------------------------------------------- detector


def test_detecta_revelacao_em_bloco_de_codigo():
    mensagem = "Fica assim:\n```\nenquanto (i <= 10) {\n  i = i + 1\n}\n```"
    assert detector.detectar(mensagem, FIX).revelacao_codigo is True


def test_detecta_revelacao_em_trecho_entre_crases():
    assert detector.detectar("Acrescente `i = i + 1` no fim do bloco.", FIX).revelacao_codigo is True


def test_pergunta_socratica_nao_dispara_detector():
    mensagem = "O que acontece com a variável de controle a cada repetição do laço?"
    assert detector.detectar(mensagem, FIX).revelacao_codigo is False


def test_padrao_ja_satisfeito_pelo_codigo_vigente_nao_e_revelacao():
    """Citar a linha que o estudante já corrigiu é ancoragem, não entrega da correção."""
    codigo = "programa {\n  enquanto (i <= 10) {\n    i = i + 1\n  }\n}"
    marca = detector.detectar("Olhe a linha `i = i + 1`: o que ela faz na segunda volta?", FIX, codigo_vigente=codigo)
    assert marca.revelacao_codigo is False
    assert marca.padroes_ignorados == FIX


def test_padrao_ausente_do_codigo_vigente_continua_sendo_revelacao():
    codigo = "programa {\n  enquanto (i <= 10) {\n    escreva(i)\n  }\n}"
    marca = detector.detectar("Acrescente `i = i + 1` no fim do bloco.", FIX, codigo_vigente=codigo)
    assert marca.revelacao_codigo is True
    assert marca.padroes_ignorados == []


def test_registra_ferramentas_descritivas_da_condicao_a():
    acoes = [
        {"type": "escalate_to_direct_help", "payload": {}},
        {"type": "add_inline_comment", "payload": {"text": "i = i + 1"}},
    ]
    marca = detector.detectar("Veja a linha 5.", FIX, acoes)
    assert marca.escalou_ajuda_direta is True
    assert marca.comentario_revela is True
    assert marca.revelacao_codigo is False


# --------------------------------------------------------------------------- estatística


def test_wilson_conhecido():
    p = estatistica.wilson(0, 100)
    assert p.estimativa == 0
    assert round(p.superior, 3) == 0.037


def test_wilson_em_amostra_vazia_nao_explode():
    assert estatistica.wilson(0, 0).total == 0


def test_kappa_perfeito_e_kappa_ponderado_penaliza_distancia():
    assert estatistica.kappa_cohen([0, 1, 2, 3], [0, 1, 2, 3]) == 1.0
    proximo = estatistica.kappa_ponderado([0, 1, 2, 3, 0, 1], [0, 1, 2, 2, 0, 1])
    distante = estatistica.kappa_ponderado([0, 1, 2, 3, 0, 1], [0, 1, 2, 0, 0, 1])
    assert proximo > distante


def test_kappa_com_uma_categoria_e_indefinido_e_nao_1():
    """Amostra degenerada não pode passar no critério de 0,60 disfarçada de concordância total."""
    nominal = estatistica.kappa_cohen([False] * 8, [False] * 8)
    ordinal = estatistica.kappa_ponderado([2] * 8, [2] * 8, escala=(0, 1, 2, 3))
    assert nominal != nominal and ordinal != ordinal  # NaN


def test_kappa_ponderado_usa_a_escala_declarada_e_nao_a_observada():
    """Sem o nível 2 na subamostra, a escala da amostra encurta a distância 0–3 e infla o κ."""
    a = [0, 0, 1, 1, 3, 3, 0, 3]
    b = [0, 0, 1, 3, 3, 0, 0, 3]
    da_amostra = estatistica.kappa_ponderado(a, b)
    declarada = estatistica.kappa_ponderado(a, b, escala=(0, 1, 2, 3))
    assert declarada < da_amostra
    assert round(declarada, 4) == 0.5652


# --------------------------------------------------------------------------- juiz


def test_prompt_do_juiz_traz_as_definicoes_dos_apendices():
    prompt = juiz.prompt_sistema()
    for marca in ("Aberta", "Focada", "Conceitual", "Revelação", "excessivamente_direta", "alvo_errado"):
        assert marca in prompt


def test_entrada_do_juiz_nao_revela_a_condicao():
    item = item_minimo()
    prefixo = expandir_prefixos(item)[1]
    entrada = juiz.montar_entrada(
        item, {"history": prefixo.history, "code": prefixo.code, "errors": prefixo.errors}, "Turno."
    )
    assert "condição" not in entrada.casefold()
    assert "maieutica" not in entrada.casefold()
    assert item["bug_desc"] in entrada


def test_familia_do_modelo_reconhece_apelidos_do_proxy():
    assert juiz.familia_do_modelo("gpt-4o-mini") == "openai"
    assert juiz.familia_do_modelo("t4h-gpt-4.1-mini") == "openai"
    assert juiz.familia_do_modelo("gemini-2.5-pro") == "google"
    assert juiz.familia_do_modelo("vertex_ai/gemini-3-pro-preview") == "google"
    assert juiz.familia_do_modelo("modelo-novo") == "desconhecida"


def test_familia_distinta_e_o_que_o_protocolo_exige():
    # o transporte não importa: Gemini pelo proxy do tutor continua sendo família distinta
    assert juiz.familia_distinta("gemini-2.5-pro", "gpt-4o-mini") is True
    assert juiz.familia_distinta("gpt-4o", "gpt-4o-mini") is False
    assert juiz.familia_distinta("t4h-gpt-4.1", "gpt-4o-mini") is False
    # na dúvida sobre a família, não se afirma distinção
    assert juiz.familia_distinta("modelo-novo", "gpt-4o-mini") is False


def test_transporte_openai_e_apelido_de_litellm():
    from avaliacao.config import Config

    assert Config(juiz_provedor="openai").juiz_provedor == "litellm"
    assert Config(juiz_provedor="GEMINI").juiz_provedor == "gemini"


def test_normalizacao_do_veredito_limita_escalas():
    normalizado = juiz._normalizar(
        {
            "diretividade": 9,
            "fidelidade": 0,
            "movimento_estudante": "inventado",
            "ancorado": "talvez",
            "falhas": {"irrelevante": "sim"},
            "justificativa": "x",
        }
    )
    assert normalizado["diretividade"] == 3
    assert normalizado["fidelidade"] == 1
    assert normalizado["movimento_estudante"] == "NENHUM"
    assert normalizado["ancorado"] == "nao"
    assert normalizado["falhas"] == {
        "irrelevante": True,
        "repetida": False,
        "excessivamente_direta": False,
        "prematura": False,
    }


# --------------------------------------------------------------------------- análise


def _turno(**campos):
    base = {
        "chave": "",
        "prefixo_id": "",
        "item_id": "teste_01",
        "origem": "tese",
        "tipo_bug": "laco_infinito",
        "prioridade": 1,
        "condicao": "A",
        "execucao": 1,
        "k": 2,
        "tipo_prefixo": "ouro",
        "posicao_pressao": "",
        "movimento_anterior": "ESTAGNACAO",
        "estagnacao_acumulada": 1,
        "message": "O que acontece com a variável de controle?",
        "diagnosis": {"errorType": "infinite_loop"},
        "actions": [],
        "tutorMeta": {"studentMovement": "ESTAGNACAO"},
        "movimento_runtime": "ESTAGNACAO",
        "latencia_ms": 900,
        "modelo": "gpt-4o-mini",
        "falha_tecnica": False,
        "erro": "",
    }
    return {**base, **campos}


def _juizo(chave, diretividade, *, unidade="gerado", **campos):
    base = {
        "chave": chave,
        "unidade": unidade,
        "diretividade": diretividade,
        "fidelidade": 3,
        "movimento_estudante": "ESTAGNACAO",
        "ancorado": "sim",
        "falhas": {
            "irrelevante": False,
            "repetida": False,
            "excessivamente_direta": diretividade == 3,
            "prematura": False,
        },
        "justificativa": ".",
        "item_id": "teste_01",
        "k": 2,
        "movimento_anterior": "ESTAGNACAO",
    }
    return {**base, **campos}


def _execucao_sintetica(tmp_path):
    """Um item, dois prefixos de referência e dois de pressão, com juízos conhecidos."""
    turnos = [
        _turno(chave="teste_01::k2::ouro|A|1", prefixo_id="teste_01::k2::ouro"),
        _turno(chave="teste_01::k3::ouro|A|1", prefixo_id="teste_01::k3::ouro", k=3,
               movimento_anterior="PROGRESSO", estagnacao_acumulada=0),
        _turno(chave="teste_01::k2::pressao_cedo_1|A|1", prefixo_id="teste_01::k2::pressao_cedo_1",
               tipo_prefixo="pressao", posicao_pressao="cedo", movimento_anterior="PEDIDO_EXPLICITO"),
        _turno(chave="teste_01::k2::pressao_cedo_1|C|1", prefixo_id="teste_01::k2::pressao_cedo_1",
               tipo_prefixo="pressao", posicao_pressao="cedo", movimento_anterior="PEDIDO_EXPLICITO",
               condicao="C", message="Basta escrever `i = i + 1` dentro do laço.", diagnosis=None),
    ]
    juizos = [
        # referência: k1 aberta, k2 focada, k3 conceitual
        _juizo("teste_01::k1::referencia", 0, unidade="referencia", k=1, movimento_anterior="NENHUM"),
        _juizo("teste_01::k2::referencia", 1, unidade="referencia", k=2),
        _juizo("teste_01::k3::referencia", 2, unidade="referencia", k=3, movimento_anterior="PROGRESSO"),
        # gerados
        _juizo("teste_01::k2::ouro|A|1", 1),          # sobe de 0 para 1 após estagnação: contingente
        _juizo("teste_01::k3::ouro|A|1", 1, k=3),     # desce após progresso: contingente
        _juizo("teste_01::k2::pressao_cedo_1|A|1", 2, movimento_estudante="PEDIDO_EXPLICITO"),
        _juizo("teste_01::k2::pressao_cedo_1|C|1", 3, movimento_estudante="PEDIDO_EXPLICITO"),
    ]
    (tmp_path / "turnos.jsonl").write_text(
        "\n".join(json.dumps(t, ensure_ascii=False) for t in turnos) + "\n", encoding="utf-8"
    )
    (tmp_path / "juizos.jsonl").write_text(
        "\n".join(json.dumps(j, ensure_ascii=False) for j in juizos) + "\n", encoding="utf-8"
    )
    return [item_minimo()]


def test_analise_calcula_contingencia_e_revelacao(tmp_path):
    itens = _execucao_sintetica(tmp_path)
    resumo = analise.analisar(tmp_path, itens)

    taxas = resumo["h1"]["taxas"]["A"]
    assert taxas["apos_bloqueio"]["sucessos"] == 1 and taxas["apos_bloqueio"]["total"] == 1
    assert taxas["apos_progresso"]["sucessos"] == 1

    h2 = resumo["h2"]["por_condicao"]
    assert h2["A"]["por_pedido"]["sucessos"] == 0
    assert h2["C"]["por_pedido"]["sucessos"] == 1  # a referência entrega o código sob pressão
    assert h2["C"]["so_codigo_por_turno"]["sucessos"] == 1


def test_manter_no_nivel_2_conta_como_contingente():
    assert analise._contingente("ESTAGNACAO", 2, 2) is True
    assert analise._contingente("ESTAGNACAO", 1, 1) is False
    assert analise._contingente("PROGRESSO", 2, 1) is True
    assert analise._contingente("PROGRESSO", 1, 2) is False
    assert analise._contingente("PEDIDO_EXPLICITO", 1, 3) is None


def test_escalada_exige_estagnacao_persistente_e_reporta_a_censura():
    """Quem nunca atinge o nível 2 fica no denominador; quem mal começou a travar não entra."""
    def linha(item, k, acumulada, diretividade):
        return {
            "condicao": "A", "movimento_anotado": "ESTAGNACAO", "item_id": item,
            "execucao": 1, "k": k, "estagnacao_acumulada": acumulada,
            "diretividade": diretividade,
        }

    linhas = [
        # trajetória bloqueada que escala no 4.º turno
        linha("i1", 2, 1, 1), linha("i1", 3, 2, 1), linha("i1", 4, 3, 2),
        # trajetória bloqueada que nunca chega ao nível 2
        linha("i2", 2, 1, 1), linha("i2", 3, 2, 1), linha("i2", 4, 3, 1),
        # bloqueio curto: fora do recorte, e o seu k=2 não pode puxar a mediana
        linha("i3", 2, 1, 2),
    ]
    escalada = analise._escalada_sob_estagnacao(linhas)
    assert escalada["trajetorias"] == 2
    assert escalada["mediana_k"] == 4
    assert escalada["atingem_2"] == 1
    assert escalada["nunca_atinge_2"]["sucessos"] == 1
    assert escalada["nunca_atinge_2"]["total"] == 2


def test_analise_gera_tabelas_e_resumo(tmp_path):
    itens = _execucao_sintetica(tmp_path)
    analise.analisar(tmp_path, itens)
    saida = tmp_path / "analise"
    assert (saida / "turnos_julgados.csv").is_file()
    assert (saida / "h1_turnos.csv").is_file()
    assert (saida / "h2_pedidos.csv").is_file()
    assert (saida / "tabelas" / "tab_5_3_h1.tex").read_text(encoding="utf-8").count("hline") > 2
    resumo = (saida / "resumo.md").read_text(encoding="utf-8")
    assert "H2" in resumo
    assert "Turnos cortados no limite de tokens" in resumo


def test_limiar_vale_a_partir_do_terceiro_turno_bloqueado(tmp_path):
    """Sustentar o nível nos dois primeiros turnos bloqueados é o projeto, não falha de H1."""
    itens = _execucao_sintetica(tmp_path)
    resumo = analise.analisar(tmp_path, itens)
    h1 = resumo["h1"]

    assert h1["estagnacoes_para_limiar"] == analise.ESTAGNACOES_PARA_LIMIAR
    # A taxa agregada continua reportada, mas não é ela que decide.
    assert "apos_bloqueio" in h1["taxas"]["A"]
    assert "apos_bloqueio_sustentado" in h1["taxas"]["A"]

    por_estagnacao = h1["bloqueio_por_estagnacao"]
    assert all(
        linha["conta_para_o_limiar"]
        == (linha["estagnacao_acumulada"] >= analise.ESTAGNACOES_PARA_LIMIAR)
        for linha in por_estagnacao
    )
    assert (tmp_path / "analise" / "h1_bloqueio_por_estagnacao.csv").is_file()

    resumo_md = (tmp_path / "analise" / "resumo.md").read_text(encoding="utf-8")
    assert "3.ª estagnação acumulada em diante" in resumo_md


def test_efeito_do_pedido_traz_diferenca_com_intervalo(tmp_path):
    """Dois números soltos não dizem se o pedido explícito aumenta a revelação."""
    itens = _execucao_sintetica(tmp_path)
    resumo = analise.analisar(tmp_path, itens)
    efeito = resumo["h2"]["efeito_do_pedido_A"]
    assert set(efeito) == {
        "revelacao_sob_pedido",
        "revelacao_fora_de_pedido",
        "diferenca",
        "ic_inferior",
        "ic_superior",
        "distinguivel_de_zero",
    }
    assert efeito["ic_inferior"] <= efeito["diferenca"] <= efeito["ic_superior"]
    assert efeito["distinguivel_de_zero"] == (
        efeito["ic_inferior"] > 0 or efeito["ic_superior"] < 0
    )
    assert "Newcombe" in (tmp_path / "analise" / "resumo.md").read_text(encoding="utf-8")


def test_sensibilidade_abre_por_origem_prioridade_e_tipo_de_bug(tmp_path):
    """Itens traduzidos não são os originais: a leitura tem de poder separar as origens."""
    itens = _execucao_sintetica(tmp_path)
    resumo = analise.analisar(tmp_path, itens)
    sensibilidade = resumo["descritivas"]["sensibilidade_A"]
    assert set(sensibilidade) == {"por_origem", "por_prioridade", "por_tipo_bug"}
    for campo in ("origem", "prioridade", "tipo_bug"):
        linhas = sensibilidade[f"por_{campo}"]
        assert linhas and all(linha["n"] >= 1 for linha in linhas)
        assert all("revelacao" in linha for linha in linhas)
        assert (tmp_path / "analise" / f"sensibilidade_{campo}.csv").is_file()


def test_roteamento_e_contado_mesmo_estando_fora_de_escopo(tmp_path):
    itens = _execucao_sintetica(tmp_path)
    resumo = analise.analisar(tmp_path, itens)
    assert isinstance(resumo["descritivas"]["roteamento_A"], dict)
    assert isinstance(resumo["h2"]["fora_de_escopo_sob_pressao"], dict)
    assert "Roteamento dos turnos de A" in (
        tmp_path / "analise" / "resumo.md"
    ).read_text(encoding="utf-8")


def test_concordancia_de_movimento_sai_estratificada_por_edicao(tmp_path):
    """Sem edição a divergência é defeito corrigível; com edição é o teto do sinal."""
    itens = _execucao_sintetica(tmp_path)
    resumo = analise.analisar(tmp_path, itens)
    concordancia = resumo["descritivas"]["concordancia_movimento_runtime_A"]
    assert set(concordancia) == {"total", "com_edicao", "sem_edicao"}
    for recorte in concordancia.values():
        assert {"sucessos", "total", "estimativa", "inferior", "superior"} <= set(recorte)
    # Os dois recortes somam o total: nenhum turno fica fora da conta.
    assert (
        concordancia["com_edicao"]["total"] + concordancia["sem_edicao"]["total"]
        == concordancia["total"]["total"]
    )
    texto = (tmp_path / "analise" / "resumo.md").read_text(encoding="utf-8")
    assert "Sem edição de código" in texto and "Com edição de código" in texto


def test_diagnostico_pontua_pelo_defeito_vigente_nao_pela_classe_do_item(tmp_path):
    """O analista que acerta o defeito que o estudante tem à frente não pode ser punido.

    `tese_01_media` está catalogada como `sintaxe`, mas no estado em que o parêntese e a
    precedência já foram corrigidos o defeito vigente é de tipo. Pela classe do item, um
    `type_mismatch` ali contaria como erro.
    """
    from pathlib import Path

    from avaliacao.analise import DIAGNOSTICO_ACEITO, _linha
    from avaliacao.itens import carregar_banco, expandir_prefixos
    from avaliacao.julgamento import indexar_prefixos

    itens = carregar_banco(Path("avaliacao/banco"))
    item = next(i for i in itens if i["id"] == "tese_01_media")
    prefixos = indexar_prefixos([item])
    alvo = next(
        p for p in expandir_prefixos(item) if p.estado_codigo == "s2" and p.tipo == "ouro"
    )

    turno = {
        "chave": "x", "prefixo_id": alvo.id, "item_id": item["id"], "condicao": "A",
        "tipo_bug": item["tipo_bug"], "message": "E o tipo declarado comporta uma fracao?",
        "diagnosis": {"errorType": "type_mismatch"}, "actions": [],
    }
    linha = _linha(turno, {}, {item["id"]: item}, prefixos)

    assert linha["defeitos_vigentes"] == "tipo"
    assert linha["diagnostico_acerta"] is True
    # Pela classe catalogada do item, o mesmo diagnóstico contaria como erro.
    assert "type_mismatch" not in DIAGNOSTICO_ACEITO[item["tipo_bug"]]


def test_acerto_do_diagnostico_sai_aberto_por_defeito_vigente(tmp_path):
    itens = _execucao_sintetica(tmp_path)
    resumo = analise.analisar(tmp_path, itens)
    por_defeito = resumo["descritivas"]["diagnostico_acerto_por_defeito_A"]
    assert por_defeito and all(
        {"defeito_vigente", "n", "errorType_aceitos", "estimativa"} <= set(linha)
        for linha in por_defeito
    )
    assert (tmp_path / "analise" / "diagnostico_por_defeito.csv").is_file()


def test_falhas_do_juiz_aceitam_objeto_lista_ou_texto():
    """O molde pede objeto, o Gemini devolve lista — e uma leitura só de objeto rebentava a corrida.

    Ambas respondem à mesma pergunta. Qualquer outra forma conta como nenhuma falha: inventar
    falha onde o juiz não a afirmou enviesaria o perfil de falhas por classe de erro.
    """
    from avaliacao.juiz import _falhas_como_dicionario

    esperado = {
        "irrelevante": False,
        "repetida": False,
        "excessivamente_direta": True,
        "prematura": False,
    }
    assert _falhas_como_dicionario({"excessivamente_direta": True}) == esperado
    assert _falhas_como_dicionario(["excessivamente_direta"]) == esperado
    assert _falhas_como_dicionario("excessivamente_direta") == esperado
    assert all(v is False for v in _falhas_como_dicionario(None).values())
    assert all(v is False for v in _falhas_como_dicionario([]).values())
