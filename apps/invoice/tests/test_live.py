"""Live queries of the invoice app: which events re-run which query, and every event cited is emitted."""

from pathlib import Path

from live.live_registry import live_registry

from apps.invoice import events
from apps.tax import events as tax_events

EVENTS_SOURCE = Path(events.__file__).read_text()
TAX_EVENTS_SOURCE = Path(tax_events.__file__).read_text()
INVOICE = [
    "invoice.invoice.issued",
    "invoice.invoice.rectified",
    "invoice.invoice.paid",
]
SERIES = ["invoice.series.created", "invoice.series.updated", "invoice.invoice.issued"]
# The rectification's preview: what is left of the invoice and the next number of the rectifying series (INVOICE-F08).
PREVIEW = [
    "invoice.invoice.issued",
    "invoice.invoice.rectified",
    "invoice.series.created",
    "invoice.series.updated",
]
# What a typed line starts with follows the business's territory and Taxes' rules (TAX-F11).
TAX_RULES = [
    "tax.rule.created",
    "tax.rule.ended",
    "tax.rule.deactivated",
    "tax.rule.activated",
    "tax.settings.updated",
]


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
        "invoice.invoice.rectification_preview": PREVIEW,
        "invoice.invoice.line_defaults": TAX_RULES,
        "invoice.series.list": SERIES,
        "invoice.series.peek_next": SERIES,
        "invoice.numbering.status": SERIES,
        "invoice.numbering.gaps": ["invoice.invoice.issued"],
        "invoice.numbering.allocations": ["invoice.invoice.issued"],
        "invoice.issuer.get": ["invoice.issuer.updated"],
    }


def test_every_event_is_a_literal_of_events_py():
    # Invoicing's own events, or those of Taxes (a requirement), each a literal of its app's events.py.
    for on in invoice_queries().values():
        for event in on:
            assert f'"{event}"' in (TAX_EVENTS_SOURCE if event.startswith("tax.") else EVENTS_SOURCE), event


def test_a_tax_rule_or_the_territory_re_runs_only_what_a_typed_line_starts_with():
    affected = {
        name
        for name in live_registry.affected(["tax.settings.updated"])
        if name.startswith("invoice.")
    }
    assert affected == {"invoice.invoice.line_defaults"}


def test_issuing_re_runs_the_lists_the_series_and_the_book_but_not_the_issuer():
    affected = {
        name
        for name in live_registry.affected([events.INVOICE_ISSUED])
        if name.startswith("invoice.")
    }
    assert affected == set(invoice_queries()) - {
        "invoice.issuer.get",
        "invoice.invoice.line_defaults",
    }


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
