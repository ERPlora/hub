"""Numbering and series of the invoice app (INVOICE-F11–F13), run as the screens, the assistant and the API run them.
The rest of its write operations are in ``test_services.py``.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.utils import translation
from live.errors import Conflict, OperationError, PermissionDenied

from apps.invoice.models import Invoice, InvoiceSeries
from apps.invoice.tests.conftest import HUB_DB, ctx_for, run
from apps.invoice.tests.test_services import MADRID, at, events, manual

pytestmark = HUB_DB


# ── Numbering (INVOICE-F11) ─────────────────────────────────────────────────────────────────────


def test_a_new_year_opens_its_series_inheriting_the_last_ones_and_starts_again(
    issuer, monkeypatch
):
    run(
        "invoice.series.create",
        {
            "code": "FACT",
            "invoice_type": "F1",
            "year": 2026,
            "name": "Facturas",
            "format": "F{year}/{seq:04d}",
        },
    )
    at(monkeypatch, dt.datetime(2026, 12, 31, 22, 0, tzinfo=MADRID))
    assert manual().number == "F2026/0001"
    # 00:30 on 1 January in Madrid is still 2026 in UTC: the business's day decides.
    at(monkeypatch, dt.datetime(2026, 12, 31, 23, 30, tzinfo=dt.UTC))
    invoice = manual()
    assert (invoice.number, invoice.issue_date, invoice.year) == (
        "F2027/0001",
        dt.date(2027, 1, 1),
        2027,
    )
    new_year = InvoiceSeries.objects.get(code="FACT", year=2027)
    assert (new_year.name, new_year.format, new_year.is_default) == (
        "Facturas",
        "F{year}/{seq:04d}",
        False,
    )


def test_a_series_continues_the_numbering_of_another_system(issuer, today):
    run(
        "invoice.series.create",
        {"code": "FACT", "invoice_type": "F1", "year": today.year, "next_number": 120},
    )
    assert manual().number == f"FACT-{today.year}-000120"


def test_a_manual_invoice_says_what_the_operation_is_by_its_lines(issuer):
    # VeriFactu's DescripcionOperacion: the concepts invoiced, at most 500 characters.
    invoice = manual(
        lines=[
            {"description": "Haircut course", "quantity": "1", "unit_price": 5000, "tax_rate": "21"},
            {"description": "Dye kit", "quantity": "2", "unit_price": 1000, "tax_rate": "21"},
        ]
    )
    assert invoice.description == "Haircut course, Dye kit"
    assert [(line.unit_price, line.discount_amount) for line in invoice.lines] == [
        (Decimal("5000"), 0),
        (Decimal("1000"), 0),
    ]
    many = manual(
        lines=[
            {"description": "x" * 255, "quantity": "1", "unit_price": 100, "tax_rate": "21"}
        ]
        * 3
    )
    assert len(many.description) == 500


def test_a_number_that_exists_in_the_series_is_refused_and_the_counter_does_not_move(
    issuer, monkeypatch
):
    # Series made before the year was required (a format without {year}): next year repeats the
    # numbers, and the guard refuses the second one without spending it.
    for year in (2026, 2027):
        InvoiceSeries.objects.create(
            code="FACT", invoice_type="F1", year=year, prefix="F", format="F-{seq}"
        )
    at(monkeypatch, dt.datetime(2026, 6, 1, 12, tzinfo=MADRID))
    assert manual().number == "F-1"
    at(monkeypatch, dt.datetime(2027, 6, 1, 12, tzinfo=MADRID))
    with pytest.raises(Conflict) as refused:
        manual()
    assert refused.value.code == "invoice.number_taken"
    assert InvoiceSeries.objects.get(code="FACT", year=2027).current_number == 0


def test_a_number_longer_than_sixty_characters_is_refused_when_the_series_is_made(issuer, today):
    # NumSerieFactura holds 60 characters: the number with its widest sequence must fit.
    long = "{prefix}-{prefix}-{prefix}-{year}-{seq:09d}"
    with pytest.raises(OperationError) as refused:
        run(
            "invoice.series.create",
            {"code": "SHOP", "invoice_type": "F1", "year": today.year, "prefix": "A" * 20, "format": long},
        )
    assert (refused.value.status, set(refused.value.fields)) == (422, {"format"})
    series = run(
        "invoice.series.create",
        {"code": "SHOP", "invoice_type": "F1", "year": today.year, "format": long},
    )
    with pytest.raises(OperationError) as refused:
        run("invoice.series.update", {"series_id": str(series.id), "prefix": "B" * 20})
    assert (refused.value.status, set(refused.value.fields)) == (422, {"prefix"})


def test_a_manual_invoice_is_numbered_in_a_series_of_this_year(issuer, today):
    old = run(
        "invoice.series.create",
        {"code": "OLD", "invoice_type": "F1", "year": today.year - 1},
    )
    with pytest.raises(Conflict) as refused:
        manual(series_id=str(old.id))
    assert (refused.value.code, set(refused.value.fields)) == (
        "invoice.series_other_year",
        {"series_id"},
    )
    assert InvoiceSeries.objects.get(pk=old.id).current_number == 0


def test_a_manual_ticket_stops_at_the_tickets_limit(issuer):
    # The same limit as the till's (RD 1619/2012 art. 4): above it, only a full invoice.
    over = [{"description": "Course", "quantity": "1", "unit_price": 247935, "tax_rate": "21"}]
    with pytest.raises(Conflict) as refused:
        run("invoice.invoice.create", {"series_code": "TICKET", "lines": over})
    assert refused.value.code == "invoice.ticket_over_limit"
    assert not Invoice.objects.exists()
    at_limit = [{"description": "Course", "quantity": "1", "unit_price": 247934, "tax_rate": "21"}]
    ticket = run("invoice.invoice.create", {"series_code": "TICKET", "lines": at_limit})
    assert (ticket.invoice_type, ticket.total_amount) == ("F2", 300000)


def test_the_tickets_limit_is_said_with_its_thousands_grouped(issuer):
    # «3.000,00 €» in Spanish and «€3,000.00» in English, never «3000.00 €».
    over = [{"description": "Course", "quantity": "1", "unit_price": 247935, "tax_rate": "21"}]
    for language, amount in (("es", "3.000,00 €"), ("en", "€3,000.00")):
        with translation.override(language), pytest.raises(Conflict) as refused:
            run("invoice.invoice.create", {"series_code": "TICKET", "lines": over})
        assert refused.value.code == "invoice.ticket_over_limit"
        assert amount in refused.value.message.replace("\u00a0", " ").replace("\u202f", " ")


# ── Series (INVOICE-F12, F13) ───────────────────────────────────────────────────────────────────


def test_a_series_is_created_with_the_code_as_prefix_and_the_next_number(db):
    series = run(
        "invoice.series.create",
        {
            "code": "shop",
            "name": "Shop",
            "invoice_type": "F1",
            "year": 2026,
            "next_number": 5,
        },
    )
    assert (series.code, series.prefix, series.current_number, series.next_number) == (
        "SHOP",
        "SHOP",
        4,
        "SHOP-2026-000005",
    )
    assert events("invoice.series.created")[-1].payload == {
        "id": str(series.id),
        "code": "SHOP",
        "year": 2026,
    }


def test_a_code_is_unique_in_its_year(db):
    run("invoice.series.create", {"code": "SHOP", "invoice_type": "F1", "year": 2026})
    with pytest.raises(Conflict) as refused:
        run(
            "invoice.series.create",
            {"code": "SHOP", "invoice_type": "F2", "year": 2026},
        )
    assert (refused.value.code, set(refused.value.fields)) == (
        "invoice.series_exists",
        {"code"},
    )
    run("invoice.series.create", {"code": "SHOP", "invoice_type": "F1", "year": 2027})


def test_marking_a_series_default_demotes_the_one_of_its_year(db):
    first = run(
        "invoice.series.create",
        {"code": "A", "invoice_type": "F1", "year": 2026, "is_default": True},
    )
    other_year = run(
        "invoice.series.create",
        {"code": "A", "invoice_type": "F1", "year": 2027, "is_default": True},
    )
    second = run(
        "invoice.series.create",
        {"code": "B", "invoice_type": "F1", "year": 2026, "is_default": True},
    )
    assert InvoiceSeries.objects.get(pk=first.id).is_default is False
    assert InvoiceSeries.objects.get(pk=other_year.id).is_default is True
    run("invoice.series.update", {"series_id": str(first.id), "is_default": True})
    assert InvoiceSeries.objects.get(pk=second.id).is_default is False


def test_a_series_that_continues_another_system_stays_editable_until_its_first_document(
    issuer, today,
):
    # Starting at 7 moves the counter but numbers nothing: prefix, format and next number freeze only
    # with the first document the series issues (the e2e of INVOICE-F12 caught it locked at birth).
    series = run(
        "invoice.series.create",
        {"code": "SHOP", "invoice_type": "F1", "year": today.year, "next_number": 7},
    )
    assert series.format_locked is False
    changed = run(
        "invoice.series.update",
        {"series_id": str(series.id), "prefix": "W"},
    )
    changed = run(
        "invoice.series.update",
        {"series_id": str(series.id), "format": "{prefix}{year}{seq:03d}", "next_number": 8},
    )
    assert (changed.prefix, changed.next_number, changed.format_locked) == (
        "W",
        f"W{today.year}008",
        False,
    )
    assert manual(series_code="SHOP").number == f"W{today.year}008"
    with pytest.raises(Conflict) as refused:
        run("invoice.series.update", {"series_id": str(series.id), "prefix": "X"})
    assert refused.value.code == "invoice.series_locked"


def test_prefix_format_and_next_number_freeze_with_the_first_number(issuer, today):
    series = run(
        "invoice.series.create",
        {"code": "FACT", "invoice_type": "F1", "year": today.year},
    )
    changed = run(
        "invoice.series.update",
        {
            "series_id": str(series.id),
            "prefix": "F",
            "format": "{prefix}{year}{seq:05d}",
            "next_number": 10,
        },
    )
    assert (
        changed.prefix,
        changed.format,
        changed.current_number,
        changed.next_number,
    ) == ("F", "{prefix}{year}{seq:05d}", 9, f"F{today.year}00010")
    assert manual().number == f"F{today.year}00010"
    for change in ({"prefix": "G"}, {"format": "{year}{seq}"}, {"next_number": 99}):
        with pytest.raises(Conflict) as refused:
            run("invoice.series.update", {"series_id": str(series.id), **change})
        assert refused.value.code == "invoice.series_locked"
    renamed = run(
        "invoice.series.update",
        {
            "series_id": str(series.id),
            "name": "Main",
            "is_active": False,
            "prefix": "F",
        },
    )
    assert (renamed.name, renamed.is_active) == ("Main", False)
    assert events("invoice.series.updated")[-1].payload["fields"] == [
        "is_active",
        "name",
    ]


def test_an_employee_cannot_keep_the_series(db):
    with pytest.raises(PermissionDenied):
        run(
            "invoice.series.create",
            {"code": "A", "invoice_type": "F1", "year": 2026},
            ctx_for("hub_employee"),
        )
