"""When an invoice is overdue (INVOICE-F16): issued, not paid, and its due date has passed on the business's clock."""

import base64
import datetime as dt
import io

import pytest
from openpyxl import load_workbook

from apps.invoice.models import Invoice
from apps.invoice.tests.conftest import HUB_DB, ctx_for, run
from apps.invoice.tests.manual import LINE, RECIPIENT, manual

pytestmark = [HUB_DB, pytest.mark.usefixtures("issuer", "nothing_leaves")]

ZONE = "Europe/Madrid"
#: The day every invoice here is issued, and the day they fall due.
ISSUED = (ZONE, dt.datetime(2026, 11, 1, 11, 0, tzinfo=dt.UTC))
DUE = "2026-11-24"
ON_ITS_DAY = (ZONE, dt.datetime(2026, 11, 24, 22, 30, tzinfo=dt.UTC))
#: 00:30 of the 25th in Madrid, still the 24th in UTC and in the Canary Islands.
NEXT_DAY = dt.datetime(2026, 11, 24, 23, 30, tzinfo=dt.UTC)


def overdue_numbers(**filters) -> list[str]:
    return [row.number for row in run("invoice.invoice.list", {"status": "overdue", **filters}).rows]


def flag(answer) -> bool:
    """What the list and the invoice itself say of it, which is the same."""
    [row] = [row for row in run("invoice.invoice.list", {"limit": 100}).rows if row.id == answer.id]
    detail = run("invoice.invoice.get", {"invoice_id": str(answer.id)})
    assert row.overdue == detail.overdue
    return row.overdue


@pytest.fixture
def due(at):
    """An invoice issued on 1 November that falls due on the 24th."""
    at(ISSUED)
    return manual(due_date=DUE)


def test_it_is_not_overdue_on_its_due_day_and_it_is_the_day_after(due, at):
    at(ON_ITS_DAY)
    assert (flag(due), overdue_numbers()) == (False, [])
    at((ZONE, NEXT_DAY))
    assert (flag(due), overdue_numbers()) == (True, [due.number])


def test_the_day_changes_on_the_business_s_clock(due, at):
    at(("Atlantic/Canary", NEXT_DAY))
    assert (flag(due), overdue_numbers()) == (False, [])


def test_an_overdue_invoice_is_still_an_issued_one(due, at):
    at((ZONE, NEXT_DAY))
    [row] = run("invoice.invoice.list", {"status": "issued"}).rows
    assert (row.number, row.status, row.overdue, row.can_mark_paid) == (due.number, "issued", True, True)


def test_once_paid_it_is_not_overdue(due, at):
    at((ZONE, NEXT_DAY))
    paid = run("invoice.invoice.mark_paid", {"invoice_id": str(due.id)})
    assert (paid.overdue, flag(due), overdue_numbers()) == (False, False, [])


def test_once_rectified_it_is_not_overdue_nor_is_its_rectification(due, at):
    at((ZONE, NEXT_DAY))
    rectification = run("invoice.invoice.rectify", {"invoice_id": str(due.id), "reason": "Wrong price"}).invoice
    assert (flag(due), rectification.overdue, rectification.due_date, overdue_numbers()) == (False, False, None, [])


def test_without_a_due_date_it_is_never_overdue(at):
    at(ISSUED)
    invoice = manual()
    at((ZONE, NEXT_DAY))
    assert (flag(invoice), overdue_numbers()) == (False, [])


def test_a_replaced_ticket_is_not_overdue_but_the_invoice_that_replaced_it_is(at):
    at(ISSUED)
    ticket = run("invoice.invoice.create", {"series_code": "TICKET", "lines": [LINE], "due_date": DUE})
    full = run("invoice.invoice.substitute", {"number": ticket.number, **RECIPIENT}).invoice
    at((ZONE, NEXT_DAY))
    assert (flag(ticket), flag(full), overdue_numbers()) == (False, True, [full.number])


def test_the_filter_joins_the_others(due, at):
    at(ISSUED)
    other = manual(customer_name="Bar Pepe", customer_tax_id="12345678Z", due_date=DUE)
    at((ZONE, NEXT_DAY))
    assert overdue_numbers(search="Pepe") == [other.number]
    assert overdue_numbers(issue_date_to="2026-10-31") == []
    assert run("invoice.invoice.list", {"status": "overdue", "limit": 1}).total == 2


def test_the_excel_keeps_the_overdue_ones_as_the_list_does(due, at):
    at(ISSUED)
    manual()
    at((ZONE, NEXT_DAY))
    file = run("invoice.invoice.export", {"status": "overdue"})
    sheet = load_workbook(io.BytesIO(base64.b64decode(file.content_base64))).active
    assert [row[0].value for row in sheet.iter_rows(min_row=2)] == [due.number]
    assert file.invoices == 1


def test_someone_who_sees_only_theirs_filters_only_theirs(due, at):
    at((ZONE, NEXT_DAY))
    Invoice.objects.filter(pk=due.id).update(created_by="somebody-else")
    page = run("invoice.invoice.list", {"status": "overdue"}, ctx_for("hub_employee", actor="tester"))
    assert page.rows == []
