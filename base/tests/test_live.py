"""base's live queries: the Home's three, each re-run after the events its hooks name (PLAN-HUB round 2026-10-21).

The modules declare in ``refresh_on`` what changes their steps, panels and counters; base follows the union of them
per query, and the SaaS's photo (``base.hub.state_applied``: apps, country or vertical may change) re-runs all three.
"""

from live.live_registry import live_registry
from live.meta import module_configs

from base import live as base_live
from base.events import (
    BLUEPRINT_IMPORTED,
    FAILED_EVENT_CREATED,
    FAILED_EVENT_DISCARDED,
    FAILED_EVENT_RETRIED,
    FILE_EVENTS,
    HUB_DATA_RESET,
    HUB_REGISTERED,
    HUB_STATE_APPLIED,
    IMPORT_UNDONE,
)

#: What Settings › Data does to the business (APP-BASE-2): the Home reads itself again after each (BASE-G131).
DATA = {BLUEPRINT_IMPORTED, IMPORT_UNDONE, HUB_DATA_RESET}
FAILED_EVENTS = (FAILED_EVENT_CREATED, FAILED_EVENT_RETRIED, FAILED_EVENT_DISCARDED)

#: The way in's live queries (APP-BASE-3) have their own test: base/tests/test_access_live.py.
WAY_IN = ("base.access.", "base.device.", "base.profile.")
#: People and permissions' (APP-BASE-5) too: base/tests/test_people.py and base/tests/test_approvals.py.
PEOPLE = ("base.person.", "base.role.", "base.api_key.", "base.approval.", "base.api_doc.")


def declared(hook):
    return sorted({event for config in module_configs() for item in getattr(config, hook) for event in item.refresh_on})


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_the_three_queries_and_their_events():
    on = {
        name: events
        for name, events in live_registry.subscribable.items()
        if name.startswith("base.") and not name.startswith(WAY_IN + PEOPLE)
    }
    assert on == {
        "base.setup.status": sorted({*declared("setup"), HUB_STATE_APPLIED, *DATA}),
        "base.widget.list": sorted({*declared("widgets"), HUB_STATE_APPLIED, *DATA}),
        # The failed events the relay gives up on, resent or discarded change the bell's row (APP-BASE-7).
        "base.bell.counters": sorted({*declared("bell"), HUB_STATE_APPLIED, *DATA, *FAILED_EVENTS}),
        "base.notice.list": sorted({*declared("notices"), HUB_STATE_APPLIED}),
        # Apps (APP-BASE-4): the photo gives or takes the right to a paid module.
        "base.app.list": [HUB_STATE_APPLIED],
        "base.plan.usage": [HUB_STATE_APPLIED],
        "base.blueprint.list": sorted({HUB_STATE_APPLIED, *DATA}),
        "base.import.list": sorted(DATA),
        # Business settings (APP-BASE-6): the SaaS registers the business again when it changes on erplora.com.
        "base.business.get": [HUB_REGISTERED],
        # System (APP-BASE-7): the failed events, and the photo (it turns the app they were for on or off).
        "base.failed_event.list": sorted({HUB_STATE_APPLIED, *FAILED_EVENTS}),
        # The status re-runs on the photo and on every reconnection (a deploy's new release shows by itself); the log
        # also when a failed event appears, is resent or discarded (its level changes).
        "base.system.status": [HUB_STATE_APPLIED],
        "base.event.list": sorted({HUB_STATE_APPLIED, *FAILED_EVENTS}),
        # Files (APP-BASE-8): every write of the business's files, and the photo (the plan's space).
        "base.file.list": sorted({HUB_STATE_APPLIED, *FILE_EVENTS}),
        # Locations (round 2026-10-24b): nothing writes them yet but the admin; the photo re-runs them.
        "base.location.list": [HUB_STATE_APPLIED],
    }


def test_the_union_is_of_every_module_whatever_the_setting():
    """Declarations are fixed from the start: the demo's events are followed even where its hooks are hidden."""
    assert "demo.item.created" in base_live.events_of("setup")
    assert base_live.events_of("bell") == sorted({*declared("bell"), HUB_STATE_APPLIED})


def test_a_new_demo_item_re_runs_the_list_and_the_bell_but_not_the_panels():
    affected = live_registry.affected(["demo.item.created"])
    assert {"base.setup.status", "base.bell.counters"} <= affected


def test_a_booking_re_runs_the_devices_notices():
    """APPOINTMENT-F28: Citas names the booking and the cancellation; a write in another hub re-runs only its own scope
    (the live registry's rule, tested in packages/live), and a change of the photo re-runs them too."""
    affected = live_registry.affected(["appointment.appointment.created"])
    assert "base.notice.list" in affected
    assert "base.notice.list" in live_registry.affected(["appointment.appointment.cancelled"])
    assert "base.notice.list" in live_registry.affected([HUB_STATE_APPLIED])
    assert "base.notice.list" not in live_registry.affected(["demo.item.created"])


def test_loading_undoing_or_resetting_re_runs_the_home_and_the_loads():
    """BASE-G131: the Home reads its list, its panels and its bell again after a load, without reloading the page."""
    for event in DATA:
        assert {"base.setup.status", "base.widget.list", "base.bell.counters", "base.import.list"} <= (
            live_registry.affected([event])
        )
    assert "base.notice.list" not in live_registry.affected([BLUEPRINT_IMPORTED])
