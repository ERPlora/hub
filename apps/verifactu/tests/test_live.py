"""Live queries of the verifactu app: which events re-run which query, and every event cited is emitted."""

from pathlib import Path

from live.live_registry import live_registry

from apps.verifactu import events

EVENTS_SOURCE = Path(events.__file__).read_text()
RECORDS = [
    "verifactu.record.created",
    "verifactu.record.transmitted",
    "verifactu.record.rejected",
    "verifactu.record.accepted_with_errors",
    "verifactu.contingency.processed",
    "verifactu.contingency.retried",
    "verifactu.record.reconciled",
]


def verifactu_queries():
    return {
        name: on
        for name, on in live_registry.subscribable.items()
        if name.startswith("verifactu.")
    }


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_each_query_and_its_events():
    assert verifactu_queries() == {
        "verifactu.config.get": [
            "verifactu.config.changed",
            "verifactu.record.created",
        ],
        "verifactu.record.list": RECORDS,
        "verifactu.record.get": [*RECORDS, "verifactu.config.changed"],
        "verifactu.record.by_invoice": RECORDS,
        "verifactu.contingency.list": RECORDS,
        "verifactu.event.list": events.ALL,
        "verifactu.stats.compliance_summary": RECORDS,
        "verifactu.stats.records_by_status": RECORDS,
        "verifactu.stats.contingency_summary": RECORDS,
        "verifactu.stats.events_recent": events.ALL,
        "verifactu.aeat_record.list": [
            "verifactu.aeat.queried",
            "verifactu.chain.recovered",
        ],
        "verifactu.chain.status": [
            "verifactu.record.created",
            "verifactu.chain.validated",
            "verifactu.chain.recovered",
        ],
        "verifactu.diagnostic.last": ["verifactu.diagnostic.run"],
    }


def test_every_event_is_a_literal_of_events_py():
    for on in verifactu_queries().values():
        for event in on:
            assert f'"{event}"' in EVENTS_SOURCE, event


def test_a_new_record_re_runs_the_lists_the_queue_and_the_chain_but_not_the_aeats_photo():
    affected = {
        name
        for name in live_registry.affected([events.RECORD_CREATED])
        if name.startswith("verifactu.")
    }
    assert "verifactu.aeat_record.list" not in affected
    assert {
        "verifactu.record.list",
        "verifactu.contingency.list",
        "verifactu.chain.status",
    } <= affected
