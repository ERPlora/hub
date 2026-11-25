"""The tables' codes can be followed live: a new code, and any change to the tables, re-run the list."""

from live.live_registry import live_registry

from apps.online_order import events


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_the_list_follows_its_codes_and_the_tables():
    assert live_registry.subscribable["online_order.qr_code.list"] == [
        events.QR_CODE_REGENERATED,
        "table.table.created",
        "table.table.updated",
        "table.table.deleted",
        "table.zone.created",
        "table.zone.updated",
        "table.zone.deleted",
    ]
