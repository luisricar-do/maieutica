"""Regras de coleta, atribuição e lixeira (funções puras)."""

import csv
import io

import pytest

from services.coletas import (
    StateError,
    apply_coleta_action,
    apply_controle_action,
    apply_session_action,
    coleta_of_session,
    controle_for_ide,
    empty_state,
    normalize_state,
    public_coletas,
    public_controle,
    slugify,
    summary_csv,
)

T0 = "2026-10-22T13:00:00.000Z"
T1 = "2026-10-22T14:00:00.000Z"
T2 = "2026-10-22T15:00:00.000Z"


def _state_with(*coletas):
    state = empty_state()
    state["coletas"] = [
        {"id": cid, "nome": cid, "data": "2026-10-22", "criadaEm": T0,
         "abertaEm": opened, "encerradaEm": closed}
        for cid, opened, closed in coletas
    ]
    return state


def test_normalize_fills_missing_keys():
    assert normalize_state(None) == empty_state()
    state = normalize_state({"coletas": [{"id": "x"}, "lixo", {}], "descartes": {"s": {}}})
    assert [c["id"] for c in state["coletas"]] == ["x"]
    assert state["descartes"] == {"s": {}} and state["atribuicoes"] == {}


def test_create_builds_readable_unique_id():
    state = empty_state()
    first = apply_coleta_action(state, {"acao": "criar", "nome": "Turma A — Manhã", "data": "2026-10-22"}, T0)
    second = apply_coleta_action(state, {"acao": "criar", "nome": "Turma A — Manhã", "data": "2026-10-22"}, T0)
    assert first["id"] == "2026-10-22-turma-a-manha"
    assert second["id"] == "2026-10-22-turma-a-manha-2"
    assert first["abertaEm"] is None


@pytest.mark.parametrize(
    "payload",
    [
        {"acao": "criar", "nome": "", "data": "2026-10-22"},
        {"acao": "criar", "nome": "x" * 81, "data": "2026-10-22"},
        {"acao": "criar", "nome": "ok", "data": "22/10/2026"},
        {"acao": "criar", "nome": "ok", "data": "2026-02-30"},
        {"acao": "criar", "nome": "ok"},
        {"acao": "voar", "id": "x"},
        "não é objeto",
    ],
)
def test_create_validation(payload):
    state = _state_with(("x", None, None))
    with pytest.raises(StateError) as exc:
        apply_coleta_action(state, payload, T0)
    assert exc.value.status == 400


def test_open_closes_the_other_and_reopen_keeps_start():
    state = _state_with(("a", T0, None), ("b", None, None))
    apply_coleta_action(state, {"acao": "abrir", "id": "b"}, T1)
    a, b = state["coletas"]
    assert a["encerradaEm"] == T1
    assert b["abertaEm"] == T1 and b["encerradaEm"] is None

    apply_coleta_action(state, {"acao": "encerrar", "id": "b"}, T2)
    apply_coleta_action(state, {"acao": "abrir", "id": "a"}, T2)
    assert a["abertaEm"] == T0 and a["encerradaEm"] is None
    assert [c["id"] for c in public_coletas(state)][0] == "a"


def test_close_requires_open_and_unknown_is_404():
    state = _state_with(("a", None, None))
    with pytest.raises(StateError) as exc:
        apply_coleta_action(state, {"acao": "encerrar", "id": "a"}, T0)
    assert exc.value.status == 409
    with pytest.raises(StateError) as exc:
        apply_coleta_action(state, {"acao": "abrir", "id": "nao-ha"}, T0)
    assert exc.value.status == 404


def test_create_and_open_in_one_step():
    state = _state_with(("a", T0, None))
    new = apply_coleta_action(
        state, {"acao": "criar", "nome": "B", "data": "2026-10-22", "abrir": True}, T1
    )
    assert new["abertaEm"] == T1
    assert state["coletas"][0]["encerradaEm"] == T1


def test_delete_drops_assignments_to_it():
    state = _state_with(("a", T0, None), ("b", None, None))
    state["atribuicoes"] = {"s1": "a", "s2": "b", "s3": None}
    assert apply_coleta_action(state, {"acao": "excluir", "id": "a"}, T1) is None
    assert state["atribuicoes"] == {"s2": "b", "s3": None}


def test_edit_changes_name_and_date_not_id():
    state = _state_with(("a", None, None))
    apply_coleta_action(state, {"acao": "editar", "id": "a", "nome": "Novo", "data": "2026-11-01"}, T0)
    coleta = state["coletas"][0]
    assert (coleta["id"], coleta["nome"], coleta["data"]) == ("a", "Novo", "2026-11-01")


def test_membership_by_window():
    state = _state_with(("manha", T0, T1), ("tarde", T1, None), ("planejada", None, None))
    # Viva só de manhã.
    assert coleta_of_session("s", "2026-10-22T13:10:00Z", "2026-10-22T13:50:00Z", state) == "manha"
    # Começou antes da abertura, mas seguiu viva depois: entra.
    assert coleta_of_session("s", "2026-10-22T12:50:00Z", "2026-10-22T13:05:00Z", state) == "manha"
    # Atravessa as duas janelas: fica a aberta mais recentemente.
    assert coleta_of_session("s", "2026-10-22T13:50:00Z", "2026-10-22T14:10:00Z", state) == "tarde"
    # Morreu antes de qualquer abertura.
    assert coleta_of_session("s", "2026-10-22T12:00:00Z", "2026-10-22T12:30:00Z", state) is None
    assert coleta_of_session("s", None, None, state) is None


def test_manual_assignment_wins_and_none_means_no_coleta():
    state = _state_with(("manha", T0, None), ("outra", None, None))
    first, last = "2026-10-22T13:10:00Z", "2026-10-22T13:20:00Z"
    state["atribuicoes"] = {"s1": "outra", "s2": None, "s3": "apagada"}
    assert coleta_of_session("s1", first, last, state) == "outra"
    assert coleta_of_session("s2", first, last, state) is None
    assert coleta_of_session("s3", first, last, state) is None


def test_session_actions():
    state = _state_with(("a", None, None))
    apply_session_action(state, "mover", ["s1", "s2"], {"coletaId": "a"}, T0)
    apply_session_action(state, "mover", ["s2"], {"coletaId": None}, T0)
    assert state["atribuicoes"] == {"s1": "a", "s2": None}
    with pytest.raises(StateError) as exc:
        apply_session_action(state, "mover", ["s1"], {"coletaId": "nao-ha"}, T0)
    assert exc.value.status == 404

    apply_session_action(state, "descartar", ["s1"], {"motivo": "  sessão de teste  "}, T0)
    apply_session_action(state, "descartar", ["s1"], {"motivo": "outro"}, T1)
    assert state["descartes"] == {"s1": {"em": T0, "motivo": "sessão de teste"}}
    apply_session_action(state, "restaurar", ["s1", "nunca-esteve"], {}, T1)
    assert state["descartes"] == {}


def test_slugify_strips_accents_and_symbols():
    assert slugify("  Ação & Reação: 2ª turma! ") == "acao-reacao-2a-turma"


def test_summary_csv_one_row_per_task():
    sessions = [
        {"sessionId": "s1", "participantId": "P1", "chatTurns": 4, "tutorErrors": 0,
         "tasks": [{"task": 0, "practice": True, "outcome": "solved", "lastCheck": {"x": 1}},
                   {"task": 3, "practice": False, "outcome": "timeout"}]},
        {"sessionId": "s2", "participantId": None, "tasks": []},
    ]
    rows = list(csv.DictReader(io.StringIO(summary_csv("c1", sessions))))
    assert [(r["sessionId"], r["ordem"], r["task"], r["outcome"]) for r in rows] == [
        ("s1", "1", "0", "solved"),
        ("s1", "2", "3", "timeout"),
        ("s2", "", "", ""),
    ]
    assert {r["coletaId"] for r in rows} == {"c1"}


def test_summary_csv_keeps_old_columns_and_adds_starter_code_last():
    sessions = [{"sessionId": "s1", "tasks": [{"task": 2, "starterCode": False}]}]
    rows = list(csv.reader(io.StringIO(summary_csv("c1", sessions))))
    assert rows[0][:3] == ["coletaId", "sessionId", "participantId"]
    assert rows[0][-1] == "starterCode" and rows[1][-1] == "False"


# --- Controle da sessão -------------------------------------------------------------------


def test_controle_defaults_show_starter_code_and_keep_start_locked():
    state = normalize_state(None)
    assert controle_for_ide(state) == {"preCodigo": True, "inicioLiberado": False}
    # Estado gravado antes do controle existir: mesmos padrões.
    assert controle_for_ide(normalize_state({"coletas": []})) == {
        "preCodigo": True,
        "inicioLiberado": False,
    }


def test_normalize_keeps_controle_and_drops_garbage():
    raw = {"controle": {"preCodigo": False, "liberacao": {"coletaId": "a", "em": T0}}}
    assert normalize_state(raw)["controle"] == {
        "preCodigo": False,
        "liberacao": {"coletaId": "a", "em": T0},
    }
    bad = {"controle": {"preCodigo": "nao", "liberacao": {"coletaId": 3}}}
    assert normalize_state(bad)["controle"] == {"preCodigo": True, "liberacao": None}


def test_coleta_action_does_not_wipe_controle():
    state = _state_with(("a", T0, None))
    apply_controle_action(state, {"acao": "pre_codigo", "mostrar": False}, T1)
    apply_controle_action(state, {"acao": "liberar"}, T1)
    state = normalize_state(state)  # como em ``mutate_state``: gravado e relido
    apply_coleta_action(state, {"acao": "editar", "id": "a", "nome": "Turma A"}, T2)
    assert controle_for_ide(normalize_state(state)) == {"preCodigo": False, "inicioLiberado": True}


def test_release_belongs_to_the_open_coleta():
    state = _state_with(("a", T0, None), ("b", None, None))
    apply_controle_action(state, {"acao": "liberar"}, T1)
    assert public_controle(state) == {
        "preCodigo": True,
        "inicioLiberado": True,
        "liberadoEm": T1,
        "coletaAberta": "a",
    }
    # A turma seguinte começa travada: abrir outra coleta encerra «a» e a liberação não vale.
    apply_coleta_action(state, {"acao": "abrir", "id": "b"}, T2)
    assert controle_for_ide(state)["inicioLiberado"] is False
    assert public_controle(state)["liberadoEm"] is None
    apply_controle_action(state, {"acao": "liberar"}, T2)
    assert controle_for_ide(state)["inicioLiberado"] is True
    apply_controle_action(state, {"acao": "travar"}, T2)
    assert controle_for_ide(state)["inicioLiberado"] is False


def test_release_without_open_coleta_holds_until_one_opens():
    state = _state_with(("a", None, None))
    apply_controle_action(state, {"acao": "liberar"}, T1)
    assert public_controle(state)["inicioLiberado"] is True
    assert public_controle(state)["coletaAberta"] is None
    apply_coleta_action(state, {"acao": "abrir", "id": "a"}, T2)
    assert public_controle(state)["inicioLiberado"] is False


@pytest.mark.parametrize(
    "payload",
    [None, [], {}, {"acao": "reiniciar"}, {"acao": "pre_codigo"},
     {"acao": "pre_codigo", "mostrar": "false"}, {"acao": "pre_codigo", "mostrar": 0}],
)
def test_controle_action_validation(payload):
    with pytest.raises(StateError) as exc:
        apply_controle_action(empty_state(), payload, T0)
    assert exc.value.status == 400
