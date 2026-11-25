"""Live queries of the tips app and the events that re-run them after the COMMIT."""

from live.live_registry import live

from apps.tip.events import PAYMENT_METHOD_CREATED, SALE_SETTINGS_UPDATED, SETTINGS_UPDATED, TIP_EVENTS

live("tip.tip.list", on=TIP_EVENTS)
# Its payment methods are Sales': a new one or one switched off changes what can be set.
live("tip.settings.get", on=[SETTINGS_UPDATED, PAYMENT_METHOD_CREATED, SALE_SETTINGS_UPDATED])
