"""Live queries of base: the Home's three and the device's notices, re-run after the events the modules' hooks name.

Each step, panel and counter names in ``refresh_on`` the events that change it (PLAN-HUB round 2026-10-21); base
follows the union of them per query, fixed from the start like every declaration. The SaaS's photo
(``base.hub.state_applied``) re-runs the three: it may turn apps on or off and change the country or the vertical. What
Settings › Data does to the business (a load, an undo, a reset) re-runs them too, and its own two queries.
"""

from live.live_registry import live
from live.meta import module_configs

from base.events import DATA_EVENTS, HUB_STATE_APPLIED


def events_of(hook: str) -> list[str]:
    """The events that re-run base's query of ``hook`` (``setup``, ``widgets``, ``bell`` or ``notices``)."""
    named = {event for config in module_configs() for item in getattr(config, hook) for event in item.refresh_on}
    return sorted(named | {HUB_STATE_APPLIED})


live("base.setup.status", on=sorted({*events_of("setup"), *DATA_EVENTS}))
live("base.widget.list", on=sorted({*events_of("widgets"), *DATA_EVENTS}))
live("base.bell.counters", on=sorted({*events_of("bell"), *DATA_EVENTS}))
live("base.notice.list", on=events_of("notices"))

# ── Data: blueprints, imports and reset (APP-BASE-2) ──
# A load, an undo or a reset re-runs the Home (above: BASE-G131, the Home up to date without reloading), the catalogue
# (the Home's card asks whether the business is still empty) and the list of loads of Settings › Data.
live("base.blueprint.list", on=sorted({HUB_STATE_APPLIED, *DATA_EVENTS}))
live("base.import.list", on=sorted(DATA_EVENTS))
