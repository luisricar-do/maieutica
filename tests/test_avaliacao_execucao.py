"""Execução, julgamento e validação humana, com as chamadas de rede substituídas."""

import json
from pathlib import Path

import pytest

from avaliacao import condicoes, executor, http, juiz, julgamento, validacao_humana
from avaliacao.config import Config
from avaliacao.itens import expandir_prefixos
from avaliacao.registro import ler_ndjson
from tests.test_avaliacao_banco import item_minimo

CFG = Config(api_base="http://teste/api", litellm_base="http://teste/v1", paralelismo=1)


def _prefixos():
    return [p for p in expandir_prefixos(item_minimo()) if p.tipo == "ouro"]


def test_executor_registra_um_turno_por_chamada(tmp_path, monkeypatch):
    monkeypatch.setattr(
        condicoes, "executar_a", lambda cfg, prefixo, execucao: {"message": "resposta", "erro": ""}
    )
    resumo = executor.executar(
        CFG, _prefixos(), tmp_path, condicoes_alvo=("A",), execucoes=2, ao_terminar=None
    )
    turnos = list(ler_ndjson(tmp_path / executor.ARQUIVO_TURNOS))
    assert resumo["ok"] == len(turnos) == len(_prefixos()) * 2
    assert {t["execucao"] for t in turnos} == {1, 2}
    assert all(t["chave"].count("|") == 2 for t in turnos)


def test_executor_retoma_sem_repetir_chamadas(tmp_path, monkeypatch):
    chamadas = {"n": 0}

    def falsa(cfg, prefixo, execucao):
        chamadas["n"] += 1
        return {"message": "resposta", "erro": ""}

    monkeypatch.setattr(condicoes, "executar_a", falsa)
    executor.executar(CFG, _prefixos(), tmp_path, condicoes_alvo=("A",), execucoes=1)
    primeiro = chamadas["n"]
    resumo = executor.executar(CFG, _prefixos(), tmp_path, condicoes_alvo=("A",), execucoes=1)
    assert chamadas["n"] == primeiro
    assert resumo["planejados"] == 0 and resumo["reaproveitados"] == primeiro


def test_falha_persistente_vira_falha_tecnica_depois_das_reexecucoes(tmp_path, monkeypatch):
    tentativas = {"n": 0}

    def sempre_falha(cfg, prefixo, execucao):
        tentativas["n"] += 1
        return {"message": "", "erro": "HTTP 500"}

    monkeypatch.setattr(condicoes, "executar_a", sempre_falha)
    resumo = executor.executar(
        CFG, _prefixos()[:1], tmp_path, condicoes_alvo=("A",), execucoes=1, reexecucoes=2
    )
    assert tentativas["n"] == 3
    assert resumo["falhas_tecnicas"] == 1
    assert list(ler_ndjson(tmp_path / executor.ARQUIVO_TURNOS))[0]["falha_tecnica"] is True


def _prepara_turnos(tmp_path, monkeypatch):
    monkeypatch.setattr(
        condicoes,
        "executar_a",
        lambda cfg, prefixo, execucao: {"message": "O que muda a cada volta?", "erro": ""},
    )
    executor.executar(CFG, _prefixos(), tmp_path, condicoes_alvo=("A",), execucoes=1)


def test_julgamento_cobre_turnos_gerados_e_de_referencia(tmp_path, monkeypatch):
    _prepara_turnos(tmp_path, monkeypatch)
    vistos = []

    def falso_juiz(cfg, item, contexto, turno):
        vistos.append(turno)
        return {"diretividade": 1, "fidelidade": 3, "falhas": {}, "ancorado": "sim", "erro": ""}

    monkeypatch.setattr(juiz, "julgar", falso_juiz)
    resumo = julgamento.julgar_execucao(CFG, tmp_path, [item_minimo()])
    juizos = list(ler_ndjson(tmp_path / julgamento.ARQUIVO_JUIZOS))
    unidades = {j["unidade"] for j in juizos}
    assert unidades == {"gerado", "referencia"}
    assert resumo["erros"] == 0
    assert len(juizos) == len(vistos) == 3 + 3

    # segunda passagem não repete nada
    resumo2 = julgamento.julgar_execucao(CFG, tmp_path, [item_minimo()])
    assert resumo2["planejados"] == 0


def test_trocar_de_juiz_rejulga_em_vez_de_misturar(tmp_path, monkeypatch):
    _prepara_turnos(tmp_path, monkeypatch)
    modelos = []

    def falso_juiz(cfg, item, contexto, turno):
        modelos.append(cfg.juiz_modelo)
        return {
            "diretividade": 1,
            "fidelidade": 3,
            "falhas": {},
            "ancorado": "sim",
            "juiz_modelo": cfg.juiz_modelo,
            "erro": "",
        }

    monkeypatch.setattr(juiz, "julgar", falso_juiz)
    barato = Config(**{**CFG.__dict__, "juiz_modelo": "gpt-4o"})
    protocolo = Config(**{**CFG.__dict__, "juiz_modelo": "gemini-3.1-pro-preview"})

    primeira = julgamento.julgar_execucao(barato, tmp_path, [item_minimo()])
    segunda = julgamento.julgar_execucao(protocolo, tmp_path, [item_minimo()])
    terceira = julgamento.julgar_execucao(protocolo, tmp_path, [item_minimo()])

    assert segunda["planejados"] == primeira["planejados"]  # nada reaproveitado do outro juiz
    assert segunda["reaproveitados"] == 0
    assert terceira["planejados"] == 0  # mesmo juiz: retoma normalmente
    assert set(modelos) == {"gpt-4o", "gemini-3.1-pro-preview"}


def test_analise_usa_um_juiz_so_e_declara_qual(tmp_path, monkeypatch):
    from avaliacao import analise
    from avaliacao.registro import escrever_json

    _prepara_turnos(tmp_path, monkeypatch)
    escrever_json(
        tmp_path / "manifesto.json",
        {"juiz_modelo": "gpt-4o", "modelo_base": "gpt-4o-mini", "juiz_transporte": "litellm"},
    )
    monkeypatch.setattr(
        juiz,
        "julgar",
        lambda cfg, item, contexto, turno: {
            "diretividade": 1,
            "fidelidade": 3,
            "movimento_estudante": "ESTAGNACAO",
            "ancorado": "sim",
            "falhas": {},
            "juiz_modelo": cfg.juiz_modelo,
            "erro": "",
        },
    )
    julgamento.julgar_execucao(Config(**{**CFG.__dict__, "juiz_modelo": "gpt-4o"}), tmp_path, [item_minimo()])
    julgamento.julgar_execucao(
        Config(**{**CFG.__dict__, "juiz_modelo": "gemini-3.1-pro-preview"}), tmp_path, [item_minimo()]
    )

    resumo = analise.analisar(tmp_path, [item_minimo()])
    assert resumo["juiz"]["modelo"] == "gpt-4o"
    assert resumo["juiz"]["familia_distinta"] is False
    assert resumo["juiz"]["outros_no_arquivo"] == ["gemini-3.1-pro-preview"]
    texto = (tmp_path / "analise" / "resumo.md").read_text(encoding="utf-8")
    assert "Não reportável" in texto

    outro = analise.analisar(tmp_path, [item_minimo()], juiz_modelo="gemini-3.1-pro-preview")
    assert outro["juiz"]["familia_distinta"] is True


def _juiz_com_niveis_variados(monkeypatch):
    """Juiz que percorre os três níveis: sem variação, o κ da diretividade seria indefinido."""
    contador = {"n": 0}

    def falso_juiz(cfg, item, contexto, turno):
        contador["n"] += 1
        return {
            "diretividade": contador["n"] % 3,
            "fidelidade": 3,
            "movimento_estudante": "ESTAGNACAO",
            "ancorado": "sim",
            "falhas": {"irrelevante": False, "repetida": False, "excessivamente_direta": False, "prematura": False},
            "erro": "",
        }

    monkeypatch.setattr(juiz, "julgar", falso_juiz)


def test_planilha_humana_e_cega_e_kappa_fecha_o_ciclo(tmp_path, monkeypatch):
    _prepara_turnos(tmp_path, monkeypatch)
    _juiz_com_niveis_variados(monkeypatch)
    julgamento.julgar_execucao(CFG, tmp_path, [item_minimo()])

    resumo = validacao_humana.gerar_amostra(
        tmp_path, [item_minimo()], tamanho=3, tamanho_referencia=2
    )
    destino = tmp_path / "validacao_humana"
    assert resumo["gerados"] == 3
    assert resumo["referencia"] == 2
    assert resumo["amostra"] == 5
    cabecalho = (destino / validacao_humana.ARQUIVO_CODIFICACAO).read_text(encoding="utf-8").splitlines()[0]
    assert "condicao" not in cabecalho and "diretividade" in cabecalho
    # Turnos de referência e gerados partilham a mesma folha e as mesmas colunas: nada na
    # planilha diz ao codificador de onde veio o turno.
    assert "unidade" not in cabecalho and "referencia" not in cabecalho

    mapa = json.loads((destino / "mapa_amostra.json").read_text(encoding="utf-8"))
    do_juiz = {j["chave"]: j["diretividade"] for j in ler_ndjson(tmp_path / julgamento.ARQUIVO_JUIZOS)}

    def _planilha(ids_e_valores):
        linhas = ["id_cego,diretividade,fidelidade,movimento_estudante,ancorado,irrelevante,repetida,excessivamente_direta,prematura"]
        linhas += [
            f"{identificador},{nivel},3,ESTAGNACAO,sim,nao,nao,nao,nao"
            for identificador, nivel in ids_e_valores
        ]
        return "\n".join(linhas) + "\n"

    (destino / validacao_humana.ARQUIVO_CODIFICACAO).write_text(
        _planilha([(i, do_juiz[mapa[i]]) for i in sorted(mapa)]), encoding="utf-8"
    )

    # O mapa (que o codificador não vê) é o único sítio onde a origem aparece.
    chaves = set(mapa.values())
    assert sum(1 for c in chaves if c.endswith("::referencia")) == 2

    kappa = validacao_humana.calcular_kappa(tmp_path, [item_minimo()])
    assert kappa["n_amostra"] == 5
    assert kappa["humano_juiz"]["diretividade"] == 1.0
    assert kappa["abaixo_da_aceitacao"] == []
    # As variáveis constantes na subamostra não têm κ: ficam pendentes em vez de passar caladas.
    assert "humano_juiz:fidelidade" in kappa["indefinidos"]
    assert kappa["validadas"] is False


def test_recodificacao_tem_identificadores_proprios_e_fica_pendente_ate_ser_preenchida(
    tmp_path, monkeypatch
):
    """O terço diferido não pode reusar o `id_cego` da primeira rodada.

    Se reusasse, o codificador procuraria o que tinha respondido e o κ passaria a medir memória,
    não estabilidade. E enquanto a segunda rodada não existe, o κ intra-avaliador está pendente —
    não validado, que é diferente de reprovado.
    """
    _prepara_turnos(tmp_path, monkeypatch)
    _juiz_com_niveis_variados(monkeypatch)
    julgamento.julgar_execucao(CFG, tmp_path, [item_minimo()])

    resumo = validacao_humana.gerar_amostra(
        tmp_path, [item_minimo()], tamanho=3, tamanho_referencia=2
    )
    destino = tmp_path / "validacao_humana"
    assert resumo["recodificacao"] == 5 // validacao_humana.FRACAO_RECODIFICACAO

    mapa = json.loads((destino / "mapa_amostra.json").read_text(encoding="utf-8"))
    mapa_recodificacao = json.loads(
        (destino / "mapa_recodificacao.json").read_text(encoding="utf-8")
    )
    # Identificadores próprios, e o vínculo só existe no mapa que o codificador não abre.
    assert set(mapa_recodificacao) & set(mapa) == set()
    assert set(mapa_recodificacao.values()) <= set(mapa)

    procedimento = json.loads((destino / "procedimento.json").read_text(encoding="utf-8"))
    assert procedimento["ordem_primeira_rodada"] == sorted(mapa)
    assert procedimento["intervalo_minimo_semanas"] == validacao_humana.INTERVALO_MINIMO_SEMANAS

    cabecalho = "id_cego,diretividade,fidelidade,movimento_estudante,ancorado,irrelevante,repetida,excessivamente_direta,prematura"
    (destino / validacao_humana.ARQUIVO_CODIFICACAO).write_text(
        cabecalho + "\n" + "\n".join(f"{i},1,3,ESTAGNACAO,sim,nao,nao,nao,nao" for i in sorted(mapa)) + "\n",
        encoding="utf-8",
    )

    pendente = validacao_humana.calcular_kappa(tmp_path, [item_minimo()])
    assert pendente["recodificacao_pendente"] is True
    assert pendente["n_recodificacao"] == 0
    assert pendente["intra_avaliador"]["diretividade"] is None
    assert "intra_avaliador:diretividade" in pendente["indefinidos"]
    assert pendente["validadas"] is False

    # Preenchida a segunda rodada com a mesma classificação, o κ intra-avaliador deixa de ser
    # pendência e passa a medida.
    (destino / validacao_humana.ARQUIVO_RECODIFICACAO).write_text(
        cabecalho
        + "\n"
        + "\n".join(f"{i},1,3,ESTAGNACAO,sim,nao,nao,nao,nao" for i in sorted(mapa_recodificacao))
        + "\n",
        encoding="utf-8",
    )
    medido = validacao_humana.calcular_kappa(tmp_path, [item_minimo()])
    assert medido["recodificacao_pendente"] is False
    assert medido["n_recodificacao"] == len(mapa_recodificacao)
    assert medido["divergencias"] == 0


# --------------------------------------------------------------- condições B e C pelo serviço


def _resposta(corpo: dict, status: int = 200) -> http.Resposta:
    return http.Resposta(status, json.dumps(corpo, ensure_ascii=False), 42)


def _prefixo_pressao():
    return next(p for p in expandir_prefixos(item_minimo()) if p.tipo == "pressao")


def test_b_e_c_chamam_a_rota_de_chamada_unica(monkeypatch):
    """A condição C deixou de ser montada pelo harness: sai do mesmo serviço que A e B."""
    chamadas = []

    def falsa_post(url, payload, *, headers=None, timeout=120.0):
        chamadas.append((url, payload))
        return _resposta(
            {
                "message": "E onde x foi declarado?",
                "actions": [],
                "tutorMeta": {
                    "model": "gpt-4o-mini",
                    "promptVariant": payload["promptVariant"],
                    "promptSha256": "abc",
                    "contextSha256": "def",
                    "usage": {"promptTokens": 10, "completionTokens": 5, "totalTokens": 15},
                    "finishReason": "stop",
                    "latencyMs": 7,
                },
            }
        )

    monkeypatch.setattr(http, "post_json", falsa_post)
    prefixo = _prefixo_pressao()

    registro_b = condicoes.executar_b(CFG, prefixo, 1)
    registro_c = condicoes.executar_c(CFG, prefixo, 1)

    assert [url for url, _ in chamadas] == ["http://teste/api/help/single"] * 2
    assert chamadas[0][1]["promptVariant"] == "socratic"
    assert chamadas[1][1]["promptVariant"] == "neutral"
    # Mesmo corpo nas duas condições, à parte a variante e o sessionId.
    corpo_b = {k: v for k, v in chamadas[0][1].items() if k not in ("promptVariant", "sessionId")}
    corpo_c = {k: v for k, v in chamadas[1][1].items() if k not in ("promptVariant", "sessionId")}
    assert corpo_b == corpo_c
    assert registro_b["condicao"] == "B" and registro_c["condicao"] == "C"
    assert registro_b["finish_reason"] == "stop"
    assert registro_b["tokens"]["totalTokens"] == 15
    assert registro_b["prompt_variant"] == "socratic"


def test_harness_nao_monta_prompt_de_condicao_c():
    """O molde e a instrução de C vivem no serviço; sobreviver a um `MOLDE_C` seria ter duas."""
    assert not hasattr(condicoes, "MOLDE_C")
    assert not hasattr(condicoes, "instrucao_c")
    assert not hasattr(condicoes, "conteudo_c")
    assert not (Path(condicoes.__file__).parent / "prompts" / "condicao_c.txt").exists()


def test_b_corre_so_nos_prefixos_de_pressao():
    prefixos = expandir_prefixos(item_minimo())
    tarefas = executor.montar_tarefas(
        prefixos, condicoes_alvo=("A", "B", "C"), execucoes=1, semente=1
    )
    por_condicao = {"A": set(), "B": set(), "C": set()}
    for prefixo, condicao, _ in tarefas:
        por_condicao[condicao].add(prefixo.tipo)
    assert por_condicao["B"] == {"pressao"}
    assert por_condicao["A"] == por_condicao["C"] == {p.tipo for p in prefixos}


def test_resumo_conta_turnos_truncados(tmp_path, monkeypatch):
    def falsa(cfg, prefixo, execucao):
        return {"message": "cortado ao meio porque", "erro": "", "finish_reason": "length"}

    monkeypatch.setattr(condicoes, "executar_a", falsa)
    resumo = executor.executar(CFG, _prefixos(), tmp_path, condicoes_alvo=("A",), execucoes=1)
    n = len(_prefixos())
    assert resumo["chamadas_por_condicao"] == {"A": n}
    assert resumo["truncadas_por_condicao"] == {"A": n}


def test_hashes_do_servico_le_os_quatro_hashes(monkeypatch):
    monkeypatch.setattr(
        http,
        "get_json",
        lambda url, **_: _resposta(
            {
                "prompts": {
                    "socratic": {"text": "…", "sha256": "aa"},
                    "neutral": {"text": "…", "sha256": "bb"},
                },
                "context": {"text": "…", "sha256": "cc"},
                "problem": {"text": "…", "sha256": "dd"},
            }
        ),
    )
    # Serviço sem o bloco ``config``: os campos de política ficam declarados como desconhecidos,
    # em vez de receberem um valor plausível lido do ambiente errado (o do harness).
    assert condicoes.hashes_do_servico(CFG) == {
        "prompt_socratic": "aa",
        "prompt_neutral": "bb",
        "contexto": "cc",
        "enunciado": "dd",
        "classificador_de_movimento": "(não reportado)",
        "evaluation_mode": "(não reportado)",
        "modelo_do_servico": "(não reportado)",
    }


def test_hashes_do_servico_le_a_config_de_politica(monkeypatch):
    """O manifesto tem de distinguir os dois braços da corrida A/A, que só diferem nisto."""
    monkeypatch.setattr(
        http,
        "get_json",
        lambda url, **_: _resposta(
            {
                "prompts": {
                    "socratic": {"text": "…", "sha256": "aa"},
                    "neutral": {"text": "…", "sha256": "bb"},
                },
                "context": {"text": "…", "sha256": "cc"},
                "problem": {"text": "…", "sha256": "dd"},
                "config": {
                    "evaluationMode": True,
                    "classificadorDeMovimento": "modelo",
                    "model": "gpt-4o-mini",
                },
            }
        ),
    )
    lido = condicoes.hashes_do_servico(CFG)
    assert lido["classificador_de_movimento"] == "modelo"
    assert lido["evaluation_mode"] == "True"
    assert lido["modelo_do_servico"] == "gpt-4o-mini"


def test_hashes_do_servico_aborta_com_servico_fora(monkeypatch):
    monkeypatch.setattr(http, "get_json", lambda url, **_: http.Resposta(0, "", 5, erro="recusada"))
    with pytest.raises(SystemExit):
        condicoes.hashes_do_servico(CFG)


def test_exportacao_emparelha_gerado_com_as_referencias_da_posicao(tmp_path, monkeypatch):
    """As métricas de sobreposição rodam no código do benchmark original; aqui só a ponte."""
    from avaliacao import exportacao

    _prepara_turnos(tmp_path, monkeypatch)
    resumo = exportacao.exportar_sobreposicao(tmp_path, [item_minimo()])

    linhas = list(ler_ndjson(tmp_path / exportacao.ARQUIVO_SOBREPOSICAO))
    assert resumo["pares"] == len(linhas) > 0
    assert resumo["por_condicao"] == {"A": len(linhas)}
    for linha in linhas:
        assert linha["hipotese"].strip()
        assert linha["referencias"] and all(r.strip() for r in linha["referencias"])
        assert linha["k"] >= 1


def test_exportacao_ignora_prefixos_de_pressao(tmp_path, monkeypatch):
    """Prefixo de pressão é artificial e não tem turno humano: não há contra o que medir."""
    from avaliacao import exportacao

    prefixos = {p.id: p for p in expandir_prefixos(item_minimo())}
    pressao = next(p for p in prefixos.values() if p.tipo == "pressao")
    executor.anexar(
        tmp_path / executor.ARQUIVO_TURNOS,
        {
            "chave": executor.chave(pressao.id, "B", 1),
            "prefixo_id": pressao.id,
            "item_id": pressao.item_id,
            "condicao": "B",
            "execucao": 1,
            "message": "e o que te faz pensar isso?",
            "falha_tecnica": False,
        },
    )
    linhas = exportacao.linhas_de_sobreposicao(tmp_path, [item_minimo()])
    assert all(linha["prefixo_id"] != pressao.id for linha in linhas)
