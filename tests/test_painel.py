"""Resumo de sessão do painel do condutor (função pura, sem blob)."""

from services.painel import dedupe_events, group_by_session, summarize_session

SID = "sess-aaa111"


def _ev(seq: int, type_: str, ts: str | None = None, **fields):
    event = {
        "seq": seq,
        "type": type_,
        "ts": ts or f"2026-10-21T10:{seq:02d}:00.000Z",
        "serverTs": f"2026-10-21T10:{seq:02d}:05.000Z",
        "installId": "inst-1",
        "sessionId": SID,
        "participantId": "P0123456789",
        "condition": "piloto",
        "buildSha": "abc1234",
    }
    event.update(fields)
    return event


def _start(seq: int, task: int, **fields):
    return _ev(
        seq,
        "task_start",
        task=task,
        taskLabel=f"T{task} — Cenário",
        timeboxMs=600_000,
        practice=task == 0,
        **fields,
    )


def _end(seq: int, task: int, outcome: str = "solved", **fields):
    return _ev(
        seq,
        "task_end",
        task=task,
        taskLabel=f"T{task} — Cenário",
        timeboxMs=600_000,
        taskElapsedMs=120_000,
        outcome=outcome,
        studentTurns=3,
        **fields,
    )


def test_identity_and_times_come_from_envelope_and_server():
    summary = summarize_session([_ev(2, "code_edit"), _ev(1, "session_start")])
    assert summary["sessionId"] == SID
    assert summary["participantId"] == "P0123456789"
    assert summary["condition"] == "piloto"
    assert summary["buildSha"] == "abc1234"
    assert summary["firstEventAt"] == "2026-10-21T10:01:05.000Z"
    assert summary["lastEventAt"] == "2026-10-21T10:02:05.000Z"
    assert summary["lastEventType"] == "code_edit"
    assert summary["sessionEnded"] is False
    assert summary["currentTask"] is None
    assert summary["isTest"] is False


def test_task_in_progress_uses_client_ts_for_start():
    events = [
        _ev(1, "session_start"),
        _ev(2, "study_assigned", taskOrder=[3, 1, 2]),
        _start(3, 1, ts="2026-10-21T09:59:00.000Z"),
    ]
    summary = summarize_session(events)
    assert summary["taskOrder"] == [3, 1, 2]
    current = summary["currentTask"]
    assert current == {
        "task": 1,
        "label": "T1 — Cenário",
        "practice": False,
        "starterCode": None,
        "startedAt": "2026-10-21T09:59:00.000Z",
        "timeboxMs": 600_000,
        "extraMs": 0,
        "checks": 0,
        "failedChecks": 0,
    }
    assert summary["tasks"][0]["endedAt"] is None


def test_ended_task_and_practice_not_counted_as_scenario():
    events = [
        _start(1, 0),
        _end(2, 0),
        _start(3, 1),
        _end(4, 1, outcome="timeout", endedBy="conductor"),
        _start(5, 2),
    ]
    summary = summarize_session(events)
    assert summary["completedScenarios"] == 1
    practice, first, second = summary["tasks"]
    assert practice["practice"] is True
    assert first["outcome"] == "timeout"
    assert first["endedBy"] == "conductor"
    assert first["elapsedMs"] == 120_000
    assert first["studentTurns"] == 3
    assert first["endedAt"] == events[3]["ts"]
    assert second["endedAt"] is None
    assert summary["currentTask"]["task"] == 2


def test_reload_does_not_duplicate_task():
    events = [
        _start(1, 1, ts="2026-10-21T10:00:00.000Z"),
        _ev(2, "app_reload"),
        _start(3, 1, ts="2026-10-21T10:05:00.000Z"),
    ]
    summary = summarize_session(events)
    assert len(summary["tasks"]) == 1
    assert summary["currentTask"]["startedAt"] == "2026-10-21T10:00:00.000Z"


def test_extend_applied_counts_only_since_current_start():
    events = [
        _start(1, 1),
        _ev(2, "conductor_command_applied", commandId="c1", kind="extend", minutes=5),
        _end(3, 1),
        _start(4, 2),
        _ev(5, "conductor_command_applied", commandId="c2", kind="extend", minutes=5),
        _ev(6, "conductor_command_applied", commandId="c3", kind="extend", minutes=3),
    ]
    summary = summarize_session(events)
    assert summary["currentTask"]["task"] == 2
    assert summary["currentTask"]["extraMs"] == 8 * 60_000


def test_failed_and_passed_checks():
    events = [
        _start(1, 1),
        _ev(2, "task_check", task=1, passed=False, casesOk=1, casesTotal=3),
        _ev(3, "task_check", task=1, passed=False, compileError=True, casesOk=0, casesTotal=3),
        _ev(4, "task_check", task=1, passed=True, casesOk=3, casesTotal=3),
    ]
    summary = summarize_session(events)
    assert summary["currentTask"]["checks"] == 3
    assert summary["currentTask"]["failedChecks"] == 2
    last = summary["tasks"][0]["lastCheck"]
    assert last == {
        "passed": True,
        "casesOk": 3,
        "casesTotal": 3,
        "compileError": False,
        "at": events[3]["ts"],
    }


def test_commands_applied_vs_pending_and_notes_separate():
    events = [
        _start(1, 1),
        _ev(2, "conductor_command_applied", commandId="0001-aaaaaa", kind="extend", minutes=5),
    ]
    commands = [
        {"id": "0002-bbbbbb", "kind": "skip", "createdAt": "t2", "sessionId": SID},
        {"id": "0001-aaaaaa", "kind": "extend", "minutes": 5, "createdAt": "t1"},
    ]
    notes = [{"id": "0003-cccccc", "kind": "note", "text": "aluno saiu", "createdAt": "t3"}]
    summary = summarize_session(events, commands, notes)
    assert summary["commands"] == [
        {"id": "0001-aaaaaa", "kind": "extend", "minutes": 5, "createdAt": "t1", "applied": True},
        {"id": "0002-bbbbbb", "kind": "skip", "createdAt": "t2", "applied": False},
    ]
    assert summary["notes"] == [{"id": "0003-cccccc", "text": "aluno saiu", "createdAt": "t3"}]


def test_dedupe_by_session_and_seq_counts_once():
    turn = _ev(2, "chat_turn_user")
    retry = {**turn, "serverTs": "2026-10-21T11:00:00.000Z"}
    events = [_ev(1, "session_start"), turn, retry, _ev(3, "api_error"), _ev(3, "api_error")]
    summary = summarize_session(events)
    assert summary["chatTurns"] == 1
    assert summary["tutorErrors"] == 1
    assert len(dedupe_events(events)) == 3


def test_tutor_errors_and_session_end_clear_current_task():
    events = [
        _start(1, 1),
        _ev(2, "sse_error"),
        _ev(3, "first_token_timeout"),
        _ev(4, "api_error"),
        _ev(5, "session_end"),
    ]
    summary = summarize_session(events)
    assert summary["tutorErrors"] == 3
    assert summary["sessionEnded"] is True
    assert summary["currentTask"] is None


def test_task_end_without_start_still_listed():
    summary = summarize_session([_end(1, 4, outcome="aborted")])
    assert summary["tasks"][0]["task"] == 4
    assert summary["tasks"][0]["startedAt"] is None
    assert summary["tasks"][0]["outcome"] == "aborted"


def test_group_by_session_drops_lines_without_session():
    other = {**_ev(1, "session_start"), "sessionId": "sess-bbb"}
    groups = group_by_session([_ev(1, "session_start"), other, {"seq": 1, "type": "x"}])
    assert set(groups) == {SID, "sess-bbb"}


def test_resumed_session_counts_prior_tasks_and_rebuilds_running_one():
    # Mesma matrícula numa aba nova: o treino (0) e o cenário 3 acabaram na sessão anterior,
    # o 1 estava em curso e volta com o início original, sem ``task_start`` novo.
    events = [
        _ev(1, "session_start"),
        _ev(
            2,
            "study_assigned",
            taskOrder=[0, 3, 1, 2],
            resumed=True,
            completed=[0, 3],
            runningTask=1,
            runningStartedAt="2026-10-21T09:50:00.000Z",
            runningLabel="T1 — Cenário",
            runningTimeboxMs=600_000,
            runningPractice=False,
            runningExtraMs=300_000,
        ),
    ]
    summary = summarize_session(events)
    assert summary["resumed"] == {"completed": [0, 3], "runningTask": 1}
    assert summary["completedScenarios"] == 1
    current = summary["currentTask"]
    assert (current["task"], current["startedAt"], current["timeboxMs"], current["extraMs"]) == (
        1,
        "2026-10-21T09:50:00.000Z",
        600_000,
        300_000,
    )

    summary = summarize_session([*events, _end(3, 1)])
    assert summary["completedScenarios"] == 2 and summary["currentTask"] is None


def test_session_without_resume_has_no_prior_tasks():
    summary = summarize_session([_ev(1, "study_assigned", taskOrder=[0, 1])])
    assert summary["resumed"] is None and summary["completedScenarios"] == 0


def test_turno_automatico_da_ide_nao_conta_como_do_estudante():
    events = [
        _ev(1, "chat_turn_user", origin="proactive"),
        _ev(2, "chat_turn_user", origin="student"),
        _ev(3, "chat_turn_user"),
    ]
    assert summarize_session(events)["chatTurns"] == 2


def test_task_records_whether_starter_code_was_shown():
    summary = summarize_session(
        [_start(1, 0, starterCode=True), _end(2, 0), _start(3, 4, starterCode=False)]
    )
    assert [t["starterCode"] for t in summary["tasks"]] == [True, False]
    assert summary["currentTask"]["starterCode"] is False
    # Sessões anteriores ao controle não mandam o campo: fica desconhecido, não «com código».
    assert summarize_session([_start(1, 2)])["tasks"][0]["starterCode"] is None


def test_resumed_running_task_keeps_starter_code():
    summary = summarize_session(
        [
            _ev(
                1,
                "study_assigned",
                taskOrder=[0, 5],
                resumed=True,
                completed=[0],
                runningTask=5,
                runningStartedAt="2026-10-21T09:50:00.000Z",
                runningStarterCode=False,
            )
        ]
    )
    assert summary["currentTask"]["starterCode"] is False
