"""The apps' scheduled tasks, run by the worker (``base.worker``; VERIFACTU-F20).

A port of the old Hub's ``crates/runtime/src/scheduler.rs``. Every ``LiveAppConfig`` may declare
``scheduled_tasks``, a list of ``{"name", "operation", "cron", "catch_up"}``:

- ``operation`` is a command of the same app that runs without input; it runs as the system
  (``system_context``), never as a person;
- ``cron`` has five fields (minute, hour, day of the month, month, day of the week) and is read in
  UTC, whatever the business's zone: a programmer writes it months before anybody knows where the
  hub is (hub#731);
- ``catch_up`` is ``"collapse"``: the times missed while the worker was stopped run once, then the
  task goes on from the next time after now.

``sync`` writes the declarations to ``TaskSchedule`` when the worker starts, keeping the clock of the
tasks it already knew (``seed_module_tasks``); ``run_due`` runs, on every tick, what is due
(``process_once``): each row is claimed with ``SKIP LOCKED`` and its ``next_run`` moves in the same
transaction as the task's writes (``base.services.run_next_due_task``). A task that raises is logged
and rescheduled; the others still run. ``check_scheduled_tasks`` (``base.E001``–``E003``) refuses a
declaration the engine could not run, at ``manage.py check`` and before every command.

Every hub has its own schedule in its own database: the worker's pass over the hubs (``base.worker``) writes it once
per process and runs, under ``use_hub(hub)``, the tasks of its active apps on its own scope (review of hub#471, C1).
Since S5 there is no shared database whose tasks ran on one fixed scope; without a ``scope`` (the suite's tests
written before the tenancy) they run on ``settings.WORKER_SCOPE_SLUG``'s.
"""

import datetime as dt
import re
from dataclasses import dataclass

import pydantic
from croniter import croniter
from django.conf import settings
from django.core import checks
from django.db import close_old_connections
from live.context import Scope, system_context
from live.meta import all_live_app_configs
from live.operations import UnknownOperation
from live.operations import get as get_operation

from base import services

COLLAPSE = "collapse"
#: The keys of a declaration; ``catch_up`` may be left out (it is ``collapse``).
REQUIRED_KEYS = frozenset({"name", "operation", "cron"})
KEYS = REQUIRED_KEYS | {"catch_up"}
NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
CRON_FIELDS = 5
#: At most this many tasks a tick: each run moves its row past now, so a tick ends long before.
MAX_PER_TICK = 50


@dataclass(frozen=True)
class ScheduledTask:
    """A task an app declares: its operation runs as the system every time ``cron`` (UTC) comes."""

    app_label: str
    name: str
    operation: str
    cron: str
    catch_up: str

    @property
    def key(self) -> str:
        return f"{self.app_label}.{self.name}"


def tasks() -> list[ScheduledTask]:
    """Every task the installed apps declare (``LiveAppConfig.scheduled_tasks``)."""
    return [
        ScheduledTask(
            app_label=config.label,
            name=entry["name"],
            operation=entry["operation"],
            cron=entry["cron"],
            catch_up=entry.get("catch_up", COLLAPSE),
        )
        for config in all_live_app_configs()
        for entry in getattr(config, "scheduled_tasks", [])
    ]


def next_after(cron: str, now: dt.datetime) -> dt.datetime:
    """The first time of ``cron`` (UTC) strictly after ``now``, as an aware UTC datetime."""
    return croniter(cron, now.astimezone(dt.UTC)).get_next(dt.datetime)


def sync(now: dt.datetime, *, declared: list[ScheduledTask] | None = None) -> None:
    """Write the declared tasks (the apps', unless ``declared``) to the schedule; forget the others.

    A new task is due at its first time after ``now``; a known one keeps its clock.
    """
    declared = tasks() if declared is None else declared
    services.sync_task_schedules(
        (
            task.app_label,
            task.name,
            task.operation,
            task.cron,
            next_after(task.cron, now),
        )
        for task in declared
    )


def run_due(now: dt.datetime, *, scope: Scope | None = None, active: frozenset[str] | None = None) -> list[str]:
    """Run every task due at ``now``, one transaction each; return those that ran (``<app>.<name>``).

    ``scope``: whose they are, the system's scope they run on (a hub's own, ``host`` and its slug, in the worker's pass
    over the hubs: their live notices go on its channel); without one, ``WORKER_SCOPE_SLUG``'s (the suite's tests
    written before the tenancy). ``active``: the apps that are on there; a task of another app is not run (it moves to
    its next time). The connections are released after each task, so the worker never idles holding one.
    """
    scope = Scope("host", settings.WORKER_SCOPE_SLUG) if scope is None else scope

    def execute(name: str) -> None:
        if active is not None and name.split(".", 1)[0] not in active:
            return
        _execute(name, scope=scope)

    ran: list[str] = []
    for _ in range(MAX_PER_TICK):
        outcome = services.run_next_due_task(
            now, execute=execute, reschedule=next_after
        )
        close_old_connections()
        if outcome is None:
            break
        name, finished = outcome
        if finished:
            ran.append(name)
    return ran


def _execute(name: str, scope: Scope) -> None:
    operation = get_operation(name)
    operation(system_context(scope), operation.input())


# ── The check of the declarations ──────────────────────────────────────────────────────────────


@checks.register("base")
def check_scheduled_tasks(app_configs=None, **kwargs) -> list[checks.CheckMessage]:
    """The scheduled tasks of every app of ours (whatever ``app_configs`` ``manage.py check`` passes)."""
    return scheduled_task_errors(all_live_app_configs())


def scheduled_task_errors(configs) -> list[checks.CheckMessage]:
    errors: list[checks.CheckMessage] = []
    for config in configs:
        declared = getattr(config, "scheduled_tasks", [])
        if not isinstance(declared, list):
            errors.append(_shape(config, "scheduled_tasks", "is not a list"))
            continue
        names: set[str] = set()
        for entry in declared:
            errors.extend(_entry_errors(config, entry, names))
    return errors


def _entry_errors(config, entry, names: set[str]) -> list[checks.CheckMessage]:
    if (
        not isinstance(entry, dict)
        or not REQUIRED_KEYS <= set(entry)
        or set(entry) - KEYS
    ):
        return [
            _shape(
                config,
                repr(entry),
                "is not a dict with name, operation, cron and catch_up",
            )
        ]
    key = f"{config.label}.{entry['name']}"
    if not isinstance(entry["name"], str) or not NAME_RE.match(entry["name"]):
        return [_shape(config, key, "has a name that is not lowercase snake_case")]
    if entry["name"] in names:
        return [_shape(config, key, "is declared twice")]
    names.add(entry["name"])
    if entry.get("catch_up", COLLAPSE) != COLLAPSE:
        return [
            _shape(
                config,
                key,
                f"has catch_up {entry['catch_up']!r}; the only one is {COLLAPSE!r}",
            )
        ]
    errors = []
    cron = entry["cron"]
    if (
        not isinstance(cron, str)
        or len(cron.split()) != CRON_FIELDS
        or not croniter.is_valid(cron)
    ):
        errors.append(
            checks.Error(
                f"Scheduled task {key} has the cron {cron!r}, which the scheduler cannot read.",
                hint="Five fields, read in UTC: minute hour day-of-month month day-of-week (e.g. '*/5 * * * *').",
                obj=config,
                id="base.E002",
            )
        )
    problem = _operation_problem(config.label, entry["operation"])
    if problem:
        errors.append(
            checks.Error(
                f"Scheduled task {key} runs {entry['operation']!r}, {problem}.",
                hint="A scheduled task runs a command of its own app, as the system, without input.",
                obj=config,
                id="base.E003",
            )
        )
    return errors


def _operation_problem(app_label: str, name: object) -> str:
    try:
        operation = get_operation(name)
    except (UnknownOperation, TypeError):
        return "which is no operation"
    if operation.app_label != app_label:
        return "an operation of another app"
    if operation.kind != "command":
        return "which is a query, not a command"
    try:
        operation.input()
    except (pydantic.ValidationError, TypeError):
        return "whose input cannot be built without data"
    return ""


def _shape(config, what: str, problem: str) -> checks.Error:
    return checks.Error(
        f"Scheduled task {what} of {config.label} {problem}.",
        hint='Declare {"name": ..., "operation": "<app>.<entity>.<action>", "cron": "* * * * *", "catch_up": "collapse"}.',
        obj=config,
        id="base.E001",
    )
