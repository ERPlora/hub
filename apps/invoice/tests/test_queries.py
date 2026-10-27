"""Read operations of the invoice app (INVOICE-F14–F18, F20): the lists, the detail, the printable
document, the series and their next number, the state of the numbering, its gaps and its book.

Cases from the current product's tests: ``invoice_search_says_what_it_searches``, ``number_format``
(the preview equals what the emission writes), ``setup_numbering`` and ``number_allocation``.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.utils import timezone
from live.errors import Conflict, NotFound, PermissionDenied

from apps.invoice.models import Invoice, InvoiceSeries
from apps.invoice.tests.conftest import ctx_for, run

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()
RECIPIENT = {
    "customer_name": "Talleres Pérez SL",
    "customer_tax_id": "B12345674",
    "customer_address": "Calle Luna 3",
}


def manual(price=1000, rate="21", **more):
    data = {
        "lines": [
            {
                "description": "Service",
                "quantity": "1",
                "unit_price": price,
                "tax_rate": rate,
            }
        ],
        **RECIPIENT,
        **more,
    }
    return run("invoice.invoice.create", data)


def ticket(price=150):
    return run(
        "invoice.invoice.create",
        {
            "series_code": "TICKET",
            "lines": [
                {
                    "description": "Coffee",
                    "quantity": "1",
                    "unit_price": price,
                    "tax_rate": "10",
                }
            ],
        },
    )


def numbers(page):
    return [row.number for row in page.rows]


# The list (INVOICE-F16)


def test_the_last_issued_comes_first_and_the_list_pages_by_up_to_a_hundred(issuer):
    first, second, third = manual(), manual(), ticket()
    page = run("invoice.invoice.list", {"limit": 2}, ctx_for("hub_employee"))
    assert (numbers(page), page.total, page.limit, page.offset) == (
        [third.number, second.number],
        3,
        2,
        0,
    )
    assert numbers(run("invoice.invoice.list", {"limit": 2, "offset": 2})) == [
        first.number
    ]


def test_the_search_finds_by_number_customer_name_or_tax_id(issuer):
    full = manual()
    other = manual(customer_name="Bar Pepe", customer_tax_id="12345678Z")
    ticket()
    assert numbers(run("invoice.invoice.list", {"search": full.number.lower()})) == [
        full.number
    ]
    assert numbers(run("invoice.invoice.list", {"search": "pepe"})) == [other.number]
    assert numbers(run("invoice.invoice.list", {"search": "12345678z"})) == [
        other.number
    ]


def test_the_filters_and_the_sort(issuer):
    small, big = manual(price=1000), manual(price=90000)
    simplified = ticket()
    assert numbers(run("invoice.invoice.list", {"invoice_type": "F2"})) == [
        simplified.number
    ]
    assert numbers(
        run(
            "invoice.invoice.list",
            {"series_code": "FACT", "sort": "number", "dir": "asc"},
        )
    ) == [small.number, big.number]
    assert numbers(run("invoice.invoice.list", {"total_amount_from": 50000})) == [
        big.number
    ]
    assert numbers(
        run("invoice.invoice.list", {"total_amount_to": 1210, "invoice_type": "F1"})
    ) == [small.number]
    assert numbers(
        run("invoice.invoice.list", {"sort": "total_amount", "dir": "desc", "limit": 1})
    ) == [big.number]
    assert (
        run(
            "invoice.invoice.list",
            {"issue_date_from": str(TODAY), "issue_date_to": str(TODAY)},
        ).total
        == 3
    )
    assert (
        run(
            "invoice.invoice.list", {"issue_date_to": str(TODAY - dt.timedelta(days=1))}
        ).total
        == 0
    )
    run("invoice.invoice.mark_paid", {"number": small.number})
    assert numbers(run("invoice.invoice.list", {"status": "paid"})) == [small.number]
    assert numbers(
        run(
            "invoice.invoice.list",
            {"source_type": "manual", "status": "issued", "invoice_type": "F1"},
        )
    ) == [big.number]


def test_each_row_says_what_can_still_be_done(issuer):
    full = manual()
    rect = run(
        "invoice.invoice.rectify", {"number": full.number, "reason": "x"}
    ).invoice
    simplified = ticket()
    rows = {row.number: row for row in run("invoice.invoice.list", {}).rows}
    assert (
        rows[full.number].status,
        rows[full.number].can_rectify,
        rows[full.number].can_mark_paid,
    ) == ("cancelled", False, False)
    assert (
        rows[rect.number].can_rectify,
        rows[rect.number].can_mark_paid,
        rows[rect.number].rectifies_number,
    ) == (False, False, full.number)
    assert (
        rows[simplified.number].can_rectify,
        rows[simplified.number].can_mark_paid,
        rows[simplified.number].can_substitute,
    ) == (True, True, True)


# The detail (INVOICE-F17)


def test_an_invoice_is_read_by_its_id_or_its_number_with_its_links(issuer):
    simplified = ticket()
    full = run(
        "invoice.invoice.substitute", {"number": simplified.number, **RECIPIENT}
    ).invoice
    rect = run(
        "invoice.invoice.rectify", {"number": full.number, "reason": "Wrong"}
    ).invoice
    read = run("invoice.invoice.get", {"number": full.number}, ctx_for("hub_employee"))
    assert (
        read.substitutes.number,
        read.rectifications[0].number,
        read.remaining,
        read.status,
    ) == (simplified.number, rect.number, 0, "cancelled")
    by_id = run("invoice.invoice.get", {"invoice_id": str(simplified.id)})
    assert (by_id.substituted, by_id.substituted_by.number) == (True, full.number)
    with pytest.raises(NotFound):
        run("invoice.invoice.get", {"number": "FACT-1999-000001"})


# The document of a sale (INVOICE-F20) is in test_integration_sale.py.


def test_a_sale_without_its_invoice_answers_none(issuer):
    from apps.sale.models import Sale

    sale = Sale.objects.create(
        number="20261014-0099", business_day=TODAY, sequence=99, idempotency_key="k-99"
    )
    answer = run("invoice.invoice.by_source", {"sale": sale.number})
    assert (answer.found, answer.invoice) == (False, None)
    with pytest.raises(NotFound):
        run("invoice.invoice.by_source", {"sale": "19990101-0001"})


# The printable document (INVOICE-F18)


def test_the_document_is_the_a4_invoice_in_the_readers_language(issuer):
    invoice = manual()
    english = run("invoice.invoice.document", {"number": invoice.number}).html
    assert (
        invoice.number in english
        and "Peluquería Ana SL" in english
        and "Talleres Pérez SL" in english
    )
    assert "Invoice" in english and "Bill to" in english and "VAT 21%" in english
    spanish = run(
        "invoice.invoice.document",
        {"number": invoice.number, "duplicate": True},
        ctx_for(language="es"),
    ).html
    assert (
        "Factura" in spanish
        and "Facturar a" in spanish
        and "IVA 21" in spanish
        and "Copia" in spanish
    )
    assert "12,10" in spanish


def test_the_document_says_what_it_is_and_what_it_rectifies(issuer):
    simplified = ticket()
    assert (
        "Simplified invoice"
        in run("invoice.invoice.document", {"number": simplified.number}).html
    )
    rect = run(
        "invoice.invoice.rectify",
        {"number": simplified.number, "reason": "Spilt coffee"},
    ).invoice
    html = run("invoice.invoice.document", {"number": rect.number}).html
    assert "Rectifying invoice" in html
    assert f"Rectifies invoice {simplified.number}. Reason: Spilt coffee" in html


# Series (INVOICE-F12, F13)


def test_a_series_locks_with_its_first_document_not_with_its_counter(issuer):
    run(
        "invoice.series.create",
        {"code": "SHOP", "invoice_type": "F1", "year": TODAY.year, "next_number": 7},
    )

    def shop():
        rows = run("invoice.series.list", {"code": "SHOP"}).rows
        peek = run("invoice.series.peek_next", {"code": "SHOP", "year": TODAY.year})
        return rows[0].current_number, rows[0].format_locked, peek.format_locked

    assert shop() == (6, False, False)
    manual(series_code="SHOP")
    assert shop() == (7, True, True)


def test_the_series_list_says_each_ones_next_number(issuer):
    manual()
    run(
        "invoice.series.create",
        {
            "code": "SHOP",
            "invoice_type": "F1",
            "year": TODAY.year,
            "format": "S{year}-{seq:03d}",
        },
    )
    page = run(
        "invoice.series.list", {"sort": "code", "dir": "asc"}, ctx_for("hub_employee")
    )
    rows = {row.code: row for row in page.rows}
    assert (
        rows["FACT"].current_number,
        rows["FACT"].next_number,
        rows["FACT"].format_locked,
    ) == (1, f"FACT-{TODAY.year}-000002", True)
    assert (rows["SHOP"].next_number, rows["SHOP"].format_locked) == (
        f"S{TODAY.year}-001",
        False,
    )
    assert [row.code for row in run("invoice.series.list", {"search": "sho"}).rows] == [
        "SHOP"
    ]
    assert [
        row.code
        for row in run(
            "invoice.series.list", {"invoice_type": "F1", "sort": "code", "dir": "asc"}
        ).rows
    ] == ["FACT", "SHOP"]


def test_the_next_number_previewed_is_the_one_the_emission_writes(issuer):
    series = run(
        "invoice.series.create",
        {
            "code": "FACT",
            "invoice_type": "F1",
            "year": TODAY.year,
            "format": "VFT{year}-A-{seq:04d}",
        },
    )
    peek = run("invoice.series.peek_next", {"series_id": str(series.id)})
    assert (peek.next_sequence, peek.next_number, peek.format_locked) == (
        1,
        f"VFT{TODAY.year}-A-0001",
        False,
    )
    assert manual().number == peek.next_number
    again = run("invoice.series.peek_next", {"code": "fact"})
    assert (again.next_number, again.format_locked) == (f"VFT{TODAY.year}-A-0002", True)
    # Peeking spends nothing.
    assert InvoiceSeries.objects.get(pk=series.id).current_number == 1


# The preview of a rectification (INVOICE-F08: what the assistant says before the card of a rectification)


def preview(ctx=None, **data):
    return run("invoice.invoice.rectification_preview", data, ctx)


def test_the_preview_is_the_rectifying_invoice_that_would_be_born_and_takes_no_number(
    issuer,
):
    original = manual(
        lines=[
            {"description": "Course", "quantity": "2", "unit_price": 5000, "tax_rate": "21"},
            {"description": "Book", "quantity": "1", "unit_price": 2000, "tax_rate": "4"},
        ]
    )
    seen = preview(number=original.number, reason="The price was wrong")
    told = seen.original
    assert (told.invoice_id, told.number, told.issue_date, told.customer_name) == (
        original.id,
        original.number,
        TODAY,
        "Talleres Pérez SL",
    )
    assert (told.total_amount, told.remaining) == (14180, 14180)
    assert (
        seen.invoice_type,
        seen.reason,
        seen.series_code,
        seen.next_number,
        seen.issue_date,
        seen.whole,
    ) == ("R1", "The price was wrong", "RECT", f"RECT-{TODAY.year}-000001", TODAY, True)
    assert (seen.base_amount, seen.tax_amount, seen.total_amount, seen.currency) == (
        -12000,
        -2180,
        -14180,
        "EUR",
    )
    assert [
        (line.description, line.quantity, line.tax_rate, line.base_amount, line.total_amount)
        for line in seen.lines
    ] == [
        ("Course", Decimal("-2.000"), Decimal("21.00"), -10000, -12100),
        ("Book", Decimal("-1.000"), Decimal("4.00"), -2000, -2080),
    ]
    # Numbering is never optimistic: reading it creates no series, spends no number and leaves the original as it was.
    assert not InvoiceSeries.objects.filter(code="RECT").exists()
    assert Invoice.objects.get(pk=original.id).status == "issued"
    # What it said is what rectifying that invoice writes.
    rect = run(
        "invoice.invoice.rectify", {"number": told.number, "reason": seen.reason}
    ).invoice
    assert (rect.number, rect.invoice_type, rect.base_amount, rect.tax_amount, rect.total_amount) == (
        seen.next_number,
        "R1",
        -12000,
        -2180,
        -14180,
    )
    assert [(line.description, line.quantity, line.total_amount) for line in rect.lines] == [
        (line.description, line.quantity, line.total_amount) for line in seen.lines
    ]


def test_the_number_previewed_is_the_next_of_the_series_the_rectification_will_take(
    issuer,
):
    # Last year's rectifying series has its own format: this year's is born from it when the first one is issued.
    run(
        "invoice.series.create",
        {"code": "RECT", "invoice_type": "R1", "year": TODAY.year - 1, "format": "R{year}-{seq:04d}"},
    )
    first, second = manual(), manual()
    seen = preview(number=first.number, reason="x")
    assert seen.next_number == f"R{TODAY.year}-0001"
    assert not InvoiceSeries.objects.filter(code="RECT", year=TODAY.year).exists()
    assert run("invoice.invoice.rectify", {"number": first.number, "reason": "x"}).invoice.number == seen.next_number
    # Read twice, it says the same next number and spends none.
    again = [preview(number=second.number, reason="y").next_number for _ in range(2)]
    assert again == [f"R{TODAY.year}-0002"] * 2
    assert InvoiceSeries.objects.get(code="RECT", year=TODAY.year).current_number == 1


def test_the_preview_says_the_type_chosen_and_a_ticket_is_always_r5(issuer):
    assert preview(number=manual().number, reason="x").invoice_type == "R1"
    assert preview(number=manual().number, reason="x", rectification_type="R4").invoice_type == "R4"
    assert preview(number=ticket().number, reason="x", rectification_type="R2").invoice_type == "R5"


def test_what_cannot_be_rectified_the_preview_says_why_and_spends_nothing(issuer):
    original = manual()
    rect = run("invoice.invoice.rectify", {"number": original.number, "reason": "x"}).invoice
    simplified = ticket()
    run("invoice.invoice.substitute", {"number": simplified.number, **RECIPIENT})
    for number, code in (
        (rect.number, "invoice.cannot_rectify_rectification"),
        (original.number, "invoice.already_cancelled"),
        (simplified.number, "invoice.substituted"),
    ):
        with pytest.raises(Conflict) as refused:
            preview(number=number, reason="again")
        assert refused.value.code == code
    with pytest.raises(NotFound):
        preview(number="NOPE-1", reason="x")
    assert InvoiceSeries.objects.get(code="RECT", year=TODAY.year).current_number == 1


def test_only_who_may_rectify_reads_the_preview(issuer):
    number = manual().number
    with pytest.raises(PermissionDenied):
        preview(ctx_for("hub_employee"), number=number, reason="x")
    assert preview(ctx_for("hub_manager"), number=number, reason="x").original.number == number


# The numbering (INVOICE-F14, F15)


def test_a_fresh_hub_is_not_set_up_and_the_ticket_series_alone_does_not_set_it_up(
    issuer,
):
    status = run("invoice.numbering.status", {})
    assert (status.fiscal_year, status.total_series, status.configured) == (
        TODAY.year,
        0,
        False,
    )
    ticket()
    status = run("invoice.numbering.status", {})
    assert (status.ordinary_series, status.rectifying_series, status.configured) == (
        1,
        0,
        False,
    )
    run(
        "invoice.series.create",
        {"code": "RECT", "invoice_type": "R1", "year": TODAY.year},
    )
    assert run("invoice.numbering.status", {}).configured is True


def test_last_years_series_do_not_set_up_this_year(db):
    run(
        "invoice.series.create",
        {"code": "FACT", "invoice_type": "F1", "year": TODAY.year - 1},
    )
    run(
        "invoice.series.create",
        {
            "code": "RECT",
            "invoice_type": "R1",
            "year": TODAY.year - 1,
            "is_default": True,
        },
    )
    status = run("invoice.numbering.status", {})
    assert (status.total_series, status.default_series, status.configured) == (
        2,
        0,
        False,
    )


def test_a_correlative_numbering_has_no_gaps_and_its_book_names_each_document(issuer):
    first, second = manual(), manual()
    simplified = ticket()
    assert run("invoice.numbering.gaps", {}).total == 0
    book = run("invoice.numbering.allocations", {})
    assert [(row.series_code, row.sequence, row.number) for row in book.rows] == [
        ("FACT", 1, first.number),
        ("FACT", 2, second.number),
        ("TICKET", 1, simplified.number),
    ]
    assert [
        row.number
        for row in run("invoice.numbering.allocations", {"search": "ticket"}).rows
    ] == [simplified.number]


def test_a_gap_says_its_series_where_it_starts_and_how_many_are_missing(issuer):
    manual()
    manual()
    series = InvoiceSeries.objects.get(code="FACT", year=TODAY.year)
    # A hole that no operation can make (the number and the document are written together): planted.
    third = Invoice.objects.order_by("sequence").last()
    Invoice.objects.filter(pk=third.pk).update(
        sequence=5, number=f"FACT-{TODAY.year}-000005"
    )
    series.current_number = 5
    series.save()
    gaps = run("invoice.numbering.gaps", {"code": "FACT"})
    assert [
        (
            gap.series_code,
            gap.year,
            gap.after_sequence,
            gap.missing_from,
            gap.next_recorded,
            gap.missing_count,
        )
        for gap in gaps.rows
    ] == [("FACT", TODAY.year, 1, 2, 5, 3)]


# The issuer (INVOICE-F21)


def test_the_issuer_reads_empty_until_set_up(db):
    empty = run("invoice.issuer.get", {}, ctx_for("hub_employee"))
    assert (empty.configured, empty.legal_name, empty.country) == (False, "", "ES")


def test_the_issuer_is_read_by_everyone_who_sees_invoices(issuer):
    read = run("invoice.issuer.get", {}, ctx_for("hub_employee"))
    assert (read.configured, read.tax_id, read.address_line) == (
        True,
        "B12345674",
        "Calle Mayor 1, 28001 Madrid (Madrid)",
    )


def test_nobody_without_the_permission_reads_the_invoices(issuer):
    from live.context import OperationContext

    from apps.invoice.tests.conftest import A

    nobody = OperationContext(scope=A, actor="x", permissions=frozenset())
    with pytest.raises(PermissionDenied):
        run("invoice.invoice.list", {}, nobody)


# What a typed line of a manual invoice starts with (INVOICE-F03, TAX-F11)


def regional_rule(region, category, rate, tax_type, **more):
    run(
        "tax.rule.create",
        {
            "country_code": "ES",
            "region_code": region,
            "tax_category_key": category,
            "rate_pct": rate,
            "tax_type": tax_type,
            **more,
        },
    )


def line_defaults(ctx=None):
    """The rate a typed line starts with, and the tax its rate column is named by (Taxes' settings, the one
    place that publishes the territory's tax: invoice republishes nothing of it, TAX-F11)."""
    defaults = run("invoice.invoice.line_defaults", {}, ctx)
    assert set(defaults.model_dump()) == {"tax_rate"}
    return run("tax.settings.get", {}, ctx).tax_kind, defaults.tax_rate


def test_a_typed_line_starts_at_the_general_vat_of_the_whole_country(db):
    # The peninsula does not change: VAT, at the general rate of the factory catalogue.
    assert line_defaults(ctx_for("hub_employee")) == ("vat", Decimal("21.00"))


@pytest.mark.parametrize(
    ("region", "tax"), [("ES-CN", "igic"), ("ES-CE", "ipsi"), ("ES-ML", "ipsi")]
)
def test_a_territory_without_its_own_rule_proposes_no_rate(db, region, tax):
    # The national 21 % VAT would be declared as IGIC or IPSI: nothing is proposed, the person types it.
    run("tax.settings.update", {"region_code": region})
    assert line_defaults() == (tax, None)


@pytest.mark.parametrize(
    ("region", "rate", "tax"), [("ES-CN", "7", "igic"), ("ES-ML", "4", "ipsi")]
)
def test_a_territory_proposes_the_general_rate_of_its_own_rule(db, region, rate, tax):
    regional_rule(region, "product.generic", rate, tax)
    run("tax.settings.update", {"region_code": region})
    assert line_defaults() == (tax, Decimal(rate))


def test_a_business_that_only_sells_services_proposes_their_general_rate(db):
    regional_rule("ES-CN", "service.generic", "7", "igic")
    run("tax.settings.update", {"region_code": "ES-CN"})
    assert line_defaults() == ("igic", Decimal("7.00"))


def test_an_exempt_general_rule_is_not_proposed_as_a_typed_rate(db):
    # A typed rate is declared subject: an exempt 0 % would be declared as taxed at 0 %.
    regional_rule(
        "ES-CN",
        "product.generic",
        "0",
        "igic",
        operation_class="exempt",
        exempt_reason="E1",
    )
    run("tax.settings.update", {"region_code": "ES-CN"})
    assert line_defaults() == ("igic", None)


def test_nobody_without_issuing_reads_what_a_typed_line_starts_with(db):
    from live.context import OperationContext

    from apps.invoice.tests.conftest import A

    viewer = OperationContext(
        scope=A, actor="x", permissions=frozenset({"invoice.view_invoice"})
    )
    with pytest.raises(PermissionDenied):
        run("invoice.invoice.line_defaults", {}, viewer)
