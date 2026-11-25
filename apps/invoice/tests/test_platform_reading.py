"""How ERPlora's own business reads the invoices erplora.com issued (INVOICE-F23): they come from erplora.com, already paid,
and nobody marks them as paid here. What is kept of them, and what the issue announces, stays as it was; an invoice made
by hand in that business, and every invoice of any other, reads as always.

ERPlora's own business is business A here, as in ``test_platform_invoices.py``: real VeriFactu, no mocks.
"""

import copy

import pytest
from live.models import OutboxEvent

from apps.invoice.models import Invoice
from apps.invoice.queries.platform_reading import source_of, status_of
from apps.invoice.tests.conftest import HUB_DB, run
from apps.invoice.tests.manual import manual
from apps.invoice.tests.test_platform import BODY, CREDIT_NOTE, line
from apps.invoice.tests.test_platform_invoices import code_of, issue, platform_hub
from apps.invoice.tests.test_platform_series import TICKET, credit_note

__all__ = ["platform_hub"]

THEIRS, NOTE = BODY["number"], CREDIT_NOTE["number"]


def partial_credit_note() -> dict:
    """A credit note of a part of the invoice: the rest of it stays collected."""
    cents = {"net_cents": -1000, "tax_cents": -210, "total_cents": -1210}
    return {**credit_note(), **cents, "lines": [line(**cents)]}


def read(number: str):
    return run("invoice.invoice.get", {"number": number})


def listed(**filters) -> list[str]:
    return [row.number for row in run("invoice.invoice.list", filters).rows]


# ── The rule ──────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("invoice_type", "status", "read_as"),
    [
        ("F1", "issued", "paid"),
        ("F2", "issued", "paid"),
        ("F1", "paid", "paid"),
        ("F1", "cancelled", "cancelled"),
        ("R1", "issued", "issued"),
        ("R5", "issued", "issued"),
    ],
)
def test_what_erplora_com_issued_is_collected_unless_it_was_credited(invoice_type, status, read_as):
    theirs = Invoice(platform_ref=BODY["id"], invoice_type=invoice_type, status=status)
    assert status_of(theirs) == read_as
    assert status_of(Invoice(invoice_type=invoice_type, status=status)) == status


@pytest.mark.parametrize("source", Invoice.Source.values)
def test_what_erplora_com_issued_comes_from_there_and_the_rest_from_where_it_was_born(source):
    assert source_of(Invoice(platform_ref=BODY["id"], source_type=source)) == "platform"
    assert source_of(Invoice(source_type=source)) == source


# ── The page and the list ─────────────────────────────────────────────────────────────────────────────────────────


@HUB_DB
def test_the_page_and_the_list_say_it_comes_from_erplora_com_already_paid(platform_hub):
    issue()
    issue(copy.deepcopy(TICKET))
    rows = run("invoice.invoice.list").rows
    assert {row.number for row in rows} == {THEIRS, TICKET["number"]}
    for row in rows:
        page = read(row.number)
        for said in (row, page):
            assert (said.source_type, said.status, said.can_mark_paid) == ("platform", "paid", False)
        assert page.paid_at is None


@HUB_DB
def test_its_credit_note_comes_from_there_too_and_links_to_an_invoice_that_stays_paid(platform_hub):
    issue()
    issue(partial_credit_note())
    note = read(NOTE)
    assert (note.source_type, note.status, note.can_mark_paid) == ("platform", "issued", False)
    assert (note.rectifies.number, note.rectifies.status) == (THEIRS, "paid")
    assert (read(THEIRS).status, read(THEIRS).can_mark_paid) == ("paid", False)


@HUB_DB
def test_a_credited_invoice_reads_cancelled(platform_hub):
    issue()
    issue(credit_note())
    assert (read(THEIRS).status, read(THEIRS).source_type) == ("cancelled", "platform")
    assert read(NOTE).rectifies.status == "cancelled"


@HUB_DB
def test_an_invoice_made_by_hand_in_that_business_reads_as_always(platform_hub):
    issue()
    own = read(manual().number)
    assert (own.source_type, own.status, own.can_mark_paid) == ("manual", "issued", True)
    paid = run("invoice.invoice.mark_paid", {"number": own.number})
    assert (paid.source_type, paid.status, paid.can_mark_paid) == ("manual", "paid", False)
    assert paid.paid_at is not None


# ── The list's filters and its order ──────────────────────────────────────────────────────────────────────────────


@HUB_DB
def test_the_status_filter_finds_each_invoice_under_the_status_it_reads(platform_hub):
    issue()
    issue(partial_credit_note())
    issue(copy.deepcopy(TICKET))
    pending, collected = manual(), manual()
    run("invoice.invoice.mark_paid", {"number": collected.number})
    assert set(listed(status="paid")) == {THEIRS, TICKET["number"], collected.number}
    assert set(listed(status="issued")) == {NOTE, pending.number}
    assert listed(status="overdue") == listed(status="cancelled") == []
    for status in ("paid", "issued"):
        assert {row.status for row in run("invoice.invoice.list", {"status": status}).rows} == {status}


@HUB_DB
def test_a_credited_invoice_is_found_among_the_cancelled_and_nowhere_else(platform_hub):
    issue()
    issue(credit_note())
    assert listed(status="cancelled") == [THEIRS]
    assert listed(status="paid") == []
    assert listed(status="issued") == [NOTE]


@HUB_DB
def test_the_source_filter_leaves_out_what_erplora_com_issued(platform_hub):
    issue()
    issue(partial_credit_note())
    own = manual()
    mine = run("invoice.invoice.rectify", {"number": own.number, "reason": "Wrong price"}).invoice
    assert listed(source_type="manual") == [own.number]
    assert listed(source_type="rectification") == [mine.number]
    assert set(listed(series_code="ERP") + listed(series_code="ERPR")) == {THEIRS, NOTE}


@HUB_DB
@pytest.mark.parametrize(("direction", "order"), [("asc", ["issued", "paid", "paid"]), ("desc", ["paid", "paid", "issued"])])
def test_the_list_sorts_by_the_status_it_shows(platform_hub, direction, order):
    collected = manual()
    run("invoice.invoice.mark_paid", {"number": collected.number})
    manual()
    issue()
    rows = run("invoice.invoice.list", {"sort": "status", "dir": direction}).rows
    assert [row.status for row in rows] == order


# ── Marking it as paid ────────────────────────────────────────────────────────────────────────────────────────────


@HUB_DB
@pytest.mark.parametrize("body", [BODY, TICKET], ids=["invoice", "simplified"])
def test_nobody_marks_it_as_paid(platform_hub, body):
    issue(copy.deepcopy(body))
    before = Invoice.objects.values().get()
    heard = OutboxEvent.objects.count()
    code = code_of(lambda: run("invoice.invoice.mark_paid", {"number": body["number"]}))
    assert code == "invoice.cannot_mark_paid"
    assert Invoice.objects.values().get() == before
    assert OutboxEvent.objects.count() == heard


# ── What does not change ──────────────────────────────────────────────────────────────────────────────────────────


@HUB_DB
def test_what_is_kept_and_what_the_issue_announces_stay_as_they_were(platform_hub):
    issue()
    issue(partial_credit_note())
    kept = dict(Invoice.objects.values_list("number", "source_type"))
    assert kept == {THEIRS: "manual", NOTE: "rectification"}
    assert set(Invoice.objects.values_list("status", "paid_at")) == {("issued", None)}
    told = {event.payload["number"]: event.payload for event in OutboxEvent.objects.filter(name="invoice.invoice.issued")}
    assert {number: payload["source_type"] for number, payload in told.items()} == kept
    assert {number: payload["source"]["type"] for number, payload in told.items()} == kept
