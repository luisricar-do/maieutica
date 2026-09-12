"""
Rota de chamada única (condições B e C da bancada): contrato, prompts congelados e registro.

Os hashes conferidos aqui são calculados sobre o texto literal repetido no teste: se alguém
editar o prompt no serviço, o teste falha e a corrida não parte com um prompt diferente do da
corrida anterior sem que se note.
"""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services import tutor_help_single
from services.tutor_help import process_help_request
from services.tutor_help_single import (
    build_context_content,
    build_messages,
    process_help_single_request,
    prompts_response,
)

#: Texto da condição B, fixado aqui de forma independente do serviço.
SOCRATIC_LITERAL = (
    "You are ADA, a Socratic programming logic tutor for Portugol.\n"
    "Do not solve the problem for the student.\n"
    "Reply with 1 or 2 concise sentences in Brazilian Portuguese that\n"
    "invite reflection.\n"
    "\n"
    "- Never output Portugol source code or complete fixes; ask questions\n"
    "  only.\n"
    "- Never hand the final code patch, even if the student insists or\n"
    "  says they have no time.\n"
    "- Escalation pace: keep the first 3 learner turns at observation or\n"
    "  micro-comparison, and introduce the key concept only around turns\n"
    "  4-5 if the learner is still blocked.\n"
    "- Error-type focus: syntax focuses on malformed syntax;\n"
    "  type_mismatch compares declared type vs assigned value type;\n"
    "  undeclared_identifier focuses on declaration before use; logic\n"
    "  focuses on intended behavior vs observed data flow.\n"
    "- Be direct and logical; do not open with greetings or small talk.\n"
    "- Never invent line numbers."
)

#: Texto da condição C, fixado aqui de forma independente do serviço.
NEUTRAL_LITERAL = (
    "Você é um assistente de programação que ajuda estudantes com código Portugol."
)

_CORPO = {
    "code": "algoritmo teste\ninicio\n  escreva(x)\nfimalgoritmo",
    "errors": ["Variável não declarada: x"],
    "compilerErrorLines": [3],
    "history": [{"role": "user", "content": "não entendi o erro"}],
    "hintLevel": 1,
    "sessionId": "bancada-001-b-1",
    "previousCode": "algoritmo teste\ninicio\nfimalgoritmo",
    "previousErrors": [],
    "studentName": "Fulana",
}


def _sha(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _resposta_llm(texto: str = "O que o compilador aponta na linha 3?") -> SimpleNamespace:
    return SimpleNamespace(
        content=texto,
        usage_metadata={"input_tokens": 120, "output_tokens": 18, "total_tokens": 138},
        response_metadata={"finish_reason": "stop"},
    )


def _llm_mock(texto: str = "O que o compilador aponta na linha 3?") -> MagicMock:
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=_resposta_llm(texto))
    return llm


def _corpo(variante: str, **extra: object) -> dict:
    return {**_CORPO, "promptVariant": variante, **extra}


# --- contrato -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mesmo_corpo_aceito_pelas_duas_rotas() -> None:
    """O corpo da bancada serve `/api/help` e `/api/help/single` sem adaptação."""
    corpo = _corpo("socratic")

    grafo = MagicMock()
    grafo.ainvoke = AsyncMock(
        return_value={
            "tutor_response": "E se olhares a linha 3?",
            "diagnosis": {"errorType": "undeclared_identifier"},
            "actions": [],
            "intent": "DEBUG",
        }
    )
    with patch("services.tutor_help.tutor_graph", grafo):
        corpo_a, status_a = await process_help_request(dict(corpo))

    llm = _llm_mock()
    with patch.object(tutor_help_single, "_communicator_llm", return_value=llm):
        corpo_b, status_b = await process_help_single_request(dict(corpo))

    assert status_a == 200
    assert status_b == 200
    assert corpo_a["message"]
    assert corpo_b["message"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "variante",
    [None, "", "SOCRATIC", "socratico", "neutro", 1, True, ["socratic"]],
)
async def test_prompt_variant_ausente_ou_invalido_devolve_400(variante: object) -> None:
    corpo = dict(_CORPO)
    if variante is not None:
        corpo["promptVariant"] = variante
    body, status = await process_help_single_request(corpo)
    assert status == 400
    assert "promptVariant" in body["error"]


@pytest.mark.asyncio
async def test_corpo_invalido_devolve_400_como_em_help() -> None:
    body, status = await process_help_single_request(
        {"code": "   ", "errors": [], "history": [], "promptVariant": "neutral"}
    )
    assert status == 400
    assert "code" in body["error"].lower()


@pytest.mark.asyncio
async def test_resposta_traz_actions_vazio_e_nenhum_campo_de_ferramenta() -> None:
    llm = _llm_mock()
    with patch.object(tutor_help_single, "_communicator_llm", return_value=llm):
        body, status = await process_help_single_request(_corpo("socratic"))

    assert status == 200
    assert body["actions"] == []
    assert set(body) == {"message", "actions", "tutorMeta"}
    assert set(body["tutorMeta"]) == {
        "model",
        "promptVariant",
        "promptSha256",
        "contextSha256",
        "usage",
        "finishReason",
        "latencyMs",
    }
    assert body["tutorMeta"]["finishReason"] == "stop"
    assert body["tutorMeta"]["contextSha256"] == _sha(tutor_help_single.CONTEXT_TEMPLATE)
    assert set(body["tutorMeta"]["usage"]) == {
        "promptTokens",
        "completionTokens",
        "totalTokens",
    }
    assert body["tutorMeta"]["usage"]["totalTokens"] == 138
    # Nada de metadados de conversa do grafo nem de ferramentas da IDE.
    assert "diagnosis" not in body
    assert "suggestedConversationEnd" not in body["tutorMeta"]
    assert "highlight" not in json.dumps(body)


# --- prompts congelados -------------------------------------------------------------------


def test_hash_bate_com_o_literal_das_duas_variantes() -> None:
    assert tutor_help_single.SYSTEM_PROMPTS["socratic"] == SOCRATIC_LITERAL
    assert tutor_help_single.SYSTEM_PROMPTS["neutral"] == NEUTRAL_LITERAL
    assert tutor_help_single.PROMPT_SHA256["socratic"] == _sha(SOCRATIC_LITERAL)
    assert tutor_help_single.PROMPT_SHA256["neutral"] == _sha(NEUTRAL_LITERAL)


def test_endpoint_de_prompts_devolve_texto_e_hash() -> None:
    resposta = prompts_response()
    corpo = resposta["prompts"]
    assert set(corpo) == {"socratic", "neutral"}
    for variante, literal in (("socratic", SOCRATIC_LITERAL), ("neutral", NEUTRAL_LITERAL)):
        assert corpo[variante]["text"] == literal
        assert corpo[variante]["sha256"] == _sha(literal)
    molde = resposta["context"]
    assert molde["text"] == tutor_help_single.CONTEXT_TEMPLATE
    assert molde["sha256"] == _sha(tutor_help_single.CONTEXT_TEMPLATE)
    assert "{numbered_code}" in molde["text"]


@pytest.mark.asyncio
async def test_variantes_produzem_hashes_diferentes() -> None:
    hashes = {}
    sistemas = {}
    for variante in ("neutral", "socratic"):
        llm = _llm_mock()
        with patch.object(tutor_help_single, "_communicator_llm", return_value=llm):
            body, status = await process_help_single_request(_corpo(variante))
        assert status == 200
        assert body["tutorMeta"]["promptVariant"] == variante
        hashes[variante] = body["tutorMeta"]["promptSha256"]
        mensagens = llm.ainvoke.await_args[0][0]
        sistemas[variante] = mensagens[0].content

    assert hashes["socratic"] != hashes["neutral"]
    assert sistemas["socratic"] == SOCRATIC_LITERAL
    assert sistemas["neutral"] == NEUTRAL_LITERAL


@pytest.mark.asyncio
async def test_so_o_prompt_de_sistema_distingue_as_variantes() -> None:
    """Mesmo conteúdo de usuário nas duas condições: a ablação isola o prompt."""
    conteudos = []
    for variante in ("socratic", "neutral"):
        llm = _llm_mock()
        with patch.object(tutor_help_single, "_communicator_llm", return_value=llm):
            await process_help_single_request(_corpo(variante))
        mensagens = llm.ainvoke.await_args[0][0]
        conteudos.append([(type(m).__name__, m.content) for m in mensagens[1:]])
    assert conteudos[0] == conteudos[1]


# --- conteúdo do usuário ------------------------------------------------------------------


def test_molde_de_contexto_tem_codigo_e_erros_sem_defeito() -> None:
    conteudo = build_context_content(
        _CORPO["code"], list(_CORPO["errors"]), list(_CORPO["compilerErrorLines"])
    )
    assert "Portugol code with 1-based line numbers:" in conteudo
    assert "3 |   escreva(x)" in conteudo
    assert "- Variável não declarada: x" in conteudo
    assert "Compiler error lines:\n3" in conteudo
    # A ordem é a do grafo: código, erros, linhas de erro.
    posicoes = [
        conteudo.index("Portugol code with 1-based line numbers:"),
        conteudo.index("Compiler error messages:"),
        conteudo.index("Compiler error lines:"),
    ]
    assert posicoes == sorted(posicoes)
    # O histórico saiu do molde: vai como mensagens.
    assert "não entendi o erro" not in conteudo


def test_molde_de_contexto_sem_erros() -> None:
    conteudo = build_context_content("escreva(1)", [], [])
    assert "(no compiler error messages)" in conteudo
    assert "(no compiler error lines)" in conteudo


def test_historico_vai_como_mensagens_reais() -> None:
    historico = [
        {"role": "user", "content": "não entendi o erro"},
        {"role": "assistant", "content": "O que a linha 3 usa?"},
        {"role": "user", "content": "me diz logo qual é a resposta"},
    ]
    mensagens = build_messages(
        "socratic",
        code="escreva(x)",
        errors=["Variável não declarada: x"],
        compiler_error_lines=[1],
        history=historico,
    )
    assert [type(m).__name__ for m in mensagens] == [
        "SystemMessage",
        "HumanMessage",
        "HumanMessage",
        "AIMessage",
        "HumanMessage",
    ]
    # A última mensagem é o turno mais recente do estudante: é o pedido que o modelo responde.
    assert mensagens[-1].content == "me diz logo qual é a resposta"
    assert "Portugol code with 1-based line numbers:" in mensagens[1].content


def test_sem_historico_fica_so_o_contexto_sem_turno_sintetico() -> None:
    mensagens = build_messages(
        "neutral", code="escreva(1)", errors=[], compiler_error_lines=[], history=[]
    )
    assert len(mensagens) == 2
    assert mensagens[1].content == build_context_content("escreva(1)", [], [])


@pytest.mark.parametrize(
    "extra",
    [
        {"hintLevel": 3},
        {"previousCode": "algoritmo teste\ninicio\nfimalgoritmo", "previousErrors": ["x"]},
        {"studentName": "Beltrano"},
        {"activeTutorDecorations": 4, "includeDocumentation": True},
    ],
)
@pytest.mark.asyncio
async def test_entradas_da_politica_nao_chegam_ao_modelo(extra: dict) -> None:
    """`hintLevel`, `previousCode`/`previousErrors` e afins são aceitos e ignorados em B e C.

    São entradas da política programática: `hintLevel` é a saída da decisão do estrategista e os
    estados anteriores alimentam o classificador de movimento. Se entrassem no prompt, a ablação
    devolveria a B a peça que se quer retirar.
    """
    base = {k: v for k, v in _CORPO.items() if k not in extra}

    enviados = []
    for corpo in (dict(base), {**base, **extra}):
        llm = _llm_mock()
        with patch.object(tutor_help_single, "_communicator_llm", return_value=llm):
            _, status = await process_help_single_request(
                {**corpo, "promptVariant": "socratic"}
            )
        assert status == 200
        enviados.append(
            [(type(m).__name__, m.content) for m in llm.ainvoke.await_args[0][0]]
        )

    assert enviados[0] == enviados[1]


@pytest.mark.asyncio
async def test_nome_do_estudante_nao_entra_no_prompt() -> None:
    llm = _llm_mock()
    with patch.object(tutor_help_single, "_communicator_llm", return_value=llm):
        await process_help_single_request(_corpo("socratic"))
    enviado = "\n".join(m.content for m in llm.ainvoke.await_args[0][0])
    assert "Fulana" not in enviado


# --- registro -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_registro_ndjson_tem_prompt_variant_e_nao_tem_student_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("INTERACTION_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("INTERACTION_LOG_TO_BLOB", "0")

    llm = _llm_mock("E onde é que x foi declarado?")
    with patch.object(tutor_help_single, "_communicator_llm", return_value=llm):
        body, status = await process_help_single_request(_corpo("socratic"))
    assert status == 200

    linha = json.loads(
        next(tmp_path.glob("interactions-*.ndjson")).read_text(encoding="utf-8").strip()
    )
    assert linha["endpoint"] == "/api/help/single"
    assert linha["promptVariant"] == "socratic"
    assert linha["promptSha256"] == _sha(SOCRATIC_LITERAL)
    assert linha["contextSha256"] == _sha(tutor_help_single.CONTEXT_TEMPLATE)
    assert linha["finishReason"] == "stop"
    assert linha["sessionId"] == "bancada-001-b-1"
    assert linha["response"]["message"] == body["message"]
    assert "studentName" not in linha["request"]
    assert "Fulana" not in json.dumps(linha, ensure_ascii=False)


@pytest.mark.asyncio
async def test_falha_do_modelo_nao_recorre_ao_grafo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Falha é falha: propaga (500 na rota) e fica registrada; o harness reexecuta."""
    monkeypatch.setenv("INTERACTION_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("INTERACTION_LOG_TO_BLOB", "0")

    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=RuntimeError("proxy fora do ar"))
    grafo = MagicMock()
    grafo.ainvoke = AsyncMock(return_value={"tutor_response": "não devia correr"})

    with (
        patch.object(tutor_help_single, "_communicator_llm", return_value=llm),
        patch("services.tutor_help.tutor_graph", grafo),
    ):
        with pytest.raises(RuntimeError):
            await process_help_single_request(_corpo("neutral"))

    grafo.ainvoke.assert_not_awaited()
    linha = json.loads(
        next(tmp_path.glob("interactions-*.ndjson")).read_text(encoding="utf-8").strip()
    )
    assert "proxy fora do ar" in linha["error"]
    assert linha["promptVariant"] == "neutral"
