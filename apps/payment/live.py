"""Live queries of the payment app and the events that re-run them after the COMMIT."""

from live.live_registry import live

from apps.payment.events import METHOD_EVENTS, METHOD_UPDATED, PAYMENT_EVENTS

# A payment shows its method's name: renaming the method changes the rows.
live("payment.payment.list", on=[*PAYMENT_EVENTS, METHOD_UPDATED])
live("payment.payment.get", on=[*PAYMENT_EVENTS, METHOD_UPDATED])
live("payment.method.list", on=METHOD_EVENTS)
live("payment.method.get", on=METHOD_EVENTS)
