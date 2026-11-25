"""The two dates of a manual invoice (INVOICE-F03): the day it is dated, today unless an earlier one is chosen, and the
day it falls due, if any. The records are sealed in VeriFactu's testing environment and never sent: nothing here leaves
the machine."""

import datetime as dt
import re

import pytest
from live.errors import Conflict
from pydantic import ValidationError

from apps.invoice.models import Invoice, InvoiceSeries
from apps.invoice.tests.conftest import HUB_DB, fields, run
from apps.invoice.tests.manual import LINE, RECIPIENT, manual
from apps.verifactu.models import Record

pytestmark = [HUB_DB, pytest.mark.usefixtures("issuer", "nothing_leaves")]

YESTERDAY, TODAY, TOMORROW = dt.date(2026, 11, 23), dt.date(2026, 11, 24), dt.date(2026, 11, 25)
NOON = ("Europe/Madrid", dt.datetime(2026, 11, 24, 11, 0, tzinfo=dt.UTC))
#: 2 January 2027, the first days a business still invoices the year that ended.
NEW_YEAR = ("Europe/Madrid", dt.datetime(2027, 1, 2, 11, 0, tzinfo=dt.UTC))
#: 23:30 of 2 November in Bogotá; 05:30 of the 3rd in Madrid.
BOGOTA_NIGHT = ("America/Bogota", dt.datetime(2026, 11, 3, 4, 30, tzinfo=dt.UTC))


def stored(answer) -> Invoice:
    return Invoice.objects.get(pk=answer.id)


def refused(**data) -> Conflict:
    """The refusal of a manual invoice with ``data``: nothing is issued and no number is spent."""
    before = (Invoice.objects.count(), sum(InvoiceSeries.objects.values_list("current_number", flat=True)))
    with pytest.raises(Conflict) as error:
        manual(**data)
    after = (Invoice.objects.count(), sum(InvoiceSeries.objects.values_list("current_number", flat=True)))
    assert after == before
    return error.value


# The day it is dated


def test_an_invoice_is_dated_the_day_chosen_and_so_is_its_operation(at):
    at(NOON)
    answer = manual(issue_date="2026-11-23")
    invoice = stored(answer)
    assert (answer.issue_date, answer.operation_date, answer.number) == (YESTERDAY, YESTERDAY, "FACT-2026-000001")
    assert (invoice.issue_date, invoice.operation_date, invoice.issued_at) == (YESTERDAY, YESTERDAY, NOON[1])


@pytest.mark.parametrize("data", [{}, {"issue_date": None}, {"issue_date": "2026-11-24"}])
def test_an_invoice_is_dated_today_unless_another_day_is_chosen(at, data):
    at(NOON)
    assert manual(**data).issue_date == TODAY


def test_a_future_day_is_refused_under_its_field(at):
    at(NOON)
    error = refused(issue_date="2026-11-25")
    assert (error.code, set(error.fields)) == ("invoice.issue_date_in_future", {"issue_date"})


def test_the_future_starts_on_the_business_s_clock(at):
    # In Madrid it is already the 3rd; in the business, still the 2nd.
    at(BOGOTA_NIGHT)
    assert refused(issue_date="2026-11-03").code == "invoice.issue_date_in_future"
    assert manual(issue_date="2026-11-02").issue_date == dt.date(2026, 11, 2)


def test_a_day_before_the_last_invoice_of_its_series_is_refused_and_says_which(at):
    at(NOON)
    manual()
    error = refused(issue_date="2026-11-23")
    assert (error.code, set(error.fields)) == ("invoice.issue_date_before_last", {"issue_date"})
    assert "11/24/2026" in str(error)


def test_the_day_of_the_last_invoice_of_its_series_is_accepted(at):
    at(NOON)
    manual(issue_date="2026-11-23")
    again = manual(issue_date="2026-11-23")
    assert (again.issue_date, again.number) == (YESTERDAY, "FACT-2026-000002")


def test_the_last_invoice_is_the_one_with_the_last_number(at):
    # A book that came out of order (a business that changed its time zone) is measured by its last number.
    at(NOON)
    first, second = manual(), manual()
    Invoice.objects.filter(pk=first.id).update(issue_date=TODAY)
    Invoice.objects.filter(pk=second.id).update(issue_date=YESTERDAY)
    assert manual(issue_date="2026-11-23").issue_date == YESTERDAY


def test_the_order_is_of_each_series(at):
    at(NOON)
    run("invoice.invoice.create", {"series_code": "TICKET", "lines": [LINE]})
    assert manual(issue_date="2026-11-23").issue_date == YESTERDAY


def test_a_day_of_last_year_is_numbered_in_that_year_s_series(at):
    at(NEW_YEAR)
    december = manual(issue_date="2026-12-31")
    january = manual()
    assert (december.number, december.year) == ("FACT-2026-000001", 2026)
    assert (january.number, january.year) == ("FACT-2027-000001", 2027)


def test_a_series_of_another_year_than_the_date_is_refused(at):
    at(NEW_YEAR)
    this_year = run("invoice.series.create", {"code": "SHOP", "invoice_type": "F1", "year": 2027})
    error = refused(series_id=str(this_year.id), issue_date="2026-12-31")
    assert (error.code, set(error.fields)) == ("invoice.series_other_year", {"series_id"})
    assert manual(series_id=str(this_year.id), issue_date="2027-01-01").number == "SHOP-2027-000001"


def test_a_year_no_series_numbers_is_refused_before_anything_is_issued(at):
    at(NOON)
    with pytest.raises(ValidationError) as error:
        manual(issue_date="1999-12-31")
    assert fields(error.value) == {"issue_date"}
    assert manual(issue_date="2000-01-01").number == "FACT-2000-000001"


def test_a_line_s_tax_category_takes_the_rule_in_force_on_the_day_chosen(at):
    at(NOON)
    current = run("tax.rule.list", {"tax_category_key": "product.generic"}).rows
    [rule] = [row for row in current if row.region_code is None and row.country_code == "ES"]
    run("tax.rule.end", {"id": str(rule.id), "valid_to": "2026-11-23"})
    run(
        "tax.rule.create",
        {"country_code": "ES", "tax_category_key": "product.generic", "rate_pct": "22", "valid_from": "2026-11-24"},
    )
    line = {"description": "Kit", "quantity": "1", "unit_price": 1000, "tax_category_key": "product.generic"}
    assert [entry.rate for entry in manual(lines=[line], issue_date="2026-11-23").tax_breakdown] == [21]
    assert [entry.rate for entry in manual(lines=[line]).tax_breakdown] == [22]


# What VeriFactu declares


def test_the_record_declares_the_day_chosen_as_the_issue_date_and_no_other_operation_date(at):
    # The tax agency takes no issue date before the operation date, nor a future one.
    at(NOON)
    record = Record.objects.get(invoice_id=manual(issue_date="2026-11-23").id)
    assert (record.issue_date, record.operation_date) == (YESTERDAY, None)
    assert record.xml.count("<sum1:FechaExpedicionFactura>23-11-2026</sum1:FechaExpedicionFactura>") == 1
    assert "FechaOperacion" not in record.xml
    assert "2026-11-24T12:00:00+01:00" in record.xml


def test_the_chain_follows_the_order_the_records_are_made_in_whatever_day_they_are_dated(at):
    at(NOON)
    ticket = run("invoice.invoice.create", {"series_code": "TICKET", "lines": [LINE]})
    dated_before = manual(issue_date="2026-11-23")
    dated_today = manual()
    first, second, third = (Record.objects.get(invoice_id=answer.id) for answer in (ticket, dated_before, dated_today))
    assert (second.previous_number, second.previous_issue_date) == (ticket.number, TODAY)
    assert second.previous_fingerprint == first.fingerprint
    assert (third.previous_number, third.previous_issue_date) == (dated_before.number, YESTERDAY)
    assert third.previous_fingerprint == second.fingerprint
    assert first.sequence < second.sequence < third.sequence


def test_a_rectification_names_the_invoice_by_the_day_it_is_dated(at):
    at(NOON)
    original = manual(issue_date="2026-11-23")
    rectification = run("invoice.invoice.rectify", {"invoice_id": str(original.id), "reason": "Wrong price"})
    record = Record.objects.get(invoice_id=rectification.invoice.id)
    assert (record.issue_date, record.operation_date) == (TODAY, YESTERDAY)
    assert re.findall(r"<sum1:FechaExpedicionFactura>([\d-]+)<", record.xml) == [
        "24-11-2026",
        "23-11-2026",
        "23-11-2026",
    ]


# The day it falls due


def test_the_due_date_is_kept_with_the_invoice_and_declared_nowhere(at):
    at(NOON)
    answer = manual(due_date="2026-12-24")
    assert (answer.due_date, stored(answer).due_date) == (dt.date(2026, 12, 24), dt.date(2026, 12, 24))
    assert "24-12-2026" not in Record.objects.get(invoice_id=answer.id).xml
    page = run("invoice.invoice.list", {})
    assert [row.due_date for row in page.rows] == [dt.date(2026, 12, 24)]


@pytest.mark.parametrize("data", [{}, {"due_date": None}])
def test_an_invoice_needs_no_due_date(at, data):
    at(NOON)
    assert manual(**data).due_date is None


def test_a_due_date_before_the_invoice_s_is_refused_under_its_field(at):
    at(NOON)
    error = refused(issue_date="2026-11-23", due_date="2026-11-22")
    assert (error.code, set(error.fields)) == ("invoice.due_date_before_issue", {"due_date"})
    assert refused(due_date="2026-11-23").code == "invoice.due_date_before_issue"


def test_an_invoice_may_fall_due_the_day_it_is_dated(at):
    at(NOON)
    assert manual(due_date="2026-11-24").due_date == TODAY


def test_the_full_invoice_that_replaces_a_ticket_keeps_its_due_date(at):
    at(NOON)
    ticket = run("invoice.invoice.create", {"series_code": "TICKET", "lines": [LINE], "due_date": "2026-12-24"})
    full = run("invoice.invoice.substitute", {"number": ticket.number, **RECIPIENT}).invoice
    assert (full.invoice_type, full.due_date) == ("F3", dt.date(2026, 12, 24))


@pytest.mark.parametrize(("language", "label", "day"), [("en", "Due date", "12/24/2026"), ("es", "Vencimiento", "24/12/2026")])
def test_the_printed_document_says_when_it_falls_due_only_if_it_does(at, language, label, day):
    from apps.invoice.tests.conftest import ctx_for

    at(NOON)

    def page(answer) -> str:
        return run("invoice.invoice.document", {"invoice_id": str(answer.id)}, ctx_for(language=language)).html

    html = page(manual(due_date="2026-12-24"))
    assert f'<span class="k">{label}</span><span class="v">{day}</span>' in html
    assert label not in page(manual())
