"""Tables on the Home (PLAN-HUB round 2026-10-21; FIX-TABLE-SETUP-HOOKS): base's own query brings the old module's
item «Your tables» (module.json `setup`, tables#24), recommended, pending until one table of the room is in use (not
deleted, active), to whoever adds tables, leading to the list of tables. Every change of it records an event it is
refreshed on, and a change in hub B re-runs B's Home only.

base and table run for real: the step comes from TableConfig through base's own query, as the person.
"""

import json

import psycopg
import pytest
from django.apps import apps
from live.live_registry import live_registry
from live.models import OutboxEvent
from live.operations import get
from live.outbox import channel_for

from apps.table.tests.conftest import A, B, ctx_for, make_session, make_table, make_zone, run
from base.schemas import SetupStatusIn

STEP = "table.tables"
WAIT = 1.0
QUIET = 0.3


def step(ctx) -> dict | None:
    """Tables' step of «Finish setting up your business» for the person of ``ctx`` (``None``: not told)."""
    items = get("base.setup.status")(ctx, SetupStatusIn()).model_dump(mode="json")["items"]
    found = [item for item in items if item["app"] == "table"]
    assert len(found) <= 1, found
    return found[0] if found else None


def table_app():
    return apps.get_app_config("table")


@pytest.mark.django_db
def test_a_hub_without_tables_has_your_tables_pending_and_it_leads_to_the_tables():
    item = step(ctx_for("hub_owner"))
    assert {name: item[name] for name in ("key", "state", "level", "required", "actionable", "route", "order", "icon")} == {
        "key": STEP,
        "state": "pending",
        "level": "recommended",
        "required": False,
        "actionable": True,
        "route": "/table/tables",
        "order": 100,
        "icon": "ion:grid-outline",
    }
    assert (item["title"], item["description"]) == (
        "Your tables",
        "Add the tables of your dining room: without them there is no order per table, no split and no transfer.",
    )


@pytest.mark.django_db
def test_in_spanish_it_says_the_old_words():
    item = step(ctx_for("hub_owner", language="es"))
    assert (item["title"], item["description"]) == (
        "Tus mesas",
        "Añade las mesas de tu sala: sin ellas no hay comanda por mesa, ni dividir ni transferir.",
    )


@pytest.mark.django_db
def test_a_zone_alone_is_not_enough_its_first_table_ticks_it():
    zone = make_zone()
    assert step(ctx_for())["state"] == "pending"
    make_table("1", zone=zone)
    assert step(ctx_for())["state"] == "done"


@pytest.mark.django_db
def test_a_table_switched_off_or_deleted_is_not_in_use():
    # tables#24: a deleted table is gone and one switched off cannot be sat at.
    zone = make_zone()
    make_table("1", zone=zone, is_active=False)
    make_table("2", zone=zone, is_deleted=True)
    assert step(ctx_for())["state"] == "pending"


@pytest.mark.django_db
def test_a_full_or_blocked_room_is_still_set_up():
    # tables#24: occupancy is not set-up; reading the status would put the step back to pending in mid-service.
    zone = make_zone()
    make_session(make_table("1", zone=zone))
    make_table("2", zone=zone, blocked=True)
    assert step(ctx_for())["state"] == "done"


@pytest.mark.django_db
def test_the_manager_who_adds_tables_is_told_and_the_waiter_is_not():
    # Recommended, never ⛔: who cannot add a table is not told (base's rule; hub#435 is for the wall only).
    assert step(ctx_for("hub_manager"))["state"] == "pending"
    assert step(ctx_for("hub_employee")) is None


def add_one(zone, table):
    run("table.table.create", {"zone_id": str(zone.id), "number": "9"})


def add_many(zone, table):
    run("table.table.bulk_create", {"zone_id": str(zone.id), "count": 2, "start_number": 20})


def switch_off(zone, table):
    run("table.table.update", {"id": str(table.id), "is_active": False})


def delete(zone, table):
    run("table.table.delete", {"id": str(table.id)})


#: Each event of the step's ``refresh_on`` → the change that records it and the state it leaves the step in.
CHANGES = {
    "table.table.created": [(add_one, "done"), (add_many, "done")],
    "table.table.updated": [(switch_off, "pending")],
    "table.table.deleted": [(delete, "pending")],
}


@pytest.mark.django_db
@pytest.mark.parametrize(
    "event,change,state",
    [(event, change, state) for event, cases in CHANGES.items() for change, state in cases],
    ids=lambda value: getattr(value, "__name__", value),
)
def test_each_change_of_the_step_records_an_event_that_refreshes_it(event, change, state):
    zone = make_zone()
    table = make_table("1", zone=zone, is_active=False) if state == "done" else make_table("1", zone=zone)
    seen = set(OutboxEvent.objects.values_list("id", flat=True))
    change(zone, table)
    recorded = set(OutboxEvent.objects.exclude(id__in=seen).values_list("name", flat=True))
    assert step(ctx_for())["state"] == state
    assert recorded & set(table_app().setup[0].refresh_on) == {event}


def test_the_step_is_refreshed_on_nothing_else():
    assert set(table_app().setup[0].refresh_on) == set(CHANGES)


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
def test_a_table_added_in_hub_b_re_runs_the_home_of_b_and_tells_a_nothing(listen):
    on_a, on_b = listen(A), listen(B)
    zone = run("table.zone.create", {"name": "Terrace"}, ctx_for(scope=B))
    run("table.table.create", {"zone_id": str(zone.id), "number": "1"}, ctx_for(scope=B))

    notes = received(on_b)
    assert {channel for channel, _ in notes} == {channel_for(B)}
    events = {event for _, payload in notes for event in payload["events"]}
    assert "base.setup.status" in live_registry.affected(events)
    assert received(on_a, timeout=QUIET) == []
