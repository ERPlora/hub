"""Live queries of the demo app and the events that re-run them after the COMMIT."""

from live.live_registry import live

from apps.demo.events import ITEM_CREATED, ITEM_DELETED, ITEM_LINE_ADDED, ITEM_UPDATED

live("demo.item.list", on=[ITEM_CREATED, ITEM_UPDATED, ITEM_DELETED, ITEM_LINE_ADDED])
# A new item changes no existing detail.
live("demo.item.detail", on=[ITEM_UPDATED, ITEM_DELETED, ITEM_LINE_ADDED])
live("demo.item.stats", on=[ITEM_CREATED, ITEM_UPDATED, ITEM_DELETED, ITEM_LINE_ADDED])
