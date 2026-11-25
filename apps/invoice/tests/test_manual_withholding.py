"""The IRPF withholding of a manual invoice (INVOICE-F03): chosen from a closed list, over the whole base, it takes from what
is collected and changes nothing of the invoice nor of what VeriFactu declares. The records are sealed in VeriFactu's
testing environment and never sent: nothing here leaves the machine."""

import contextlib
import datetime as dt
import re
from decimal import Decimal

import pytest
from live.errors import Conflict
from live.operations import atomic
from pydantic import ValidationError

from apps.invoice.models import Invoice, InvoiceSeries
from apps.invoice.tests.conftest import HUB_DB, ctx_for, fields, run
from apps.invoice.tests.manual import LINE, RECIPIENT, manual
from apps.verifactu.models import Record

pytestmark = [HUB_DB, pytest.mark.usefixtures("issuer", "nothing_leaves")]

NOON = ("Europe/Madrid", dt.datetime(2026, 11, 24, 11, 0, tzinfo=dt.UTC))
HUNDRED = {**LINE, "unit_price": 10000}


def line(price: int, rate="21", **more) -> dict:
    return {**LINE, "unit_price": price, "tax_rate": rate, **more}


def withheld(rate=15, *lines, **more):
    """An invoice of 100 € + 21 % VAT with that withholding, unless ``lines`` say another thing."""
    return manual(lines=list(lines) or [HUNDRED], withholding_rate=rate, **more)


def stored(answer) -> Invoice:
    return Invoice.objects.get(pk=answer.id)


def figures(answer) -> tuple[int, int, int]:
    return answer.base_amount, answer.tax_amount, answer.total_amount


def to_collect(answer) -> tuple:
    return answer.withholding_rate, answer.withholding_amount, answer.payable_amount


# What it takes and what it leaves as it was


def test_it_takes_from_what_is_collected_and_changes_nothing_of_the_invoice():
    answer = withheld(15)
    assert figures(answer) == (10000, 2100, 12100)
    assert to_collect(answer) == (Decimal("15.00"), 1500, 10600)
    invoice = stored(answer)
    assert (invoice.withholding_rate, invoice.withholding_amount, invoice.payable_amount) == (Decimal("15.00"), 1500, 10600)
    assert invoice.total_amount == 12100


@pytest.mark.parametrize(("rate", "amount"), [(15, 1500), (7, 700), (1, 100), (19, 1900)])
def test_every_rate_of_the_list(rate, amount):
    assert to_collect(withheld(rate)) == (Decimal(rate), amount, 12100 - amount)


@pytest.mark.parametrize("data", [{}, {"withholding_rate": None}])
def test_an_invoice_without_it_collects_its_total(data):
    answer = manual(lines=[HUNDRED], **data)
    assert to_collect(answer) == (None, 0, 12100)


@pytest.mark.parametrize("rate", [0, 2, 24, 15.5, -15, 100, "15 %", True])
def test_another_rate_is_refused_under_its_field(rate):
    with pytest.raises(ValidationError) as error:
        withheld(rate)
    assert fields(error.value) == {"withholding_rate"}
    assert not Invoice.objects.exists()


def test_it_is_worked_out_over_the_whole_base_and_rounded_once():
    # Three rates and an exempt-like 0 %: 0.10 + 0.10 + 0.10 = 0.30 €; 15 % of each would be 0.02 three times.
    answer = withheld(15, line(10, "21"), line(10, "10"), line(10, "4"))
    assert answer.base_amount == 30
    assert answer.withholding_amount == 5


def test_a_line_exempt_from_vat_is_withheld_too():
    answer = withheld(15, line(10000, "0"), line(10000, "21"))
    assert (answer.base_amount, answer.tax_amount, answer.withholding_amount) == (20000, 2100, 3000)


def test_the_equivalence_surcharge_is_collected_and_never_withheld(equivalence_surcharge):
    answer = withheld(15, {**HUNDRED, "tax_rate": None, "tax_category_key": "product.generic"})
    assert figures(answer) == (10000, 2620, 12620)
    assert to_collect(answer) == (Decimal("15.00"), 1500, 11120)


# Who does not carry it


def test_a_ticket_issued_by_hand_is_refused_under_its_field_and_spends_no_number():
    before = sum(InvoiceSeries.objects.values_list("current_number", flat=True))
    with pytest.raises(Conflict) as refused:
        run("invoice.invoice.create", {"series_code": "TICKET", "lines": [LINE], "withholding_rate": 15})
    assert (refused.value.code, set(refused.value.fields)) == ("invoice.withholding_on_ticket", {"withholding_rate"})
    assert not Invoice.objects.exists()
    assert sum(InvoiceSeries.objects.values_list("current_number", flat=True)) == before


def test_a_ticket_without_it_is_issued_as_ever():
    ticket = run("invoice.invoice.create", {"series_code": "TICKET", "lines": [LINE]})
    assert to_collect(ticket) == (None, 0, 1210)


def test_the_documents_of_the_till_never_carry_it(product, charge):
    product()
    charge("inv-wh-0001")
    ticket = Invoice.objects.get(source_type="sale")
    full = run("invoice.invoice.substitute", {"number": ticket.number, **RECIPIENT}).invoice
    for document in (ticket, stored(full)):
        assert (document.withholding_rate, document.withholding_amount) == (None, 0)
        assert document.payable_amount == document.total_amount


# The rectifying invoice


def test_rectifying_it_carries_it_in_negative():
    original = withheld(15)
    rectification = run("invoice.invoice.rectify", {"number": original.number, "reason": "Wrong price"}).invoice
    assert figures(rectification) == (-10000, -2100, -12100)
    assert to_collect(rectification) == (Decimal("15.00"), -1500, -10600)
    both = [stored(original), stored(rectification)]
    assert sum(document.payable_amount for document in both) == 0
    assert both[0].withholding_amount == 1500


def test_rectifying_an_invoice_without_it_carries_none():
    original = manual(lines=[HUNDRED])
    rectification = run("invoice.invoice.rectify", {"number": original.number, "reason": "Wrong price"}).invoice
    assert to_collect(rectification) == (None, 0, -12100)


def test_the_preview_of_the_rectification_says_what_it_gives_back():
    original = withheld(15)
    data = {"number": original.number, "reason": "Wrong price"}
    preview = run("invoice.invoice.rectification_preview", data)
    assert to_collect(preview) == (Decimal("15.00"), -1500, -10600)
    assert to_collect(run("invoice.invoice.rectify", data).invoice) == to_collect(preview)


# What VeriFactu declares


def record_of(answer) -> dict:
    """Everything VeriFactu keeps and prints of a document: its record's columns, its XML, its fingerprint and its QR."""
    record = Record.objects.get(invoice_id=answer.id)
    kept = {
        field.attname: getattr(record, field.attname)
        for field in Record._meta.concrete_fields
        if field.attname not in ("id", "invoice_id")
    }
    qr = run("verifactu.record.by_invoice", {"invoice_id": str(answer.id)}).record
    return {**kept, "qr_url": qr.qr_url, "qr_svg": qr.qr_svg}


class Undo(Exception):
    """Takes back what a block issued."""


def undone(issue) -> dict:
    """The record of what ``issue()`` issues, taken back afterwards: the next document gets the same number, the same
    place in the chain and the same clock."""
    record: dict = {}
    with contextlib.suppress(Undo), atomic():
        record = record_of(issue())
        raise Undo
    assert not Record.objects.exists()
    return record


def test_the_record_of_an_invoice_is_the_same_with_it_and_without_it(at):
    at(NOON)
    plain = undone(lambda: manual(lines=[HUNDRED, line(3333, "10")]))
    assert not Invoice.objects.exists()
    carried = undone(lambda: withheld(15, HUNDRED, line(3333, "10")))
    assert carried == plain
    # What is compared is the record in full: the amount, the chain and the QR are in it.
    assert plain["total_amount"] == 15766
    assert re.findall(r"<sum1:ImporteTotal>([^<]+)<", plain["xml"]) == ["157.66"]
    assert len(plain["fingerprint"]) == 64
    assert "importe=157.66" in plain["qr_url"]


def test_the_record_of_its_rectification_is_the_same_too(at):
    at(NOON)

    def rectified(**more):
        original = manual(lines=[HUNDRED], **more)
        return run("invoice.invoice.rectify", {"number": original.number, "reason": "Wrong price"}).invoice

    plain = undone(rectified)
    assert undone(lambda: rectified(withholding_rate=15)) == plain
    assert plain["total_amount"] == -12100


# What a person reads


@pytest.mark.parametrize(
    ("language", "label", "amount", "due", "payable"),
    [
        ("en", "IRPF withholding 15%", "-€15.00", "Amount due", "€106.00"),
        ("es", "Retención IRPF 15\xa0%", "-15,00\xa0€", "A cobrar", "106,00\xa0€"),
    ],
)
def test_the_printed_document_says_it_after_its_total(language, label, amount, due, payable):
    def page(answer) -> str:
        return run("invoice.invoice.document", {"invoice_id": str(answer.id)}, ctx_for(language=language)).html

    html = page(withheld(15))
    assert f'<td class="muted">{label}</td><td class="num">{amount}</td>' in html
    assert f'<tr class="grand"><td>{due}</td><td class="num">{payable}</td></tr>' in html
    assert html.index("TOTAL") < html.index(label) < html.index(due)
    plain = page(manual(lines=[HUNDRED]))
    assert label not in plain
    assert due not in plain


def test_the_printed_rectification_says_it_in_negative():
    original = withheld(15)
    rectification = run("invoice.invoice.rectify", {"number": original.number, "reason": "Wrong price"}).invoice
    html = run("invoice.invoice.document", {"invoice_id": str(rectification.id)}).html
    assert "€15.00" in html
    assert "-€15.00" not in html
    assert "-€106.00" in html


def test_reading_it_again_says_the_same():
    answer = withheld(19)
    assert to_collect(run("invoice.invoice.get", {"number": answer.number})) == (Decimal("19.00"), 1900, 10200)


def test_marking_it_paid_moves_none_of_its_figures():
    answer = withheld(15)
    paid = run("invoice.invoice.mark_paid", {"number": answer.number})
    assert (paid.status, figures(paid), to_collect(paid)) == ("paid", figures(answer), to_collect(answer))
