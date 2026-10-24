"""Live queries of base: the Home's three and the device's notices, re-run after the events the modules' hooks name.

Each step, panel and counter names in ``refresh_on`` the events that change it (PLAN-HUB round 2026-10-21); base
follows the union of them per query, fixed from the start like every declaration. The SaaS's photo
(``base.hub.state_applied``) re-runs the three: it may turn apps on or off and change the country or the vertical. What
Settings › Data does to the business (a load, an undo, a reset) re-runs them too, and its own two queries.
"""

from live.live_registry import live
from live.meta import module_configs

from base.events import (
    DATA_EVENTS,
    FAILED_EVENT_CREATED,
    FAILED_EVENT_DISCARDED,
    FAILED_EVENT_RETRIED,
    HUB_REGISTERED,
    HUB_STATE_APPLIED,
)

#: What changes the failed events: the relay gives one up, who runs the business resends or discards one (APP-BASE-7).
FAILED_EVENTS = [FAILED_EVENT_CREATED, FAILED_EVENT_RETRIED, FAILED_EVENT_DISCARDED]


def events_of(hook: str) -> list[str]:
    """The events that re-run base's query of ``hook`` (``setup``, ``widgets``, ``bell`` or ``notices``)."""
    named = {event for config in module_configs() for item in getattr(config, hook) for event in item.refresh_on}
    return sorted(named | {HUB_STATE_APPLIED})


live("base.setup.status", on=sorted({*events_of("setup"), *DATA_EVENTS}))
live("base.widget.list", on=sorted({*events_of("widgets"), *DATA_EVENTS}))
# The failed events of System (APP-BASE-7) change the bell's row of them too.
live("base.bell.counters", on=sorted({*events_of("bell"), *DATA_EVENTS, *FAILED_EVENTS}))
live("base.notice.list", on=events_of("notices"))

# ── Apps (APP-BASE-4) ──────────────────────────────────────────────────────────────────────────────────────────
# The SaaS's photo gives or takes the right to a paid module (base.entitlement): the Apps screen follows it.
live("base.app.list", on=[HUB_STATE_APPLIED])
# The plan and the members come in the photo too: «Plan and limits» follows it.
live("base.plan.usage", on=[HUB_STATE_APPLIED])

# ── Data: blueprints, imports and reset (APP-BASE-2) ──
# A load, an undo or a reset re-runs the Home (above: BASE-G131, the Home up to date without reloading), the catalogue
# (the Home's card asks whether the business is still empty) and the list of loads of Settings › Data.
live("base.blueprint.list", on=sorted({HUB_STATE_APPLIED, *DATA_EVENTS}))
live("base.import.list", on=sorted(DATA_EVENTS))

# ── Business settings and the hub's context (APP-BASE-6) ──
# The SaaS registers the business again when its owner changes its name, time zone or language on erplora.com
# (HUBS-F15): Settings › Business follows it without reloading.
live("base.business.get", on=[HUB_REGISTERED])

# ── System (APP-BASE-7) ────────────────────────────────────────────────────────────────────────────────────────
# The failed events follow the relay, who resends or discards them, and the photo (it turns their app on or off).
live("base.failed_event.list", on=sorted([HUB_STATE_APPLIED, *FAILED_EVENTS]))
# The status: the photo, and every reconnection of the stream (a deploy) sends it again with the new release.
live("base.system.status", on=[HUB_STATE_APPLIED])
# The log: what a new event brings shows when the tab opens again; a failed event changes the level of its row at once.
live("base.event.list", on=sorted([HUB_STATE_APPLIED, *FAILED_EVENTS]))
