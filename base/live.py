"""Live queries of base: the Home's three and the device's notices, re-run after the events the modules' hooks name;
and the way in's (APP-BASE-3): the grid of «Switch user», the devices, the PIN pad's dial and «My profile».

Each step, panel and counter names in ``refresh_on`` the events that change it (PLAN-HUB round 2026-10-21); base
follows the union of them per query, fixed from the start like every declaration. The SaaS's photo
(``base.hub.state_applied``) re-runs the three: it may turn apps on or off and change the country or the vertical. What
Settings › Data does to the business (a load, an undo, a reset) re-runs them too, and its own two queries.
"""

from live.live_registry import live
from live.meta import module_configs

from base import events
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


# The way in (APP-BASE-3): the grid of «Switch user» follows the PINs, the people (the photo), the dial and the devices.
_DEVICES = [events.DEVICE_MODE_CHANGED, events.DEVICE_RENAMED, events.DEVICE_REMOVED, events.DEVICES_PRUNED]
live(
    "base.access.faces",
    on=sorted(
        {events.PIN_SET, HUB_STATE_APPLIED, events.ACCESS_SETTINGS_CHANGED, events.PROFILE_UPDATED, *_DEVICES}
        # APP-BASE-5: a PIN taken away leaves the grid.
        | {events.PERSON_PIN_REMOVED}
    ),
)
live("base.device.list", on=sorted(_DEVICES))
live("base.device.current", on=sorted({events.DEVICE_MODE_CHANGED, events.DEVICE_REMOVED, events.DEVICES_PRUNED}))
live("base.access.settings", on=[events.ACCESS_SETTINGS_CHANGED])
live("base.profile.get", on=sorted({events.PROFILE_UPDATED, events.PIN_SET, events.ACCESS_SETTINGS_CHANGED}))

# ── People and permissions (APP-BASE-5) ────────────────────────────────────────────────────────────────────────────
# Employees › Personal and a person's page follow the ways in (a PIN chosen or taken away, a badge), the names of «My
# profile» and the photo (erplora.com's people and roles, and the plan's places); Roles, the photo.
_PEOPLE = sorted({events.PIN_SET, events.PROFILE_UPDATED, HUB_STATE_APPLIED, *events.PERSON_EVENTS})
live("base.person.list", on=_PEOPLE)
live("base.person.detail", on=_PEOPLE)
live("base.role.list", on=[HUB_STATE_APPLIED])
# The keys follow their own making, rotating and revoking; the apps a key may reach, the photo (a paid app comes or goes).
live("base.api_key.list", on=sorted({HUB_STATE_APPLIED, *events.API_KEY_EVENTS}))
# Approvals follow each approval given and each pass spent; who may approve, the ways in and the photo (the roles).
live("base.approval.list", on=sorted(events.APPROVAL_EVENTS))
live("base.approval.approvers", on=sorted({events.PIN_SET, events.PROFILE_UPDATED, HUB_STATE_APPLIED, *events.PERSON_EVENTS}))
