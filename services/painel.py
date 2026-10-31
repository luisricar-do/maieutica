"""
Resumo de sessão para o painel do condutor da coleta — funções puras, sem I/O.

Entrada: as linhas NDJSON da telemetria (já desserializadas), tal como
``services.telemetry.serialize_batch_ndjson`` as grava: o evento da IDE (``type``,
``seq``, ``ts`` do cliente, campos próprios) mais o envelope (``installId``,
``sessionId``, ``participantId``, ``condition``, ``buildSha``…) e ``serverTs``.

Duas réguas de tempo, de propósito:

- ``startedAt`` (e ``endedAt``) das tarefas vêm do ``ts`` do **cliente**: é a mesma
  origem que o cronômetro da IDE usa (``Date.now()`` no navegador do aluno), logo o
  tempo restante que o painel calcula bate com o que o aluno vê, salvo diferença de
  relógio entre as duas máquinas.
- ``firstEventAt`` / ``lastEventAt`` vêm do ``serverTs`` quando existe: o relógio do
  aluno pode estar errado, e o que interessa ao condutor é há quanto tempo o servidor
  não ouve aquela máquina. O ``serverTs`` é o da chegada do lote (a IDE envia a cada
  ~10 s), não o do evento.
"""

from collections.abc import Iterable
from typing import Any

#: Erros do tutor vistos pela IDE (falha HTTP, falha do stream, primeiro token atrasado).
TUTOR_ERROR_TYPES = frozenset({"api_error", "sse_error", "first_token_timeout"})

#: Comandos que vão para a IDE; ``note`` só fica registada para o condutor.
IDE_COMMAND_KINDS = ("extend", "accept", "skip", "end_session")
COMMAND_KINDS = (*IDE_COMMAND_KINDS, "note")

#: Prefixo do ``sessionId`` da aba em "Só estou testando" (ver IDE).
TEST_SESSION_PREFIX = "teste"


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _as_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _event_time(event: dict[str, Any]) -> str | None:
    """Carimbo do servidor quando há; senão o do cliente."""
    return _as_str(event.get("serverTs")) or _as_str(event.get("ts"))


def dedupe_events(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Ordena por ``seq`` e remove repetidos por ``(sessionId, seq)``.

    Retentativas que reagrupam eventos produzem lotes sobrepostos; fica a primeira
    cópia (as linhas de um mesmo ``seq`` são iguais, tirando o ``serverTs``).
    """
    valid = [e for e in events if isinstance(e, dict) and _as_int(e.get("seq")) is not None]
    valid.sort(key=lambda e: e["seq"])
    seen: set[tuple[Any, int]] = set()
    out: list[dict[str, Any]] = []
    for event in valid:
        key = (event.get("sessionId"), event["seq"])
        if key in seen:
            continue
        seen.add(key)
        out.append(event)
    return out


def group_by_session(events: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Agrupa as linhas por ``sessionId`` (linhas sem ``sessionId`` são descartadas)."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        session_id = _as_str(event.get("sessionId")) if isinstance(event, dict) else None
        if session_id:
            groups.setdefault(session_id, []).append(event)
    return groups


def _new_task(event: dict[str, Any], index: int | None) -> dict[str, Any]:
    return {
        "task": index,
        "label": _as_str(event.get("taskLabel")),
        "practice": bool(event.get("practice")) or index == 0,
        "startedAt": _as_str(event.get("ts")),
        "endedAt": None,
        "outcome": None,
        "endedBy": None,
        "elapsedMs": None,
        "timeboxMs": _as_int(event.get("timeboxMs")),
        "studentTurns": None,
        "checks": 0,
        "failedChecks": 0,
        "lastCheck": None,
    }


def _last_task_with(tasks: list[dict[str, Any]], index: int | None) -> dict[str, Any] | None:
    for task in reversed(tasks):
        if task["task"] == index:
            return task
    return None


class _SessionState:
    """Acumulador do percurso de uma sessão (um evento de cada vez, por ``seq``)."""

    def __init__(self) -> None:
        self.tasks: list[dict[str, Any]] = []
        self.open_task: dict[str, Any] | None = None
        self.extra_ms = 0
        self.applied: set[str] = set()
        self.session_ended = False
        self.task_order: list[int] | None = None
        self.chat_turns = 0
        self.tutor_errors = 0
        #: Retomada (mesma matrícula numa aba nova): tarefas encerradas na sessão anterior.
        self.resumed: dict[str, Any] | None = None

    def apply(self, event: dict[str, Any]) -> None:
        kind = event.get("type")
        handler = _HANDLERS.get(kind) if isinstance(kind, str) else None
        if handler is not None:
            handler(self, event)
        elif kind in TUTOR_ERROR_TYPES:
            self.tutor_errors += 1

    def task_start(self, event: dict[str, Any]) -> None:
        index = _as_int(event.get("task"))
        if self.open_task is not None and self.open_task["task"] == index:
            # Recarregamento da aba: a IDE restaura o cronômetro original; a tarefa é a mesma.
            return
        task = _new_task(event, index)
        self.tasks.append(task)
        self.open_task = task
        self.extra_ms = 0

    def task_end(self, event: dict[str, Any]) -> None:
        index = _as_int(event.get("task"))
        if self.open_task is not None and self.open_task["task"] == index:
            task = self.open_task
        else:
            last = _last_task_with(self.tasks, index)
            if last is not None and last["endedAt"] is not None:
                return  # desfecho repetido de uma tarefa já encerrada
            if last is None:
                # ``task_start`` perdido: a tarefa existe, mas sem início conhecido.
                last = _new_task({**event, "ts": None}, index)
                self.tasks.append(last)
            task = last
        task["endedAt"] = _as_str(event.get("ts"))
        task["outcome"] = _as_str(event.get("outcome"))
        task["endedBy"] = _as_str(event.get("endedBy"))
        task["elapsedMs"] = _as_int(event.get("taskElapsedMs"))
        task["studentTurns"] = _as_int(event.get("studentTurns"))
        if task["timeboxMs"] is None:
            task["timeboxMs"] = _as_int(event.get("timeboxMs"))
        if task is self.open_task:
            self.open_task = None
            self.extra_ms = 0

    def task_check(self, event: dict[str, Any]) -> None:
        index = _as_int(event.get("task"))
        if self.open_task is not None and self.open_task["task"] == index:
            task = self.open_task
        else:
            task = _last_task_with(self.tasks, index)
        if task is None:
            return
        passed = event.get("passed") is True
        task["checks"] += 1
        if not passed:
            task["failedChecks"] += 1
        task["lastCheck"] = {
            "passed": passed,
            "casesOk": _as_int(event.get("casesOk")),
            "casesTotal": _as_int(event.get("casesTotal")),
            "compileError": event.get("compileError") is True,
            "at": _as_str(event.get("ts")),
        }

    def command_applied(self, event: dict[str, Any]) -> None:
        command_id = _as_str(event.get("commandId"))
        if command_id:
            self.applied.add(command_id)
        minutes = _as_int(event.get("minutes"))
        if event.get("kind") == "extend" and self.open_task is not None and minutes:
            self.extra_ms += minutes * 60_000

    def session_end(self, _event: dict[str, Any]) -> None:
        self.session_ended = True

    def study_assigned(self, event: dict[str, Any]) -> None:
        order = event.get("taskOrder")
        if isinstance(order, list):
            self.task_order = [i for i in order if _as_int(i) is not None]
        if event.get("resumed") is True:
            self._resume(event)

    def _resume(self, event: dict[str, Any]) -> None:
        """A IDE retoma sem ``task_start`` novo (a tarefa não recomeça): monta-a daqui."""
        raw = event.get("completed")
        values = (_as_int(v) for v in raw) if isinstance(raw, list) else ()
        completed = sorted({i for i in values if i is not None})
        running = _as_int(event.get("runningTask"))
        self.resumed = {"completed": completed, "runningTask": running}
        if running is None or self.open_task is not None or _last_task_with(self.tasks, running):
            return
        task = _new_task(
            {
                "taskLabel": event.get("runningLabel"),
                "practice": event.get("runningPractice"),
                # Início original, no relógio do aluno, como o ``ts`` de um ``task_start``.
                "ts": event.get("runningStartedAt"),
                "timeboxMs": event.get("runningTimeboxMs"),
            },
            running,
        )
        self.tasks.append(task)
        self.open_task = task
        self.extra_ms = _as_int(event.get("runningExtraMs")) or 0

    def chat_turn_user(self, _event: dict[str, Any]) -> None:
        self.chat_turns += 1


_HANDLERS = {
    "task_start": _SessionState.task_start,
    "task_end": _SessionState.task_end,
    "task_check": _SessionState.task_check,
    "conductor_command_applied": _SessionState.command_applied,
    "session_end": _SessionState.session_end,
    "study_assigned": _SessionState.study_assigned,
    "chat_turn_user": _SessionState.chat_turn_user,
}


def _latest_identity(events: list[dict[str, Any]], key: str) -> str | None:
    """Último valor não vazio do envelope (o pseudônimo chega depois do formulário)."""
    for event in reversed(events):
        value = _as_str(event.get(key))
        if value:
            return value
    return None


def _current_task(state: _SessionState) -> dict[str, Any] | None:
    task = state.open_task
    if task is None or state.session_ended:
        return None
    return {
        "task": task["task"],
        "label": task["label"],
        "practice": task["practice"],
        "startedAt": task["startedAt"],
        "timeboxMs": task["timeboxMs"],
        "extraMs": state.extra_ms,
        "checks": task["checks"],
        "failedChecks": task["failedChecks"],
    }


def _summarize_commands(
    commands: Iterable[dict[str, Any]], applied: set[str]
) -> list[dict[str, Any]]:
    out = []
    for command in commands:
        command_id = _as_str(command.get("id"))
        if not command_id or command.get("kind") == "note":
            continue
        item: dict[str, Any] = {"id": command_id, "kind": command.get("kind")}
        if command.get("minutes") is not None:
            item["minutes"] = command["minutes"]
        if command.get("text") is not None:
            item["text"] = command["text"]
        item["createdAt"] = command.get("createdAt")
        item["applied"] = command_id in applied
        out.append(item)
    out.sort(key=lambda c: c["id"])
    return out


def _summarize_notes(notes: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out = [
        {"id": n["id"], "text": n.get("text"), "createdAt": n.get("createdAt")}
        for n in notes
        if _as_str(n.get("id"))
    ]
    out.sort(key=lambda n: n["id"])
    return out


def _completed_scenarios(state: _SessionState) -> int:
    """Cenários encerrados nesta sessão e, numa retomada, os encerrados antes (0 é o treino)."""
    ended = {t["task"] for t in state.tasks if t["endedAt"] is not None and not t["practice"]}
    prior = set(state.resumed["completed"]) - {0} if state.resumed else set()
    return len(ended | prior)


def summarize_session(
    events: Iterable[dict[str, Any]],
    commands: Iterable[dict[str, Any]] = (),
    notes: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """
    Estado de uma sessão para o painel, a partir das linhas de telemetria dela.

    ``commands`` e ``notes`` são os JSON gravados em ``comandos/`` e ``notas/``; um
    comando conta como aplicado quando existe ``conductor_command_applied`` com o seu
    ``commandId``. ``extraMs`` soma os ``extend`` aplicados desde o ``task_start``
    corrente. Um ``task_start`` repetido para a tarefa aberta (recarregamento) não
    cria tarefa nova.
    """
    ordered = dedupe_events(events)
    state = _SessionState()
    for event in ordered:
        state.apply(event)

    first = ordered[0] if ordered else {}
    last = ordered[-1] if ordered else {}
    session_id = _latest_identity(ordered, "sessionId")
    times = [t for e in ordered if (t := _event_time(e))]
    return {
        "sessionId": session_id,
        "installId": _latest_identity(ordered, "installId"),
        "participantId": _latest_identity(ordered, "participantId"),
        "condition": _latest_identity(ordered, "condition"),
        "buildSha": _latest_identity(ordered, "buildSha"),
        "isTest": bool(session_id and session_id.startswith(TEST_SESSION_PREFIX)),
        "firstEventAt": _event_time(first),
        # Maior carimbo, não o do maior ``seq``: um lote retido no cliente pode chegar
        # depois de outro mais novo; o que conta é a última vez que o servidor ouviu a máquina.
        "lastEventAt": max(times) if times else None,
        "lastEventType": last.get("type"),
        "sessionEnded": state.session_ended,
        "taskOrder": state.task_order,
        "tasks": state.tasks,
        "currentTask": _current_task(state),
        "completedScenarios": _completed_scenarios(state),
        "resumed": state.resumed,
        "chatTurns": state.chat_turns,
        "tutorErrors": state.tutor_errors,
        "commands": _summarize_commands(commands, state.applied),
        "notes": _summarize_notes(notes),
    }
