"""base's live queries: the Home's three, each re-run after the events its hooks name (PLAN-HUB round 2026-10-21).

The modules declare in ``refresh_on`` what changes their steps, panels and counters; base follows the union of them
per query, and the SaaS's photo (``base.hub.state_applied``: apps, country or vertical may change) re-runs all three.
"""

from live.live_registry import live_registry
from live.meta import module_configs

from base import live as base_live
from base.events import HUB_STATE_APPLIED


def declared(hook):
    return sorted({event for config in module_configs() for item in getattr(config, hook) for event in item.refresh_on})


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_the_three_queries_and_their_events():
    on = {name: events for name, events in live_registry.subscribable.items() if name.startswith("base.")}
    assert on == {
        "base.setup.status": sorted({*declared("setup"), HUB_STATE_APPLIED}),
        "base.widget.list": sorted({*declared("widgets"), HUB_STATE_APPLIED}),
        "base.bell.counters": sorted({*declared("bell"), HUB_STATE_APPLIED}),
        "base.notice.list": sorted({*declared("notices"), HUB_STATE_APPLIED}),
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
