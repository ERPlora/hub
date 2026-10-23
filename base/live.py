"""Live queries of base: the Home's three and the device's notices, re-run after the events the modules' hooks name.

Each step, panel and counter names in ``refresh_on`` the events that change it (PLAN-HUB round 2026-10-21); base
follows the union of them per query, fixed from the start like every declaration. The SaaS's photo
(``base.hub.state_applied``) re-runs the three: it may turn apps on or off and change the country or the vertical.
"""

from live.live_registry import live
from live.meta import module_configs

from base.events import HUB_STATE_APPLIED


def events_of(hook: str) -> list[str]:
    """The events that re-run base's query of ``hook`` (``setup``, ``widgets``, ``bell`` or ``notices``)."""
    named = {event for config in module_configs() for item in getattr(config, hook) for event in item.refresh_on}
    return sorted(named | {HUB_STATE_APPLIED})


live("base.setup.status", on=events_of("setup"))
live("base.widget.list", on=events_of("widgets"))
live("base.bell.counters", on=events_of("bell"))
live("base.notice.list", on=events_of("notices"))

# ── Apps (APP-BASE-4) ──────────────────────────────────────────────────────────────────────────────────────────
# The SaaS's photo gives or takes the right to a paid module (base.entitlement): the Apps screen follows it.
live("base.app.list", on=[HUB_STATE_APPLIED])
