"""Write operations of the invoice app (INVOICE-F03, F05, F08, F19, F21, F22), run as the screens,
the assistant and the API run them. Numbering and series (INVOICE-F11–F13) are in ``test_services_series.py``;
the documents born of a sale, a refund or a void, in ``test_integration_sale.py``; two sessions at once, in
``test_concurrency.py``.

Cases from the current product's tests: ``create.hub``, ``mark_paid``, ``number_format``,
``number_allocation``, ``rectify_date``, ``rectify_lines``, ``rectify_note``, ``substitution_unique``,
``business_date`` and ``setup_numbering``.
"""

import datetime as dt
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.utils import translation
from live.context import system_context
from live.errors import Conflict, NotFound, OperationError, PermissionDenied
from live.models import OutboxEvent

from apps.invoice import services
from apps.invoice.models import Invoice, InvoiceSeries, Issuer
from apps.invoice.services import writes
from apps.invoice.tests.conftest import A, HUB_DB, ISSUER, ctx_for, run
from apps.sale.tests.test_integration_tax import where_rules_are_made

pytestmark = HUB_DB

MADRID = ZoneInfo("Europe/Madrid")
RECIPIENT = {
    "customer_name": "Talleres Pérez SL",
    "customer_tax_id": "B12345674",
    "customer_address": "Calle Luna 3, 28004 Madrid",
}


def manual(series_code=None, lines=None, **more):
    data = {
        "lines": lines
        or [
            {
                "description": "Haircut course",
                "quantity": "2",
                "unit_price": 5000,
                "tax_rate": "21",
            }
        ],
        **({"series_code": series_code} if series_code else {}),
        **RECIPIENT,
        **more,
    }
    return run("invoice.invoice.create", data)


def events(name):
    return list(OutboxEvent.objects.filter(name=name).order_by("created_at", "id"))


def at(monkeypatch, moment: dt.datetime):
    """Moves the clock the operations read (the business day follows Madrid), in every module of the writes that
    reads it."""
    clock = writes._now
    for module in vars(services).values():
        if getattr(module, "_now", None) is clock:
            monkeypatch.setattr(module, "_now", lambda: moment)


# ── The issuer (INVOICE-F21, F22) ───────────────────────────────────────────────────────────────


def test_without_an_issuer_nothing_is_issued_and_no_number_is_used(db):
    with pytest.raises(Conflict) as refused:
        manual()
    assert refused.value.code == "invoice.issuer_missing"
    assert Invoice.objects.count() == 0
    assert not InvoiceSeries.objects.filter(current_number__gt=0).exists()


def test_the_owner_sets_up_the_issuer(db):
    issuer = run("invoice.issuer.update", ISSUER)
    assert (issuer.configured, issuer.source, issuer.address_line) == (
        True,
        "manual",
        "Calle Mayor 1, 28001 Madrid (Madrid)",
    )
    assert events("invoice.issuer.updated")[-1].payload == {"source": "manual"}
    again = run(
        "invoice.issuer.update", {**ISSUER, "legal_name": "Peluquería Ana y Luis SL"}
    )
    assert again.legal_name == "Peluquería Ana y Luis SL"
    assert Issuer.objects.count() == 1


def test_the_manager_cannot_change_the_issuer(db):
    with pytest.raises(PermissionDenied):
        run("invoice.issuer.update", ISSUER, ctx_for("hub_manager"))


def test_the_saas_photo_fills_the_issuer_and_an_older_one_is_ignored(db):
    with pytest.raises(PermissionDenied):
        run("invoice.issuer.sync", {**ISSUER, "version": 3}, ctx_for("hub_owner"))
    synced = run("invoice.issuer.sync", {**ISSUER, "version": 3}, system_context(A))
    assert (synced.applied, synced.issuer.source, synced.issuer.synced_version) == (
        True,
        "saas",
        3,
    )
    older = run(
        "invoice.issuer.sync",
        {**ISSUER, "legal_name": "Old SL", "version": 2},
        system_context(A),
    )
    assert (older.applied, older.issuer.legal_name) == (False, "Peluquería Ana SL")
    # The same version again (the SaaS pushes its photo once more) changes nothing either.
    same = run(
        "invoice.issuer.sync",
        {**ISSUER, "legal_name": "Same SL", "version": 3},
        system_context(A),
    )
    assert (same.applied, same.issuer.legal_name) == (False, "Peluquería Ana SL")
    newer = run(
        "invoice.issuer.sync",
        {**ISSUER, "legal_name": "New SL", "version": 4},
        system_context(A),
    )
    assert (newer.applied, newer.issuer.legal_name) == (True, "New SL")


# ── Issuing by hand (INVOICE-F03) ───────────────────────────────────────────────────────────────


def test_a_two_line_invoice_writes_its_series_its_header_and_its_lines(issuer, today):
    invoice = manual(
        lines=[
            {
                "description": "Haircut course",
                "quantity": "2",
                "unit_price": 5000,
                "tax_rate": "21",
            },
            {
                "description": "Book",
                "quantity": "1",
                "unit_price": 2000,
                "tax_rate": "4",
            },
        ],
        notes="Thanks",
    )
    assert invoice.number == f"FACT-{today.year}-000001"
    assert (
        invoice.invoice_type,
        invoice.series_code,
        invoice.status,
        invoice.source_type,
    ) == ("F1", "FACT", "issued", "manual")
    assert (invoice.base_amount, invoice.tax_amount, invoice.total_amount) == (
        12000,
        2180,
        14180,
    )
    assert [(e.rate, e.base, e.quota) for e in invoice.tax_breakdown] == [
        (Decimal("21.00"), 10000, 2100),
        (Decimal("4.00"), 2000, 80),
    ]
    assert [
        (line.description, line.quantity, line.unit_price, line.total_amount)
        for line in invoice.lines
    ] == [
        ("Haircut course", Decimal("2.000"), 5000, 12100),
        ("Book", Decimal("1.000"), 2000, 2080),
    ]
    assert (invoice.issuer_name, invoice.issuer_tax_id, invoice.issuer_address) == (
        "Peluquería Ana SL",
        "B12345674",
        "Calle Mayor 1, 28001 Madrid (Madrid)",
    )
    assert (
        invoice.customer_name,
        invoice.customer_tax_id,
        invoice.issue_date,
        invoice.operation_date,
    ) == (
        "Talleres Pérez SL",
        "B12345674",
        today,
        today,
    )
    assert invoice.notes == "Thanks"
    issued = events("invoice.invoice.issued")[-1].payload
    assert issued == {
        "invoice_id": str(invoice.id),
        "number": invoice.number,
        "series": "FACT",
        "invoice_type": "F1",
        "total": 14180,
        "source_type": "manual",
        "sale_id": None,
        "source": {"type": "manual", "sale_id": None, "refund_id": None, "void": False},
        "rectifies_id": None,
        "substitutes_id": None,
    }
    series = InvoiceSeries.objects.get(code="FACT", year=today.year)
    # The factory series is born on first use, named in English in the row and read in Spanish.
    assert (series.current_number, series.invoice_type, series.prefix, series.name) == (
        1,
        "F1",
        "FACT",
        "Invoices",
    )


def test_the_same_series_numbers_its_second_invoice_next(issuer, today):
    manual()
    assert manual().number == f"FACT-{today.year}-000002"


def test_a_full_invoice_needs_the_customers_name_tax_id_and_address_and_uses_no_number(
    issuer,
):
    with pytest.raises(Conflict) as refused:
        run(
            "invoice.invoice.create",
            {
                "lines": [
                    {
                        "description": "x",
                        "quantity": "1",
                        "unit_price": 100,
                        "tax_rate": "21",
                    }
                ],
                "customer_name": "Ana",
            },
        )
    assert refused.value.code == "invoice.recipient_incomplete"
    assert set(refused.value.fields) == {"customer_tax_id", "customer_address"}
    assert Invoice.objects.count() == 0
    assert not InvoiceSeries.objects.filter(current_number__gt=0).exists()


def test_a_ticket_series_issues_a_simplified_invoice_without_a_recipient(issuer, today):
    ticket = run(
        "invoice.invoice.create",
        {
            "series_code": "TICKET",
            "lines": [
                {
                    "description": "Coffee",
                    "quantity": "1",
                    "unit_price": 150,
                    "tax_rate": "10",
                }
            ],
        },
    )
    assert (ticket.invoice_type, ticket.number, ticket.total_amount) == (
        "F2",
        f"TICKET-{today.year}-000001",
        165,
    )


def test_a_line_with_a_tax_category_takes_its_rule_not_the_rate_typed(issuer):
    invoice = manual(
        lines=[
            {
                "description": "Medical check",
                "quantity": "1",
                "unit_price": 5000,
                "tax_rate": "21",
                "tax_category_key": "service.health",
            }
        ]
    )
    entry = invoice.tax_breakdown[0]
    assert (entry.qualification, entry.exempt_reason, entry.rate, entry.quota) == (
        "exempt",
        "E1",
        Decimal("0.00"),
        0,
    )
    assert invoice.total_amount == 5000
    # A category is named by its key, its name or an alias (voice).
    by_name = manual(
        lines=[
            {
                "description": "Lunch",
                "quantity": "1",
                "unit_price": 1000,
                "tax_category_key": "Restaurant — food",
            }
        ]
    )
    assert (by_name.tax_breakdown[0].rate, by_name.lines[0].tax_category_key) == (
        Decimal("10.00"),
        "restaurant.food",
    )


def test_a_line_with_a_tax_category_takes_the_rule_of_the_business_region(issuer):
    # TAX-F11: a business of the Canary Islands declares the IGIC of its rule, never the
    # national VAT of the same category.
    run(
        "tax.rule.create",
        {
            "country_code": "ES",
            "region_code": "ES-CN",
            "tax_category_key": "product.generic",
            "rate_pct": "7",
            "tax_type": "igic",
        },
    )
    run("tax.settings.update", {"region_code": "ES-CN"})
    invoice = manual(
        lines=[
            {
                "description": "Shirt",
                "quantity": "1",
                "unit_price": 10000,
                "tax_category_key": "product.generic",
            }
        ]
    )
    entry = invoice.tax_breakdown[0]
    assert (entry.tax, entry.rate, entry.base, entry.quota) == (
        "igic",
        Decimal("7.00"),
        10000,
        700,
    )
    assert invoice.total_amount == 10700


def test_a_line_of_a_category_without_the_territorys_rule_is_refused_not_declared_as_vat(issuer):
    # The Canary Islands are outside the VAT territory: the national 21 % of the category never stands in for
    # its missing IGIC (TAX-F11); the line is refused on its field, as one of a category without any rule.
    run("tax.settings.update", {"region_code": "ES-CN"})
    line = {"description": "Shirt", "quantity": "1", "unit_price": 10000, "tax_category_key": "product.generic"}
    with pytest.raises(Conflict) as refused:
        manual(lines=[line])
    assert refused.value.code == "invoice.no_tax_rule"
    assert list(refused.value.fields) == ["lines.0.tax_category_key"]


# ── A line without a rule: its tax category as Taxes names it, and where its rule is made (hub#1149) ──


def refused_line(category: str) -> Conflict:
    """What a manual invoice with one line of ``category`` is refused with; nothing is issued."""
    line = {"description": "Shirt", "quantity": "1", "unit_price": 10000, "tax_category_key": category}
    with pytest.raises(Conflict) as refused:
        manual(lines=[line])
    assert not Invoice.objects.exists()
    return refused.value


@pytest.mark.parametrize("language", ["en", "es"])
def test_a_line_without_a_rule_names_its_tax_category_as_taxes_does_and_where_its_rule_is_made(issuer, language):
    # INVOICE-F03: a factory category by its name in the reader's language, never by its key, below its line.
    run("tax.settings.update", {"region_code": "ES-CN"})
    shown = run("tax.category.get", {"key": "product.generic"}, ctx_for(language=language)).display_name
    assert shown != "product.generic"
    with translation.override(language):
        refusal = refused_line("product.generic")
        where = where_rules_are_made()
    assert refusal.code == "invoice.no_tax_rule"
    assert refusal.fields == {"lines.0.tax_category_key": refusal.message}
    assert f"«{shown}»" in refusal.message
    assert "product.generic" not in refusal.message
    assert where in refusal.message


def test_a_tax_category_of_the_business_without_a_rule_is_named_as_it_was_typed(issuer):
    run("tax.category.create", {"key": "own.flowers", "name": "Fresh flowers"})
    refusal = refused_line("own.flowers")
    assert refusal.code == "invoice.no_tax_rule"
    assert "«Fresh flowers»" in refusal.message
    assert "own.flowers" not in refusal.message


def test_an_unknown_tax_category_is_refused_on_its_line(issuer):
    with pytest.raises(OperationError) as refused:
        manual(
            lines=[
                {
                    "description": "x",
                    "quantity": "1",
                    "unit_price": 100,
                    "tax_category_key": "nothing.like.this",
                }
            ]
        )
    assert refused.value.code == "invoice.unknown_tax_category"
    assert refused.value.fields == {"lines.0.tax_category_key": refused.value.message}


def test_a_priced_line_that_comes_to_nothing_is_refused_but_a_free_one_is_honest(
    issuer,
):
    with pytest.raises(Conflict) as refused:
        manual(
            lines=[
                {
                    "description": "Screw",
                    "quantity": "0.001",
                    "unit_price": 1,
                    "tax_rate": "21",
                }
            ]
        )
    assert refused.value.code == "invoice.line_amount_underflow"
    assert Invoice.objects.count() == 0
    free = manual(
        lines=[
            {"description": "Gift", "quantity": "1", "unit_price": 0, "tax_rate": "21"}
        ]
    )
    assert free.total_amount == 0


def test_an_inactive_series_or_one_that_does_not_issue_invoices_is_refused(issuer, today):
    shop = run(
        "invoice.series.create",
        {"code": "SHOP", "invoice_type": "F1", "year": today.year, "is_active": False},
    )
    with pytest.raises(Conflict) as refused:
        manual(series_id=str(shop.id))
    assert refused.value.code == "invoice.series_inactive"
    credit = run(
        "invoice.series.create",
        {"code": "ABONO", "invoice_type": "R1", "year": today.year},
    )
    with pytest.raises(Conflict) as refused:
        manual(series_id=str(credit.id))
    assert refused.value.code == "invoice.series_not_issuable"
    with pytest.raises(NotFound):
        manual(series_code="NOWHERE")


def test_without_a_series_the_default_one_of_the_year_numbers(issuer, today):
    run(
        "invoice.series.create",
        {
            "code": "WEB",
            "invoice_type": "F1",
            "year": today.year,
            "prefix": "W",
            "is_default": True,
        },
    )
    assert manual().number == f"W-{today.year}-000001"


# ── Marking paid (INVOICE-F19) ──────────────────────────────────────────────────────────────────


def test_an_issued_invoice_is_marked_paid_once(issuer):
    invoice = manual()
    paid = run(
        "invoice.invoice.mark_paid", {"number": invoice.number}, ctx_for("hub_employee")
    )
    assert paid.status == "paid" and paid.paid_at is not None
    assert events("invoice.invoice.paid")[-1].payload["invoice_id"] == str(invoice.id)
    with pytest.raises(Conflict) as refused:
        run("invoice.invoice.mark_paid", {"invoice_id": str(invoice.id)})
    assert refused.value.code == "invoice.cannot_mark_paid"
    with pytest.raises(NotFound):
        run("invoice.invoice.mark_paid", {"number": "NOPE-1"})


def test_a_cancelled_invoice_or_a_rectifying_one_is_not_marked_paid(issuer):
    invoice = manual()
    rect = run(
        "invoice.invoice.rectify",
        {"invoice_id": str(invoice.id), "reason": "wrong customer"},
    ).invoice
    for target in (invoice.id, rect.id):
        with pytest.raises(Conflict) as refused:
            run("invoice.invoice.mark_paid", {"invoice_id": str(target)})
        assert refused.value.code == "invoice.cannot_mark_paid"


# ── Rectifying by hand (INVOICE-F08) ────────────────────────────────────────────────────────────


def test_rectifying_negates_the_whole_original_and_cancels_it(issuer, today):
    original = manual(
        lines=[
            {
                "description": "Course",
                "quantity": "2",
                "unit_price": 5000,
                "tax_rate": "21",
            },
            {
                "description": "Book",
                "quantity": "1",
                "unit_price": 2000,
                "tax_rate": "4",
            },
        ]
    )
    result = run(
        "invoice.invoice.rectify",
        {"number": original.number, "reason": "Wrong customer"},
    )
    rect = result.invoice
    assert (result.issued, result.already) == (True, False)
    assert (
        rect.invoice_type,
        rect.number,
        rect.series_code,
        rect.rectification_kind,
    ) == ("R1", f"RECT-{today.year}-000001", "RECT", "I")
    assert (rect.base_amount, rect.tax_amount, rect.total_amount) == (
        -12000,
        -2180,
        -14180,
    )
    assert [(e.rate, e.base, e.quota) for e in rect.tax_breakdown] == [
        (Decimal("21.00"), -10000, -2100),
        (Decimal("4.00"), -2000, -80),
    ]
    # One signed factor per line: the quantity; the price stays the price of what was sold.
    assert [
        (line.description, line.quantity, line.unit_price, line.total_amount)
        for line in rect.lines
    ] == [
        ("Course", Decimal("-2.000"), 5000, -12100),
        ("Book", Decimal("-1.000"), 2000, -2080),
    ]
    assert (
        rect.description,
        rect.issue_date,
        rect.source_type,
        rect.rectifies.number,
        rect.rectifies.status,
    ) == (
        "Wrong customer",
        today,
        "rectification",
        original.number,
        "cancelled",
    )
    # The recipient and the issuer of the original.
    assert (rect.customer_name, rect.customer_tax_id, rect.issuer_tax_id) == (
        "Talleres Pérez SL",
        "B12345674",
        "B12345674",
    )
    assert Invoice.objects.get(pk=original.id).status == "cancelled"
    rectified = events("invoice.invoice.rectified")[-1].payload
    assert rectified == {
        "invoice_id": str(original.id),
        "number": original.number,
        "status": "cancelled",
        "rectification_id": str(rect.id),
        "rectification_number": rect.number,
        "remaining": 0,
    }
    assert events("invoice.invoice.issued")[-1].payload["invoice_type"] == "R1"


def test_a_rectifying_one_or_a_cancelled_one_is_not_rectified_and_no_number_is_used(
    issuer, today,
):
    original = manual()
    rect = run(
        "invoice.invoice.rectify", {"invoice_id": str(original.id), "reason": "x"}
    ).invoice
    with pytest.raises(Conflict) as refused:
        run(
            "invoice.invoice.rectify",
            {"invoice_id": str(original.id), "reason": "again"},
        )
    assert refused.value.code == "invoice.already_cancelled"
    with pytest.raises(Conflict) as refused:
        run("invoice.invoice.rectify", {"invoice_id": str(rect.id), "reason": "again"})
    assert refused.value.code == "invoice.cannot_rectify_rectification"
    assert InvoiceSeries.objects.get(code="RECT", year=today.year).current_number == 1


def test_the_type_is_chosen_for_a_full_invoice_and_always_r5_for_a_ticket(issuer):
    invoice = manual()
    assert (
        run(
            "invoice.invoice.rectify",
            {
                "invoice_id": str(invoice.id),
                "reason": "bad debt",
                "rectification_type": "R4",
            },
        ).invoice.invoice_type
        == "R4"
    )
    ticket = run(
        "invoice.invoice.create",
        {
            "series_code": "TICKET",
            "lines": [
                {
                    "description": "Coffee",
                    "quantity": "1",
                    "unit_price": 150,
                    "tax_rate": "10",
                }
            ],
        },
    )
    assert (
        run(
            "invoice.invoice.rectify",
            {"invoice_id": str(ticket.id), "reason": "x", "rectification_type": "R2"},
        ).invoice.invoice_type
        == "R5"
    )


def test_a_rectification_is_dated_today_and_another_day_is_refused(issuer, today):
    invoice = manual()
    with pytest.raises(Conflict) as refused:
        run(
            "invoice.invoice.rectify",
            {
                "invoice_id": str(invoice.id),
                "reason": "x",
                "issue_date": str(today - dt.timedelta(days=1)),
            },
        )
    assert refused.value.code == "invoice.rectify_date_not_allowed"
    assert not Invoice.objects.filter(invoice_type__startswith="R").exists()
    assert (
        run(
            "invoice.invoice.rectify",
            {"invoice_id": str(invoice.id), "reason": "x", "issue_date": str(today)},
        ).invoice.issue_date
        == today
    )


def test_an_employee_cannot_rectify(issuer):
    invoice = manual()
    with pytest.raises(PermissionDenied):
        run(
            "invoice.invoice.rectify",
            {"invoice_id": str(invoice.id), "reason": "x"},
            ctx_for("hub_employee"),
        )


def test_the_note_of_a_rectification_is_read_in_the_readers_language(issuer):
    invoice = manual()
    rect = run(
        "invoice.invoice.rectify",
        {"invoice_id": str(invoice.id), "reason": "Precio mal"},
    ).invoice
    with translation.override("es"):
        detail = run(
            "invoice.invoice.get", {"invoice_id": str(rect.id)}, ctx_for(language="es")
        )
    assert (
        detail.rectifies.number == invoice.number and detail.description == "Precio mal"
    )


# ── Replacing a ticket by a full invoice (INVOICE-F05) ──────────────────────────────────────────


def ticket():
    return run(
        "invoice.invoice.create",
        {
            "series_code": "TICKET",
            "lines": [
                {
                    "description": "Coffee",
                    "quantity": "2",
                    "unit_price": 150,
                    "tax_rate": "10",
                }
            ],
        },
    )


def test_a_ticket_is_replaced_by_a_full_invoice_with_its_figures(issuer, today):
    simplified = ticket()
    result = run(
        "invoice.invoice.substitute",
        {"number": simplified.number, **RECIPIENT},
        ctx_for("hub_employee"),
    )
    full = result.invoice
    assert (result.issued, full.invoice_type, full.series_code, full.number) == (
        True,
        "F3",
        "FACT",
        f"FACT-{today.year}-000001",
    )
    assert (full.base_amount, full.tax_amount, full.total_amount) == (
        simplified.base_amount,
        simplified.tax_amount,
        simplified.total_amount,
    )
    assert [(line.description, line.total_amount) for line in full.lines] == [
        (line.description, line.total_amount) for line in simplified.lines
    ]
    assert (
        full.customer_name,
        full.customer_tax_id,
        full.source_type,
        full.substitutes.number,
    ) == (
        "Talleres Pérez SL",
        "B12345674",
        "substitution",
        simplified.number,
    )
    assert full.operation_date == simplified.operation_date
    replaced = run("invoice.invoice.get", {"number": simplified.number})
    assert (replaced.substituted, replaced.substituted_by.number, replaced.status) == (
        True,
        full.number,
        "issued",
    )
    assert (replaced.can_rectify, replaced.can_substitute) == (False, False)


def test_a_ticket_has_one_full_invoice_and_asking_again_issues_nothing(issuer, today):
    simplified = ticket()
    first = run(
        "invoice.invoice.substitute", {"number": simplified.number, **RECIPIENT}
    ).invoice
    again = run(
        "invoice.invoice.substitute", {"number": simplified.number, **RECIPIENT}
    )
    assert (again.issued, again.already, again.invoice.id) == (False, True, first.id)
    assert InvoiceSeries.objects.get(code="FACT", year=today.year).current_number == 1


def test_only_a_ticket_is_replaced_and_the_replaced_one_is_rectified_through_its_full_invoice(
    issuer,
):
    with pytest.raises(Conflict) as refused:
        run("invoice.invoice.substitute", {"number": manual().number, **RECIPIENT})
    assert refused.value.code == "invoice.not_a_ticket"
    simplified = ticket()
    full = run(
        "invoice.invoice.substitute", {"number": simplified.number, **RECIPIENT}
    ).invoice
    with pytest.raises(Conflict) as refused:
        run("invoice.invoice.rectify", {"number": simplified.number, "reason": "x"})
    assert refused.value.code == "invoice.substituted"
    assert (
        run(
            "invoice.invoice.rectify", {"number": full.number, "reason": "x"}
        ).invoice.invoice_type
        == "R1"
    )


def test_a_full_invoice_needs_the_whole_recipient(issuer):
    simplified = ticket()
    with pytest.raises(Conflict) as refused:
        run(
            "invoice.invoice.substitute",
            {"number": simplified.number, "customer_name": "Ana"},
        )
    assert refused.value.code == "invoice.recipient_incomplete"
