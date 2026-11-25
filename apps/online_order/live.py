"""Live queries of Online orders and the events that re-run them after the COMMIT."""

from live.live_registry import live

from apps.online_order.events import QR_CODE_REGENERATED
from apps.table.events import TABLE_EVENTS, ZONE_EVENTS

# A table's code, and each table's number and zone as Tables changes them.
live("online_order.qr_code.list", on=[QR_CODE_REGENERATED, *TABLE_EVENTS, *ZONE_EVENTS])
