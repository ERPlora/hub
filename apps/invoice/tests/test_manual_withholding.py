"""The IRPF withholding of a manual invoice (INVOICE-F03): chosen from a closed list, over the whole base, it takes from what
is collected and changes nothing of the invoice. The records are sealed in VeriFactu's testing environment and never sent:
nothing here leaves the machine."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from apps.invoice.models import Invoice
from apps.invoice.tests.conftest import HUB_DB, fields, run
from apps.invoice.tests.manual import HUNDRED, LINE, RECIPIENT, line, manual, page, refused, stored, withheld

pytestmark = [HUB_DB, pytest.mark.usefixtures("issuer", "nothing_leaves")]


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


@pytest.mark.parametrize("rate", [0, 2, 24, 15.5, -15, 100, "15 %"])
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
    error = refused(series_code="TICKET", withholding_rate=15)
    assert (error.code, set(error.fields)) == ("invoice.withholding_on_ticket", {"withholding_rate"})


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


# What a person reads


@pytest.mark.parametrize(
    ("language", "label", "amount", "due", "payable"),
    [
        ("en", "IRPF withholding 15%", "-€15.00", "Amount due", "€106.00"),
        ("es", "Retención IRPF 15\xa0%", "-15,00\xa0€", "A cobrar", "106,00\xa0€"),
    ],
)
def test_the_printed_document_says_it_after_its_total(language, label, amount, due, payable):
    html = page(withheld(15), language)
    assert f'<td class="muted">{label}</td><td class="num">{amount}</td>' in html
    assert f'<tr class="grand"><td>{due}</td><td class="num">{payable}</td></tr>' in html
    assert html.index("TOTAL") < html.index(label) < html.index(due)
    plain = page(manual(lines=[HUNDRED]), language)
    assert label not in plain
    assert due not in plain


def test_the_printed_rectification_says_it_in_negative():
    original = withheld(15)
    rectification = run("invoice.invoice.rectify", {"number": original.number, "reason": "Wrong price"}).invoice
    html = page(rectification)
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
