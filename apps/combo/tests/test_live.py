"""Live queries of the combo app: which events re-run which query.

The list of menus follows the menus; a menu's builder and the till's catalogue follow everything of a
menu and Inventory's product changes (a choice shows its product's name, price and state). ``resolve``
is a calculation, not a list to follow.
"""

import json
from pathlib import Path

import psycopg
import pytest
from live.errors import InvalidPayload
from live.live_registry import live_registry
from live.outbox import channel_for

from apps.combo import events, services

from .conftest import A, B, ctx_for, run

EVENTS_SOURCE = Path(events.__file__).read_text()
SERVICES_SOURCE = Path(services.__file__).read_text()

MENU = [events.COMBO_CREATED, events.COMBO_UPDATED, events.COMBO_DELETED]
TREE = [
    *MENU,
    events.GROUP_CREATED,
    events.GROUP_UPDATED,
    events.GROUP_DELETED,
    events.GROUP_REORDERED,
    events.OPTION_CREATED,
    events.OPTION_UPDATED,
    events.OPTION_DELETED,
    events.OPTION_REORDERED,
    "inventory.product.updated",
    "inventory.product.deleted",
]


def combo_queries():
    return {
        name: on
        for name, on in live_registry.subscribable.items()
        if name.startswith("combo.")
    }


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_the_lists_and_the_menu_can_be_followed_live():
    assert set(combo_queries()) == {
        "combo.combo.list",
        "combo.combo.get",
        "combo.combo.for_sale",
    }


def test_each_query_and_its_events():
    queries = combo_queries()
    # The list counts the courses of each menu.
    assert queries["combo.combo.list"] == [
        *MENU,
        events.GROUP_CREATED,
        events.GROUP_DELETED,
    ]
    assert queries["combo.combo.get"] == TREE
    assert queries["combo.combo.for_sale"] == TREE


def test_every_event_of_the_app_is_a_literal_of_events_py_recorded_by_a_service():
    for on in combo_queries().values():
        for event in on:
            assert f'"{event}"' in EVENTS_SOURCE, event
    for name, value in vars(events).items():
        if name.isupper() and isinstance(value, str) and value.startswith("combo."):
            assert f"events.{name}" in SERVICES_SOURCE, name


def test_a_product_deleted_in_inventory_re_runs_the_builder_and_the_till():
    affected = live_registry.affected(["inventory.product.deleted"])
    assert {"combo.combo.get", "combo.combo.for_sale"} <= affected
    assert "combo.combo.list" not in affected


# A write in hub B reaches B's channel only (real LISTEN sessions, after the COMMIT)


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


def received(session, timeout=1.0, stop_after=None):
    return [(note.channel, json.loads(note.payload)) for note in session.notifies(timeout=timeout, stop_after=stop_after)]


@pytest.mark.django_db(transaction=True)
def test_a_menu_written_in_b_notifies_b_only(listen):
    on_a, on_b = listen(A), listen(B)
    run("combo.combo.create", {"name": "Menu B", "supply_kind": "goods"}, ctx_for(scope=B))
    assert received(on_b, stop_after=1) == [(channel_for(B), {"events": [events.COMBO_CREATED]})]
    assert received(on_a, timeout=0.3) == []
    # Positive control: the same listener of A hears a menu written in A.
    run("combo.combo.create", {"name": "Menu A", "supply_kind": "goods"}, ctx_for(scope=A))
    assert received(on_a, stop_after=1) == [(channel_for(A), {"events": [events.COMBO_CREATED]})]


@pytest.mark.django_db(transaction=True)
def test_a_refused_write_notifies_nobody(listen):
    on_a = listen(A)
    with pytest.raises(InvalidPayload):
        run("combo.combo.create", {"name": "Menu"}, ctx_for(scope=A))
    assert received(on_a, timeout=0.3) == []
