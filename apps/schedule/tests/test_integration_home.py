"""Schedules on the Home (PLAN-HUB round 2026-10-21; FIX-SCHEDULE-SETUP-HOOKS): base's own query brings the old
module's item «Confirm your opening hours» (module.json `setup`, schedules#42), recommended, pending while the week is
still the default one migration 0002 planted, to whoever changes the hours, leading to the week. Confirming the week
or saving a day of it (even as closed) ticks it and records the event it is refreshed on; a change in hub B re-runs
B's Home only; with Schedules off the Home does not ask.

base and schedule run for real: the step comes from ScheduleConfig through base's own query, as the person.
"""

import json

import psycopg
import pytest
from django.apps import apps
from live.context import OperationContext, Scope
from live.live_registry import live_registry
from live.meta import all_live_app_configs, permissions_for_role
from live.models import OutboxEvent
from live.operations import get
from live.outbox import channel_for

from apps.schedule.models import ScheduleSettings, WeekDay
from apps.schedule.tests.conftest import A, B
from base.schemas import SetupStatusIn

STEP = "schedule.hours"
WAIT = 1.0
QUIET = 0.3


def person(
    role: str = "hub_owner", scope: Scope = A, language: str = "en", permissions: set[str] | None = None
) -> OperationContext:
    """Whoever reads the Home: the role's permissions on ``scope`` (``permissions`` replaces them), in ``language``."""
    if permissions is None:
        permissions = permissions_for_role(all_live_app_configs(), role)
    return OperationContext(scope=scope, actor="tester", permissions=permissions, language=language)


def step(ctx=None) -> dict | None:
    """Schedules' step of «Finish setting up your business» for the person of ``ctx`` (``None``: not told)."""
    items = get("base.setup.status")(ctx or person(), SetupStatusIn()).model_dump(mode="json")["items"]
    found = [item for item in items if item["app"] == "schedule"]
    assert len(found) <= 1, found
    return found[0] if found else None


def run(name: str, data: dict, ctx: OperationContext | None = None):
    op = get(name)
    return op(ctx or person("hub_manager"), op.input.model_validate(data))


def schedule_app():
    return apps.get_app_config("schedule")


@pytest.mark.django_db
def test_a_hub_with_the_default_week_has_confirm_your_opening_hours_pending_and_it_leads_to_the_week():
    # The week migration 0002 planted is there, nobody confirmed it.
    assert WeekDay.objects.count() == 7
    item = step()
    assert {name: item[name] for name in ("key", "state", "level", "required", "actionable", "route", "order", "icon")} == {
        "key": STEP,
        "state": "pending",
        "level": "recommended",
        "required": False,
        "actionable": True,
        "route": "/schedule/hours",
        "order": 101,
        "icon": "ion:time-outline",
    }
    assert (item["title"], item["description"]) == (
        "Confirm your opening hours",
        "We set up a default week for you (Monday to Friday, 09:00–18:00). If it matches your business, confirm it "
        "in one tap; if not, edit the days that differ — bookings outside your opening hours are refused.",
    )


@pytest.mark.django_db
def test_in_spanish_it_says_the_old_words():
    item = step(person(language="es"))
    assert (item["title"], item["description"]) == (
        "Confirma tu horario",
        "Hemos puesto un horario por defecto por ti (de lunes a viernes, de 09:00 a 18:00). Si coincide con el de tu "
        "negocio, confírmalo de un toque; si no, edita los días que cambien: las reservas fuera de tu horario se "
        "rechazan.",
    )


@pytest.mark.django_db
def test_confirming_the_week_ticks_it():
    run("schedule.week.confirm", {})
    assert step()["state"] == "done"


@pytest.mark.django_db
def test_saving_a_day_ticks_it_even_as_closed():
    # schedules#42: «We do not open on Mondays» is a decision about the business, not the absence of one.
    run("schedule.week.set_day", {"weekday": 0, "is_closed": True})
    assert step()["state"] == "done"


@pytest.mark.django_db
def test_the_first_day_of_the_week_a_special_day_or_a_temporary_change_do_not_confirm_the_week():
    run("schedule.settings.update", {"week_starts_on": 7})
    run("schedule.special_day.create", {"date": "2026-12-25", "name": "Christmas", "is_closed": True})
    run("schedule.override.create", {"start_date": "2026-08-01", "end_date": "2026-08-15", "reason": "Holidays"})
    assert step()["state"] == "pending"


@pytest.mark.django_db
def test_whoever_changes_the_hours_is_told_and_who_only_reads_them_is_not():
    # Recommended, never ⛔: who cannot change the hours is not told (base's rule). The employee only looks.
    assert step(person("hub_admin"))["state"] == "pending"
    assert step(person("hub_manager"))["state"] == "pending"
    assert step(person("hub_employee")) is None
    reader = permissions_for_role(all_live_app_configs(), "hub_owner") - {"schedule.change"}
    assert step(person(permissions=reader)) is None


@pytest.mark.django_db
def test_with_schedules_off_the_home_does_not_ask_to_confirm_the_hours():
    # base brings only the steps of the modules on in the scope: Schedules off (after the apps that need it), no step.
    administrator = OperationContext(scope=A, actor="ana", permissions=frozenset({"*"}))
    for app in ("online_booking", "appointment", "reservation", "schedule"):
        run("base.app.disable", {"app": app}, administrator)
    assert step() is None
    assert step(person(scope=B))["state"] == "pending"


def confirm():
    run("schedule.week.confirm", {})


def save_a_day():
    run("schedule.week.set_day", {"weekday": 1, "intervals": [{"open_time": "10:00", "close_time": "20:00"}]})


#: Each event of the step's ``refresh_on`` → the changes that record it (each leaves the step done).
CHANGES = {"schedule.week.updated": [confirm, save_a_day]}


@pytest.mark.django_db
@pytest.mark.parametrize(
    "event,change",
    [(event, change) for event, cases in CHANGES.items() for change in cases],
    ids=lambda value: getattr(value, "__name__", value),
)
def test_each_change_of_the_step_records_an_event_that_refreshes_it(event, change):
    before = step()["state"]
    seen = set(OutboxEvent.objects.values_list("id", flat=True))
    change()
    recorded = set(OutboxEvent.objects.exclude(id__in=seen).values_list("name", flat=True))
    assert (before, step()["state"]) == ("pending", "done")
    assert recorded & set(schedule_app().setup[0].refresh_on) == {event}


@pytest.mark.django_db
def test_confirming_a_confirmed_week_records_nothing_and_it_stays_done():
    # SCHEDULE-F03: confirming twice changes nothing and says nothing.
    confirm()
    seen = set(OutboxEvent.objects.values_list("id", flat=True))
    confirm()
    assert OutboxEvent.objects.exclude(id__in=seen).count() == 0
    assert ScheduleSettings.objects.get().hours_confirmed is True
    assert step()["state"] == "done"


def test_the_step_is_refreshed_on_nothing_else():
    assert set(schedule_app().setup[0].refresh_on) == set(CHANGES)


def test_base_re_runs_the_home_on_them():
    assert set(CHANGES) <= set(live_registry.subscribable["base.setup.status"])


# ── Two hubs ─────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def listen(db_dsn):
    sessions = []

    def open_session(scope):
        session = psycopg.connect(db_dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def received(session, timeout=WAIT):
    return [(note.channel, json.loads(note.payload)) for note in session.notifies(timeout=timeout)]


# Transactional: the notice leaves after a real COMMIT.
@pytest.mark.django_db(transaction=True)
def test_a_week_confirmed_in_hub_b_re_runs_the_home_of_b_and_tells_a_nothing(listen):
    on_a, on_b = listen(A), listen(B)
    run("schedule.week.confirm", {}, person("hub_manager", B))

    notes = received(on_b)
    assert {channel for channel, _ in notes} == {channel_for(B)}
    events = {event for _, payload in notes for event in payload["events"]}
    assert "base.setup.status" in live_registry.affected(events)
    assert received(on_a, timeout=QUIET) == []
