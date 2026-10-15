"""Live queries of the invoice app: which events re-run which query, and every event cited is emitted."""

from pathlib import Path

from live.live_registry import live_registry

from apps.invoice import events

EVENTS_SOURCE = Path(events.__file__).read_text()
INVOICE = [
    "invoice.invoice.issued",
    "invoice.invoice.rectified",
    "invoice.invoice.paid",
]
SERIES = ["invoice.series.created", "invoice.series.updated", "invoice.invoice.issued"]


def invoice_queries():
    return {
        name: on
        for name, on in live_registry.subscribable.items()
        if name.startswith("invoice.")
    }


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_each_query_and_its_events():
    assert invoice_queries() == {
        "invoice.invoice.list": INVOICE,
        "invoice.invoice.get": INVOICE,
        "invoice.invoice.by_source": INVOICE,
        "invoice.invoice.document": INVOICE,
        "invoice.series.list": SERIES,
        "invoice.series.peek_next": SERIES,
        "invoice.numbering.status": SERIES,
        "invoice.numbering.gaps": ["invoice.invoice.issued"],
        "invoice.numbering.allocations": ["invoice.invoice.issued"],
        "invoice.issuer.get": ["invoice.issuer.updated"],
    }


def test_every_event_is_a_literal_of_events_py():
    for on in invoice_queries().values():
        for event in on:
            assert f'"{event}"' in EVENTS_SOURCE, event


def test_issuing_re_runs_the_lists_the_series_and_the_book_but_not_the_issuer():
    affected = {
        name
        for name in live_registry.affected([events.INVOICE_ISSUED])
        if name.startswith("invoice.")
    }
    assert affected == set(invoice_queries()) - {"invoice.issuer.get"}


def test_paying_re_runs_only_what_shows_a_document():
    affected = {
        name
        for name in live_registry.affected([events.INVOICE_PAID])
        if name.startswith("invoice.")
    }
    assert affected == {
        "invoice.invoice.list",
        "invoice.invoice.get",
        "invoice.invoice.by_source",
        "invoice.invoice.document",
    }
