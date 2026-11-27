"""Live queries of the tips app and the events that re-run them after the COMMIT."""

from live.live_registry import live

from apps.tip.events import (
    PAYMENT_METHOD_CREATED,
    SALE_SETTINGS_UPDATED,
    SETTINGS_UPDATED,
    SHIFT_EVENTS,
    TIP_EVENTS,
)

live("tip.tip.list", on=TIP_EVENTS)
# By its sale's number, a tip added to that sale changes which one is read.
live("tip.tip.get", on=TIP_EVENTS)
# Its payment methods are Sales': a new one or one switched off changes what can be set.
live("tip.settings.get", on=[SETTINGS_UPDATED, PAYMENT_METHOD_CREATED, SALE_SETTINGS_UPDATED])
# What the charge proposes is the settings' suggestions of a payment method.
live("tip.suggestion.get", on=[SETTINGS_UPDATED, PAYMENT_METHOD_CREATED, SALE_SETTINGS_UPDATED])
# By shift, a working day clocked in, out or corrected in Time clock moves the tips from one line to another.
live("tip.report.get", on=[*TIP_EVENTS, *SHIFT_EVENTS])
live("tip.report.mine", on=TIP_EVENTS)
