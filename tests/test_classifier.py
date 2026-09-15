"""Testes do nó de classificação do movimento (LLM mockado).

O que aqui se fixa é a divisão de trabalho: o estimador entra **só** no degrau do texto, e o
pedido explícito e a regra do compilador continuam determinísticos. É essa divisão que faz a
variável consumida pela política voltar a medir o que a dissertação chama de bloqueio.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.classifier import MovementEstimate, MovementLabel, run_classifier
from agents.graph import classifier_node

CODIGO = """programa {
  funcao inicio() {
    inteiro v[5]
    para (inteiro i = 0; i < 5; i++) {
      leia(v[0])
    }
  }
}"""


def _historico(falas: list[str], *, codigo: str = CODIGO) -> list[dict[str, Any]]:
    """Diálogo alternado em que o estudante nunca edita o código: o texto é quem decide."""
    history: list[dict[str, Any]] = []
    for i, fala in enumerate(falas):
        if i:
            history.append({"role": "assistant", "content": f"Pergunta {i} do tutor."})
        history.append({"role": "user", "content": fala, "code": codigo, "errors": []})
    return history


def _estado(history: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    estado: dict[str, Any] = {
        "history": history,
        "code": CODIGO,
        "errors": [],
        "previous_code": CODIGO,
        "previous_errors": [],
        "problem_statement": "Ler 5 numeros e somar os multiplos de 3.",
        "diagnosis": {
            "errorType": "logic",
            "affectedVariable": "v",
            "errorLine": 5,
            "errorDescription": "leia(v[0]) sempre grava na posicao 0; devia ser v[i].",
        },
    }
    estado.update(extra)
    return estado


def _llm(*, rotulo: MovementLabel | None = None, erro: Exception | None = None):
    """Substitui o cliente de chat; devolve ``registo`` com o payload de cada chamada."""
    registo: list[str] = []

    async def _ainvoke(mensagens):
        registo.append(str(mensagens[-1].content))
        if erro is not None:
            raise erro
        return MovementEstimate(movement=rotulo or MovementLabel.ESTAGNACAO)

    fabrica = MagicMock()
    estruturado = MagicMock()
    fabrica.return_value.with_structured_output.return_value = estruturado
    estruturado.ainvoke = AsyncMock(side_effect=_ainvoke)
    return fabrica, registo


#: Cinco hipóteses erradas seguidas, sem uma única edição de código. A regra textual lê "acho",
#: "porque" e "testei" como hipótese nova e devolve PROGRESSO nas cinco — o contador nunca sai
#: de zero e a política nunca escala. É o caso que motivou o nó.
FALAS_DE_HIPOTESE_ERRADA = [
    "oi, meu programa nao soma direito",
    "acho que o para esta errado, porque i comeca em 0",
    "testei mudar o limite do para mas continua, deve ser o i < 5",
    "entao o problema e a declaracao inteiro v[5], falta tamanho",
    "percebi que o leia precisa de mais parametros, deve ser isso",
    "acredito que o erro esta na funcao inicio, ela devia retornar algo",
]


@pytest.mark.asyncio
async def test_hipotese_errada_sem_edicao_passa_a_acumular() -> None:
    fabrica, _ = _llm(rotulo=MovementLabel.REGRESSAO)
    with patch("agents.classifier._create_classifier_llm", fabrica):
        out = await run_classifier(_estado(_historico(FALAS_DE_HIPOTESE_ERRADA)))

    assert out["student_movement"] == "REGRESSAO"
    assert out["movement_source"] == "modelo"
    assert out["stagnation_source"] == "historico"
    # Cinco turnos de bloqueio desde a abertura: acima do limiar de escalonamento (4).
    assert out["stagnation_streak"] == 5


@pytest.mark.asyncio
async def test_progresso_estimado_zera_o_contador() -> None:
    fabrica, _ = _llm(rotulo=MovementLabel.PROGRESSO)
    with patch("agents.classifier._create_classifier_llm", fabrica):
        out = await run_classifier(_estado(_historico(FALAS_DE_HIPOTESE_ERRADA)))

    assert out["student_movement"] == "PROGRESSO"
    assert out["stagnation_streak"] == 0


@pytest.mark.asyncio
async def test_pedido_explicito_nao_e_estimado() -> None:
    """A condição de H2 continua determinística: o modelo não decide o que é pedido."""
    falas = FALAS_DE_HIPOTESE_ERRADA[:3] + ["me fala qual e a linha pra mudar"]
    fabrica, registo = _llm(rotulo=MovementLabel.REGRESSAO)
    with patch("agents.classifier._create_classifier_llm", fabrica):
        out = await run_classifier(_estado(_historico(falas)))

    assert out["student_movement"] == "PEDIDO_EXPLICITO"
    assert out["movement_source"] == "texto"
    # O turno do pedido não foi ao modelo; os dois anteriores foram.
    assert all("me fala qual e a linha" not in p.split(">>> ")[-1] for p in registo)


@pytest.mark.asyncio
async def test_regra_do_compilador_prevalece_sobre_o_modelo() -> None:
    """Com edição e o compilador a decidir, o movimento é evidência objetiva, não estimativa."""
    corrigido = CODIGO.replace("v[0]", "v[i]")
    history = _historico(FALAS_DE_HIPOTESE_ERRADA[:4])
    for turno in history:
        if turno["role"] == "user":
            turno["errors"] = ["erro: simbolo nao declarado"]
    history[-1]["code"] = corrigido
    history[-1]["errors"] = []
    estado = _estado(
        history,
        code=corrigido,
        errors=[],
        previous_code=CODIGO,
        previous_errors=["erro: simbolo nao declarado"],
    )

    fabrica, registo = _llm(rotulo=MovementLabel.REGRESSAO)
    with patch("agents.classifier._create_classifier_llm", fabrica):
        out = await run_classifier(estado)

    assert out["student_movement"] == "PROGRESSO"
    assert out["movement_source"] == "codigo"
    # O erro de compilação desapareceu: o compilador decide e o contador zera, por mais que o
    # modelo tenha chamado regressão aos turnos de texto que vieram antes.
    assert out["stagnation_streak"] == 0
    assert all(">>> STUDENT: " + FALAS_DE_HIPOTESE_ERRADA[3] not in p for p in registo)


@pytest.mark.asyncio
async def test_falha_do_modelo_cai_para_a_regra_deterministica() -> None:
    fabrica, _ = _llm(erro=RuntimeError("proxy fora do ar"))
    with patch("agents.classifier._create_classifier_llm", fabrica):
        out = await run_classifier(_estado(_historico(FALAS_DE_HIPOTESE_ERRADA)))

    # Sem estimativa nenhuma, o nó não devolve campo nenhum: fica o que o serviço derivou.
    assert out == {}


@pytest.mark.asyncio
async def test_cada_turno_e_estimado_so_com_o_seu_passado() -> None:
    """Sem isto o rótulo do turno 2 dependeria do turno 5, e o contador deixaria de ser o que a
    política teria consumido naquele momento."""
    fabrica, registo = _llm(rotulo=MovementLabel.ESTAGNACAO)
    with patch("agents.classifier._create_classifier_llm", fabrica):
        await run_classifier(_estado(_historico(FALAS_DE_HIPOTESE_ERRADA)))

    assert len(registo) == 5
    for payload in registo:
        dialogo = payload.split("<dialogue>")[1]
        julgado = dialogo.split(">>> STUDENT: ")[1]
        posicao = FALAS_DE_HIPOTESE_ERRADA.index(julgado.split("\n")[0].strip())
        for futura in FALAS_DE_HIPOTESE_ERRADA[posicao + 1 :]:
            assert futura not in dialogo


@pytest.mark.asyncio
async def test_no_do_grafo_so_corre_quando_a_chave_o_pede(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """O padrão é o artefato pré-registado: a regra determinística, sem chamada ao modelo."""
    estado = _estado(_historico(FALAS_DE_HIPOTESE_ERRADA))
    fabrica, registo = _llm(rotulo=MovementLabel.REGRESSAO)

    with patch("agents.classifier._create_classifier_llm", fabrica):
        monkeypatch.delenv("CLASSIFICADOR_DE_MOVIMENTO", raising=False)
        assert await classifier_node(estado) == {}
        assert registo == []

        monkeypatch.setenv("CLASSIFICADOR_DE_MOVIMENTO", "modelo")
        out = await classifier_node(estado)

    assert out["stagnation_streak"] == 5
    assert registo
