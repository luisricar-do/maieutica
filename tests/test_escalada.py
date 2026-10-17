"""
Escada de concretude decidida em código (``POLITICA_DE_ESCALADA``).

Prende-se a regra de ritmo (focado até o terceiro turno bloqueado, conceitual a partir do quarto
no nível de dica 1), que o nível chega ao estrategista e ao comunicador só em depuração, que a
política ``prompt`` deixa os dois prompts como em ``1e7e5cd`` e que o alvo sai no ``tutorMeta``.
"""

import pytest

from agents.analyst import Diagnosis
from agents.config import POLITICA_ESCALADA_ENV, ConfiguracaoInvalida, politica_de_escalada, verificar_configuracao
from agents.escalada import NIVEL_CONCEITUAL, NIVEL_FOCADO, nivel_alvo, nivel_do_turno
from agents.strategist import _build_strategist_system_content
from agents.tutor import _build_system_content
from services.tutor_help import build_tutor_meta_from_actions


@pytest.mark.parametrize(
    ("streak", "hint", "esperado"),
    [
        (0, 1, NIVEL_FOCADO),
        (3, 1, NIVEL_FOCADO),
        (4, 1, NIVEL_CONCEITUAL),
        (7, 1, NIVEL_CONCEITUAL),
        (1, 2, NIVEL_FOCADO),
        (2, 2, NIVEL_CONCEITUAL),
        (0, 3, NIVEL_CONCEITUAL),
    ],
)
def test_nivel_alvo_segue_o_ritmo_do_nivel_de_dica(streak: int, hint: int, esperado: int) -> None:
    assert nivel_alvo(streak, hint) == esperado


def test_nivel_nunca_chega_a_revelacao() -> None:
    assert max(nivel_alvo(s, h) for s in range(20) for h in (1, 2, 3)) == NIVEL_CONCEITUAL


@pytest.mark.parametrize(("bruto", "esperado"), [(None, "programatica"), ("", "programatica"), ("PROMPT", "prompt")])
def test_politica_padrao_e_programatica(monkeypatch: pytest.MonkeyPatch, bruto: str | None, esperado: str) -> None:
    if bruto is None:
        monkeypatch.delenv(POLITICA_ESCALADA_ENV, raising=False)
    else:
        monkeypatch.setenv(POLITICA_ESCALADA_ENV, bruto)
    assert politica_de_escalada() == esperado


def test_politica_invalida_falha_no_arranque(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(POLITICA_ESCALADA_ENV, "programática ou prompt")
    with pytest.raises(ConfiguracaoInvalida):
        verificar_configuracao()


def test_sem_nivel_fora_de_depuracao_ou_com_politica_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(POLITICA_ESCALADA_ENV, raising=False)
    assert nivel_do_turno("DEBUG", 5) == NIVEL_CONCEITUAL
    assert nivel_do_turno("CASUAL", 5) is None
    assert nivel_do_turno("THEORY", 5) is None
    monkeypatch.setenv(POLITICA_ESCALADA_ENV, "prompt")
    assert nivel_do_turno("DEBUG", 5) is None


def _diagnostico() -> Diagnosis:
    return Diagnosis(
        errorType="logic",
        errorLine=4,
        affectedVariable="i",
        errorDescription="laço não termina",
        hintAngle="condição de parada",
        severity="high",
    )


def test_estrategista_recebe_o_nivel_e_sem_ele_fica_igual() -> None:
    base = _build_strategist_system_content(_diagnostico(), "programa {}", 0, stagnation_streak=4)
    com_nivel = _build_strategist_system_content(_diagnostico(), "programa {}", 0, stagnation_streak=4, nivel_alvo=2)
    assert "<directive_level>" not in base
    assert com_nivel.startswith(base)
    assert "SYSTEM-COMPUTED DIRECTIVE LEVEL FOR THIS TURN: 2 (conceptual)" in com_nivel


def test_comunicador_recebe_o_nivel_so_em_depuracao() -> None:
    debug = _build_system_content("plano", "DEBUG", [], nivel_alvo=1)
    sem = _build_system_content("plano", "DEBUG", [])
    casual = _build_system_content("plano", "CASUAL", [], nivel_alvo=1)
    assert "Concreteness level of this message: 1 (focused)" in debug
    assert debug.startswith(sem)
    assert "<directive_level>" not in casual


def test_meta_registra_politica_e_alvo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(POLITICA_ESCALADA_ENV, raising=False)
    meta = build_tutor_meta_from_actions([], intent="DEBUG", stagnation_streak=4, hint_level=1)
    assert meta["politicaDeEscalada"] == "programatica"
    assert meta["nivelAlvo"] == NIVEL_CONCEITUAL
    monkeypatch.setenv(POLITICA_ESCALADA_ENV, "prompt")
    meta = build_tutor_meta_from_actions([], intent="DEBUG", stagnation_streak=4, hint_level=1)
    assert meta["politicaDeEscalada"] == "prompt"
    assert "nivelAlvo" not in meta
