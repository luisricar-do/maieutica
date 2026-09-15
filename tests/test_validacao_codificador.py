"""A ferramenta de codificação não pode corromper o instrumento de confiabilidade.

O teste que manda é :func:`test_gravar_sem_editar_preserva_os_bytes`: abrir e gravar sem editar
devolve a planilha byte a byte igual. Se falhar, o escritor está a reescrever o arquivo e a
ferramenta não serve — é exatamente o que ela existe para impedir.
"""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import pytest

from avaliacao.codificador import (
    ARQUIVO_DA_RODADA,
    ARQUIVO_PROCEDIMENTO,
    CAMPOS_CODIFICAVEIS,
    CAMPOS_CONTEXTO,
    DIRETORIO_PADRAO,
    DOMINIOS,
    Planilha,
    Servico,
    ordem_da_rodada,
    validar,
)

#: Caminhos que de-cegariam o codificador. ``mapa_amostra.json`` cifra a condição no valor
#: (``…|B|2``); os demais trazem o veredito do juiz e a anotação do banco.
CAMINHOS_PROIBIDOS = ("juizos.jsonl", "turnos.jsonl", "avaliacao/banco", "mapa_amostra")

RODADAS = tuple(ARQUIVO_DA_RODADA)


def _copia(tmp_path: Path) -> Path:
    """Uma cópia completa do diretório real da validação humana."""
    destino = tmp_path / "validacao_humana"
    shutil.copytree(DIRETORIO_PADRAO, destino)
    return destino


def _planilha(diretorio: Path, rodada: str) -> Planilha:
    return Planilha(
        diretorio / ARQUIVO_DA_RODADA[rodada], ordem_da_rodada(diretorio, rodada)
    )


def _codificacao_valida() -> dict[str, str]:
    return {campo: dominio[0] for campo, dominio in DOMINIOS.items()} | {"notas": ""}


pytestmark = pytest.mark.skipif(
    not DIRETORIO_PADRAO.is_dir(), reason="planilhas da validação humana ausentes"
)


@pytest.mark.parametrize("rodada", RODADAS)
def test_gravar_sem_editar_preserva_os_bytes(tmp_path: Path, rodada: str) -> None:
    """Abrir e gravar sem editar: o arquivo sai igual, byte a byte."""
    diretorio = _copia(tmp_path)
    caminho = diretorio / ARQUIVO_DA_RODADA[rodada]
    original = caminho.read_bytes()

    _planilha(diretorio, rodada).gravar()

    assert caminho.read_bytes() == original


@pytest.mark.parametrize("rodada", RODADAS)
def test_editar_e_desfazer_volta_aos_bytes_originais(
    tmp_path: Path, rodada: str
) -> None:
    """Um ciclo real de edição não deixa resíduo de formatação quando revertido."""
    diretorio = _copia(tmp_path)
    caminho = diretorio / ARQUIVO_DA_RODADA[rodada]
    original = caminho.read_bytes()

    planilha = _planilha(diretorio, rodada)
    planilha.aplicar(planilha.ordem[3], _codificacao_valida())
    planilha.gravar()
    assert caminho.read_bytes() != original

    planilha.aplicar(planilha.ordem[3], dict.fromkeys(CAMPOS_CODIFICAVEIS, ""))
    planilha.gravar()
    assert caminho.read_bytes() == original


def test_gravacao_muda_so_o_registro_alvo(tmp_path: Path) -> None:
    diretorio = _copia(tmp_path)
    caminho = diretorio / ARQUIVO_DA_RODADA["primeira"]
    antes = list(csv.reader(caminho.open(encoding="utf-8", newline="")))

    planilha = _planilha(diretorio, "primeira")
    alvo = planilha.ordem[7]
    planilha.aplicar(
        alvo, _codificacao_valida() | {"notas": "linha um\nlinha dois, com vírgula"}
    )
    planilha.gravar()

    depois = list(csv.reader(caminho.open(encoding="utf-8", newline="")))
    assert len(antes) == len(depois)
    for posicao, (a, d) in enumerate(zip(antes[1:], depois[1:], strict=True)):
        if posicao != alvo:
            assert a == d, f"registro {posicao} mudou sem ter sido editado"
    recarregada = _planilha(diretorio, "primeira")
    assert recarregada.valor(alvo, "notas") == "linha um\nlinha dois, com vírgula"
    assert recarregada.valor(alvo, "diretividade") == DOMINIOS["diretividade"][0]


def test_contexto_com_quebras_e_acentos_sobrevive(tmp_path: Path) -> None:
    """Os campos longos são o motivo da ferramenta: têm de atravessar a gravação intactos."""
    diretorio = _copia(tmp_path)
    antes = _planilha(diretorio, "primeira")
    guardados = {
        campo: [antes.valor(p, campo) for p in antes.ordem] for campo in CAMPOS_CONTEXTO
    }
    assert any("\n" in valor for valor in guardados["conversa_ate_aqui"])

    antes.aplicar(antes.ordem[0], _codificacao_valida())
    antes.gravar()

    depois = _planilha(diretorio, "primeira")
    for campo, valores in guardados.items():
        assert [depois.valor(p, campo) for p in depois.ordem] == valores


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("diretividade", "4"),
        ("diretividade", ""),
        ("fidelidade", "0"),
        ("movimento_estudante", "progresso"),
        ("ancorado", "1"),
        ("incorreta", "sim"),
    ],
)
def test_validar_recusa_fora_do_dominio(campo: str, valor: str) -> None:
    enviados = _codificacao_valida() | {campo: valor}
    _, erros = validar(enviados)
    assert any(erro.startswith(f"{campo}:") for erro in erros)


def test_validar_aceita_o_dominio_declarado() -> None:
    for campo, dominio in DOMINIOS.items():
        for valor in dominio:
            _, erros = validar(_codificacao_valida() | {campo: valor})
            assert not erros, f"{campo}={valor} recusado"


def test_validar_normaliza_crlf_das_notas() -> None:
    valores, erros = validar(_codificacao_valida() | {"notas": "um\r\ndois\rtrês"})
    assert not erros
    assert valores["notas"] == "um\ndois\ntrês"


def test_retoma_no_primeiro_pendente(tmp_path: Path) -> None:
    diretorio = _copia(tmp_path)
    planilha = _planilha(diretorio, "primeira")
    assert planilha.primeiro_pendente() == 0

    for indice in range(5):
        planilha.aplicar(planilha.ordem[indice], _codificacao_valida())
    planilha.gravar()

    assert _planilha(diretorio, "primeira").primeiro_pendente() == 5


def test_servico_grava_avanca_e_recusa(tmp_path: Path) -> None:
    diretorio = _copia(tmp_path)
    planilha = _planilha(diretorio, "primeira")
    servico = Servico(planilha, diretorio / ARQUIVO_PROCEDIMENTO, "primeira")

    resposta, codigo = servico.gravar(0, _codificacao_valida())
    assert codigo == 200
    assert resposta["indice"] == 1
    assert resposta["codificados"] == 1

    _, codigo = servico.gravar(1, _codificacao_valida() | {"diretividade": "9"})
    assert codigo == 422
    assert _planilha(diretorio, "primeira").primeiro_pendente() == 1


def test_estado_so_serve_as_colunas_da_lista_branca(tmp_path: Path) -> None:
    diretorio = _copia(tmp_path)
    servico = Servico(
        _planilha(diretorio, "primeira"), diretorio / ARQUIVO_PROCEDIMENTO, "primeira"
    )
    estado = servico.estado(0)
    assert set(estado["registro"]) == set(CAMPOS_CONTEXTO)
    assert set(estado["codificacao"]) == set(CAMPOS_CODIFICAVEIS)
    servido = json.dumps(estado, ensure_ascii=False).casefold()
    for proibido in ("condicao", "condição", "veredito", "juiz"):
        assert proibido not in servido


def test_procedimento_recebe_as_datas_da_rodada(tmp_path: Path) -> None:
    diretorio = _copia(tmp_path)
    procedimento = diretorio / ARQUIVO_PROCEDIMENTO
    planilha = _planilha(diretorio, "recodificacao")
    servico = Servico(planilha, procedimento, "recodificacao")

    assert "rodadas" not in json.loads(procedimento.read_text(encoding="utf-8"))
    servico.gravar(0, _codificacao_valida())
    rodadas = json.loads(procedimento.read_text(encoding="utf-8"))["rodadas"]
    iniciada = rodadas["recodificacao"]["iniciada_em"]
    assert iniciada and "concluida_em" not in rodadas["recodificacao"]

    for indice in range(1, len(planilha.ordem)):
        servico.gravar(indice, _codificacao_valida())
    rodadas = json.loads(procedimento.read_text(encoding="utf-8"))["rodadas"]
    assert rodadas["recodificacao"]["concluida_em"]
    # A data de início não é reescrita por gravações posteriores.
    assert rodadas["recodificacao"]["iniciada_em"] == iniciada
    # O procedimento sorteado permanece intacto.
    original = json.loads(
        (DIRETORIO_PADRAO / ARQUIVO_PROCEDIMENTO).read_text(encoding="utf-8")
    )
    atual = json.loads(procedimento.read_text(encoding="utf-8"))
    assert {chave: atual[chave] for chave in original} == original


def test_gravacao_nao_deixa_temporarios(tmp_path: Path) -> None:
    diretorio = _copia(tmp_path)
    planilha = _planilha(diretorio, "primeira")
    planilha.aplicar(planilha.ordem[0], _codificacao_valida())
    planilha.gravar()
    assert not list(diretorio.glob("*.parcial"))
    assert not list(diretorio.glob(".*.parcial"))


def test_ordem_da_recodificacao_nao_usa_os_valores_do_mapa(tmp_path: Path) -> None:
    """A ordem vem das chaves; os valores ligam as rodadas e ficam fora da ferramenta."""
    diretorio = _copia(tmp_path)
    mapa = json.loads(
        (diretorio / "mapa_recodificacao.json").read_text(encoding="utf-8")
    )
    ordem = ordem_da_rodada(diretorio, "recodificacao")
    assert ordem == list(mapa)
    assert not set(ordem) & set(mapa.values())


def test_o_modulo_nao_menciona_caminho_que_de_cega() -> None:
    """A cegueira audita-se por leitura: nenhum caminho proibido no código da ferramenta."""
    fonte = Path("avaliacao/codificador.py").read_text(encoding="utf-8")
    codigo = "\n".join(
        linha
        for linha in fonte.splitlines()
        if not linha.lstrip().startswith(("#", "#:"))
    )
    corpo = codigo.split('"""', 2)[
        -1
    ]  # fora do docstring do módulo, que os nomeia para os proibir
    for proibido in CAMINHOS_PROIBIDOS:
        assert proibido not in corpo, f"{proibido} referenciado na ferramenta"
