from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from agents.analyst import Diagnosis
from agents.strategist import (
    contingent_level,
    pop_declared_level,
    previous_concreteness_level,
    split_concreteness_level,
    STRATEGIST_TOOLS,
    TUTOR_TOOLS,
    run_strategist,
    suggested_doc_topics,
)


def test_strategist_tools_includes_compare_and_documentation() -> None:
    names = {t.name for t in STRATEGIST_TOOLS}
    assert "compare_lines" in names
    assert "suggest_documentation" in names
    assert "scroll_to" in names
    assert "spotlight_block" in names
    assert "draw_data_flow" in names
    assert "activate_focus_mode" in names
    assert "pause_at_iteration" in names
    assert "set_concreteness_level" in names
    assert STRATEGIST_TOOLS is TUTOR_TOOLS


def test_suggested_doc_topics_extracts_only_documentation_actions() -> None:
    actions = [
        {"type": "highlight_line", "payload": {"line": 3}},
        {"type": "suggest_documentation", "payload": {"topic": "vetores"}},
        {"type": "suggest_documentation", "payload": {"topic": " escreva "}},
        {"type": "suggest_documentation", "payload": {}},
    ]
    assert suggested_doc_topics(actions) == ["vetores", "escreva"]


def test_suggested_doc_topics_empty_when_no_documentation_action() -> None:
    assert suggested_doc_topics([{"type": "highlight_line", "payload": {}}]) == []
    assert suggested_doc_topics([]) == []


def _patch_bound_chat(mock_cls: MagicMock) -> MagicMock:
    instance = mock_cls.return_value
    bound = MagicMock()
    instance.bind_tools = MagicMock(return_value=bound)
    return bound


@pytest.mark.asyncio
async def test_run_strategist_returns_actions_and_plan() -> None:
    diagnosis: Diagnosis = {
        "errorType": "none",
        "errorLine": None,
        "affectedVariable": None,
        "errorDescription": "",
        "hintAngle": "Ângulo",
        "severity": "low",
    }
    with patch("agents.llm.ChatOpenAI") as mock_cls:
        bound = _patch_bound_chat(mock_cls)
        bound.ainvoke = AsyncMock(
            return_value=AIMessage(
                content="Compare lines 1 and 3; ask about delimiters.",
                tool_calls=[
                    {
                        "name": "compare_lines",
                        "args": {"line1": 1, "line2": 3},
                        "id": "c1",
                    }
                ],
            )
        )
        actions, plan = await run_strategist(diagnosis, [], "x")
    assert plan == "Compare lines 1 and 3; ask about delimiters."
    assert actions == [{"type": "compare_lines", "payload": {"line1": 1, "line2": 3}}]


@pytest.mark.asyncio
async def test_run_strategist_tool_only_uses_fallback_plan() -> None:
    diagnosis: Diagnosis = {
        "errorType": "none",
        "errorLine": None,
        "affectedVariable": None,
        "errorDescription": "",
        "hintAngle": "",
        "severity": "low",
    }
    with patch("agents.llm.ChatOpenAI") as mock_cls:
        bound = _patch_bound_chat(mock_cls)
        bound.ainvoke = AsyncMock(
            return_value=AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "highlight_line",
                        "args": {"line": 2, "color": "warning"},
                        "id": "c1",
                    }
                ],
            )
        )
        actions, plan = await run_strategist(diagnosis, [], "x")
    assert actions == [{"type": "highlight_line", "payload": {"line": 2, "color": "warning"}}]
    assert "Diretriz:" in plan


@pytest.mark.asyncio
async def test_run_strategist_type_mismatch_fallback_avoids_delimiter_language() -> None:
    diagnosis: Diagnosis = {
        "errorType": "type_mismatch",
        "errorLine": 4,
        "affectedVariable": "x",
        "errorDescription": "A variável x é inteira, mas recebe cadeia.",
        "hintAngle": "Compare o tipo declarado com o valor atribuído.",
        "severity": "medium",
    }
    with patch("agents.llm.ChatOpenAI") as mock_cls:
        bound = _patch_bound_chat(mock_cls)
        bound.ainvoke = AsyncMock(
            return_value=AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "highlight_line",
                        "args": {"line": 4, "color": "warning"},
                        "id": "c1",
                    }
                ],
            )
        )
        actions, plan = await run_strategist(diagnosis, [], 'inteiro x\nx = "hello"')
    assert actions == [{"type": "highlight_line", "payload": {"line": 4, "color": "warning"}}]
    assert "tipo declarado" in plan
    assert "fechamentos" not in plan
    assert "delimitadores" not in plan


@pytest.mark.asyncio
async def test_run_strategist_includes_documentation_in_system_when_provided() -> None:
    diagnosis: Diagnosis = {
        "errorType": "none",
        "errorLine": None,
        "affectedVariable": None,
        "errorDescription": "",
        "hintAngle": "Ângulo",
        "severity": "low",
    }
    captured: list = []

    async def capture_ainvoke(messages):
        captured.append(messages)
        return AIMessage(content="ok")

    with patch("agents.llm.ChatOpenAI") as mock_cls:
        bound = _patch_bound_chat(mock_cls)
        bound.ainvoke = AsyncMock(side_effect=capture_ainvoke)
        await run_strategist(
            diagnosis,
            [],
            "escreva(1)",
            documentation_context=["referência sobre vetores"],
        )
    msgs = captured[0]
    system_text = msgs[0].content
    assert "documentation_reference" in system_text
    assert "referência sobre vetores" in system_text
    assert "`type_mismatch`: focus on the assignment line" in system_text
    assert "Never mention \"aberturas\"" in system_text


@pytest.mark.asyncio
async def test_run_strategist_includes_minimal_hint_escalation_pace() -> None:
    diagnosis: Diagnosis = {
        "errorType": "logic",
        "errorLine": 5,
        "affectedVariable": None,
        "errorDescription": "Resultado incorreto.",
        "hintAngle": "Compare a intenção com o resultado observado.",
        "severity": "medium",
    }
    history = [
        {"role": "user", "content": "Não entendi."},
        {"role": "assistant", "content": "Observe a linha destacada."},
        {"role": "user", "content": "Ainda não sei."},
        {"role": "assistant", "content": "Compare os valores."},
        {"role": "user", "content": "Qual é a ideia?"},
    ]
    captured: list = []

    async def capture_ainvoke(messages):
        captured.append(messages)
        return AIMessage(content="ok")

    with patch("agents.llm.ChatOpenAI") as mock_cls:
        bound = _patch_bound_chat(mock_cls)
        bound.ainvoke = AsyncMock(side_effect=capture_ainvoke)
        await run_strategist(
            diagnosis,
            history,
            "escreva(1)",
            hint_level=1,
            stagnation_streak=2,
        )
    system_text = captured[0][0].content
    assert "hint_level 1 (`Mínimo`)" in system_text
    # O ritmo do nível mínimo depende do bloqueio persistente, não do número de turnos: é a
    # formulação acumulada de H1, e é o que distingue esta regra da que ela substituiu.
    assert "`stagnation_streak` <= 3" in system_text
    assert "streak reaches 4-5" in system_text
    assert "Blocked learner turns accumulated since the last progress: 2" in system_text
    assert "Learner debugging turns in current session: 3" in system_text


@pytest.mark.asyncio
async def test_escalonamento_depende_do_acumulado_e_nao_da_contagem_de_turnos() -> None:
    """O gatilho declarado é a estagnação acumulada; a contagem de turnos fica como contexto."""
    diagnosis: Diagnosis = {
        "errorType": "logic",
        "errorLine": 5,
        "affectedVariable": None,
        "errorDescription": "Laço não termina.",
        "hintAngle": "Observe o contador.",
        "severity": "medium",
    }
    captured: list = []

    async def capture_ainvoke(messages):
        captured.append(messages)
        return AIMessage(content="ok")

    with patch("agents.llm.ChatOpenAI") as mock_cls:
        bound = _patch_bound_chat(mock_cls)
        bound.ainvoke = AsyncMock(side_effect=capture_ainvoke)
        await run_strategist(
            diagnosis,
            [{"role": "user", "content": "Não sei."}],
            "escreva(1)",
            student_movement="ESTAGNACAO",
            stagnation_streak=4,
        )
    system_text = captured[0][0].content
    assert "`ESTAGNACAO` or `REGRESSAO` with `stagnation_streak` >= 4" in system_text
    assert "NEVER `debug_user_turns`" in system_text
    assert "resets to 0 the moment the learner progresses" in system_text
    assert "Blocked learner turns accumulated since the last progress: 4" in system_text


@pytest.mark.asyncio
async def test_run_strategist_injects_movement_and_contingency_rule() -> None:
    diagnosis: Diagnosis = {
        "errorType": "logic",
        "errorLine": 5,
        "affectedVariable": None,
        "errorDescription": "Laço não termina.",
        "hintAngle": "Compare a intenção com o resultado observado.",
        "severity": "medium",
    }
    captured: list = []

    async def capture_ainvoke(messages):
        captured.append(messages)
        return AIMessage(content="ok")

    with patch("agents.llm.ChatOpenAI") as mock_cls:
        bound = _patch_bound_chat(mock_cls)
        bound.ainvoke = AsyncMock(side_effect=capture_ainvoke)
        await run_strategist(
            diagnosis,
            [{"role": "user", "content": "Me fala logo o que está errado."}],
            "escreva(1)",
            student_movement="PEDIDO_EXPLICITO",
        )
    system_text = captured[0][0].content
    assert "Learner movement in the previous turn" in system_text
    assert "PEDIDO_EXPLICITO" in system_text
    assert "CONTINGENCY RULE" in system_text
    assert "`PROGRESSO`: keep or lower the level" in system_text


def test_split_concreteness_level_tira_a_linha_e_devolve_o_numero() -> None:
    assert split_concreteness_level("LEVEL: 2\nNomeie o conceito de tipo.") == (
        2,
        "Nomeie o conceito de tipo.",
    )
    assert split_concreteness_level("level: 1 (focused)\nAponte a linha 3.") == (
        1,
        "Aponte a linha 3.",
    )
    assert split_concreteness_level("LEVEL: 2 — nomeie o tipo") == (2, "nomeie o tipo")


def test_split_concreteness_level_rebaixa_o_nivel_3_ao_teto() -> None:
    assert split_concreteness_level("LEVEL: 3\nx")[0] == 2


def test_split_concreteness_level_sem_linha_preserva_o_plano() -> None:
    plano = "Destaque a linha 2 e pergunte sobre o tipo."
    assert split_concreteness_level(plano) == (None, plano)


def test_previous_concreteness_level_le_o_ultimo_turno_do_tutor() -> None:
    history = [
        {"role": "assistant", "content": "a", "concretenessLevel": 0},
        {"role": "user", "content": "b"},
        {"role": "assistant", "content": "c", "concretenessLevel": 1},
        {"role": "user", "content": "d"},
    ]
    assert previous_concreteness_level(history) == 1
    # Último turno do tutor sem o campo: desconhecido, não o de dois turnos atrás.
    history.append({"role": "assistant", "content": "e"})
    assert previous_concreteness_level(history) is None
    assert previous_concreteness_level([]) is None


@pytest.mark.asyncio
async def test_run_strategist_pede_a_tool_de_nivel_e_injeta_o_nivel_anterior() -> None:
    diagnosis: Diagnosis = {
        "errorType": "type_mismatch",
        "errorLine": 2,
        "affectedVariable": "x",
        "errorDescription": "inteiro recebe texto",
        "hintAngle": "tipos",
        "severity": "low",
    }
    captured: list = []

    async def capture_ainvoke(messages):
        captured.append(messages)
        return AIMessage(content="ok")

    with patch("agents.llm.ChatOpenAI") as mock_cls:
        bound = _patch_bound_chat(mock_cls)
        bound.ainvoke = AsyncMock(side_effect=capture_ainvoke)
        await run_strategist(
            diagnosis,
            [
                {"role": "assistant", "content": "Olhe a linha 2.", "concretenessLevel": 1},
                {"role": "user", "content": "não sei"},
            ],
            'inteiro x\nx = "a"',
        )
    system_text = captured[0][0].content
    assert "you MUST call `set_concreteness_level` exactly once" in system_text
    assert "previous_concreteness_level (the LEVEL you chose in your previous turn" in system_text
    assert "or `unknown`): 1" in system_text


def test_pop_declared_level_tira_a_tool_das_acoes_de_ide() -> None:
    actions = [
        {"type": "set_concreteness_level", "payload": {"level": 2}},
        {"type": "highlight_line", "payload": {"line": 3}},
    ]
    assert pop_declared_level(actions) == (2, [{"type": "highlight_line", "payload": {"line": 3}}])


def test_pop_declared_level_aceita_texto_rebaixa_o_3_e_ignora_lixo() -> None:
    assert pop_declared_level([{"type": "set_concreteness_level", "payload": {"level": "1"}}])[0] == 1
    assert pop_declared_level([{"type": "set_concreteness_level", "payload": {"level": 3}}])[0] == 2
    assert pop_declared_level([{"type": "set_concreteness_level", "payload": {"level": "alto"}}]) == (None, [])
    assert pop_declared_level([{"type": "set_concreteness_level", "payload": {"level": True}}])[0] is None
    assert pop_declared_level([{"type": "highlight_line", "payload": {}}])[0] is None


def _nivel(declared, previous, movement, streak, hint_level=1):
    return contingent_level(
        declared, previous, student_movement=movement, stagnation_streak=streak, hint_level=hint_level
    )


def test_contingent_level_sobe_um_degrau_com_bloqueio_persistente_mesmo_sem_declarar() -> None:
    assert _nivel(1, 1, "ESTAGNACAO", 4) == 2
    assert _nivel(None, 1, "ESTAGNACAO", 4) == 2
    assert _nivel(0, 0, "REGRESSAO", 5) == 1
    assert _nivel(2, 2, "ESTAGNACAO", 6) == 2


def test_contingent_level_nunca_sobe_dois_degraus_nem_passa_do_teto() -> None:
    assert _nivel(2, 0, "ESTAGNACAO", 4) == 1
    assert _nivel(3, 2, "PEDIDO_EXPLICITO", 0) == 2


def test_contingent_level_mantem_com_bloqueio_curto_no_nivel_de_dica_1() -> None:
    assert _nivel(2, 1, "ESTAGNACAO", 2) == 1
    assert _nivel(0, 1, "ESTAGNACAO", 3) == 1
    assert _nivel(2, 1, "ESTAGNACAO", 2, hint_level=2) == 2


def test_contingent_level_nao_sobe_depois_de_progresso() -> None:
    assert _nivel(2, 1, "PROGRESSO", 0) == 1
    assert _nivel(0, 2, "PROGRESSO", 0) == 0
    assert _nivel(None, 2, "PROGRESSO", 0) == 2


def test_contingent_level_sem_anterior_usa_o_declarado_dentro_do_ritmo() -> None:
    assert _nivel(2, None, "NENHUM", 0) == 1
    assert _nivel(0, None, "PROGRESSO", 0) == 0
    assert _nivel(None, None, "ESTAGNACAO", 4) == 2
    assert _nivel(None, None, "ESTAGNACAO", 1) == 1
    assert _nivel(2, None, "PEDIDO_EXPLICITO", 0) == 2
