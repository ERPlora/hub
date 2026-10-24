"""Live queries of base: the Home's three and the device's notices, re-run after the events the modules' hooks name;
and the way in's (APP-BASE-3): the grid of «Switch user», the devices, the PIN pad's dial and «My profile».

Each step, panel and counter names in ``refresh_on`` the events that change it (PLAN-HUB round 2026-10-21); base
follows the union of them per query, fixed from the start like every declaration. The SaaS's photo
(``base.hub.state_applied``) re-runs the three: it may turn apps on or off and change the country or the vertical.
"""

from live.live_registry import live
from live.meta import module_configs

from base import events
from base.events import HUB_STATE_APPLIED


def events_of(hook: str) -> list[str]:
    """The events that re-run base's query of ``hook`` (``setup``, ``widgets``, ``bell`` or ``notices``)."""
    named = {event for config in module_configs() for item in getattr(config, hook) for event in item.refresh_on}
    return sorted(named | {HUB_STATE_APPLIED})


live("base.setup.status", on=events_of("setup"))
live("base.widget.list", on=events_of("widgets"))
live("base.bell.counters", on=events_of("bell"))
live("base.notice.list", on=events_of("notices"))


# The way in (APP-BASE-3): the grid of «Switch user» follows the PINs, the people (the photo), the dial and the devices.
_DEVICES = [events.DEVICE_MODE_CHANGED, events.DEVICE_RENAMED, events.DEVICE_REMOVED, events.DEVICES_PRUNED]
live(
    "base.access.faces",
    on=sorted({events.PIN_SET, HUB_STATE_APPLIED, events.ACCESS_SETTINGS_CHANGED, events.PROFILE_UPDATED, *_DEVICES}),
)
live("base.device.list", on=sorted(_DEVICES))
live("base.device.current", on=sorted({events.DEVICE_MODE_CHANGED, events.DEVICE_REMOVED, events.DEVICES_PRUNED}))
live("base.access.settings", on=[events.ACCESS_SETTINGS_CHANGED])
live("base.profile.get", on=sorted({events.PROFILE_UPDATED, events.PIN_SET, events.ACCESS_SETTINGS_CHANGED}))
