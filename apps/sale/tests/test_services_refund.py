"""Correcting a sale (SALE-F30, F31): void it before money comes back, refund it after.

A void needs a reason and a completed sale without refunds that is no full invoice; a refund gives
money back by tender (never more than each one charged minus what it already returned) and, if the
customer returns them, the lines with their units.
"""

from decimal import Decimal
from uuid import uuid7

import pytest
from live.errors import Conflict, NotFound, PermissionDenied
from live.models import OutboxEvent

from apps.sale.models import PaymentMethod, Refund, Sale
from apps.sale.tests.conftest import ctx_for, run

pytestmark = pytest.mark.django_db


def events(name: str) -> list[dict]:
    return [
        e.payload
        for e in OutboxEvent.objects.filter(name=name).order_by("created_at", "id")
    ]


@pytest.fixture
def catalog(product):
    product("Shampoo", "SHA", 1000, "product.generic")
    product("Coffee", "COF", 1500, "product.generic")


def charge(key: str, lines, payments, **more):
    return run(
        "sale.sale.complete",
        {"idempotency_key": key, "lines": lines, "payments": payments, **more},
    )


@pytest.fixture
def mixed(catalog):
    """A 70.00 € sale: 50.00 by card and 20.00 in cash."""
    return charge(
        "pos-mixed-0001",
        [
            {"product": "SHA", "quantity": "3"},
            {"product": "COF", "quantity": "2"},
            {"product": "SHA"},
        ],
        [{"method": "card", "amount": 5000}, {"method": "cash", "amount": 2000}],
    )


def refund(sale, *allocations, lines=(), reason="returned", ctx=None, **more):
    data = {
        "sale_id": str(sale.id),
        "reason": reason,
        "allocations": list(allocations),
        "lines": list(lines),
        **more,
    }
    return run("sale.sale.refund", data, ctx)


def leg(sale, method_type: str) -> str:
    return str(next(p.id for p in sale.payments if p.method_type == method_type))


# ── Void ────────────────────────────────────────────────────────────────────────────────────────


def test_voiding_a_sale_keeps_it_and_says_why(mixed):
    OutboxEvent.objects.all().delete()
    voided = run(
        "sale.sale.void",
        {"sale_id": str(mixed.id), "reason": "Wrong ticket"},
        ctx_for(actor="manager"),
    )
    assert (voided.status, voided.void_reason, voided.voided_by, voided.total) == (
        "voided",
        "Wrong ticket",
        "manager",
        7000,
    )
    assert voided.voided_at is not None and voided.number == mixed.number
    (payload,) = events("sale.sale.voided")
    assert payload | {"voided_at": None} == {
        "sale_id": str(mixed.id),
        "sale_number": mixed.number,
        "reason": "Wrong ticket",
        "voided_by": "manager",
        "voided_at": None,
        "total": 7000,
        "order_id": str(mixed.order_id),
        "document_type": "ticket",
        "customer_id": None,
    }
    assert "[VOIDED] Wrong ticket" in Sale.objects.get(pk=mixed.id).notes


def test_a_sale_is_voided_once(mixed):
    run("sale.sale.void", {"sale": mixed.number, "reason": "first"})
    with pytest.raises(Conflict) as refusal:
        run("sale.sale.void", {"sale_id": str(mixed.id), "reason": "second"})
    assert refusal.value.code == "sale.already_voided"
    assert Sale.objects.get(pk=mixed.id).void_reason == "first"
    assert len(events("sale.sale.voided")) == 1


def test_a_sale_with_refunds_is_refunded_not_voided(mixed):
    refund(mixed, {"payment_id": leg(mixed, "cash"), "amount": 500})
    with pytest.raises(Conflict) as refusal:
        run("sale.sale.void", {"sale_id": str(mixed.id), "reason": "late"})
    assert refusal.value.code == "sale.sale_already_refunded"


def test_a_full_invoice_is_corrected_with_a_credit_note(catalog):
    sale = charge(
        "pos-invoice-001",
        [{"product": "COF"}],
        [{"method": "card"}],
        document_type="invoice",
        customer_name="Bar Manolo",
        customer_tax_id="B12345674",
        customer_address="C/ Mayor 1",
    )
    with pytest.raises(Conflict) as refusal:
        run("sale.sale.void", {"sale_id": str(sale.id), "reason": "x"})
    assert refusal.value.code == "sale.void_requires_credit_note"


def test_voiding_is_the_managers_and_an_unknown_sale_is_not_found(mixed):
    with pytest.raises(PermissionDenied):
        run(
            "sale.sale.void",
            {"sale_id": str(mixed.id), "reason": "x"},
            ctx_for("hub_employee"),
        )
    with pytest.raises(NotFound) as refusal:
        run("sale.sale.void", {"sale_id": str(uuid7()), "reason": "x"})
    assert refusal.value.code == "sale.sale_not_found"


# ── Refund by tender ────────────────────────────────────────────────────────────────────────────


def test_a_partial_refund_leaves_the_sale_completed(mixed):
    OutboxEvent.objects.all().delete()
    done = refund(
        mixed,
        {"payment_id": leg(mixed, "cash"), "amount": 2000},
        idempotency_key="refund-0001",
        note="by the counter",
    )
    assert (done.total, done.fully_refunded, done.already) == (2000, False, False)
    sale = run("sale.sale.get", {"sale_id": str(mixed.id)})
    assert (sale.status, sale.refunded_total, sale.refundable_total) == (
        "completed",
        2000,
        5000,
    )
    (payload,) = events("sale.sale.refunded")
    assert (
        payload["refund_id"] == str(done.refund_id)
        and payload["total"] == 2000
        and payload["fully_refunded"] is False
    )
    assert payload["payments"] == [
        {
            "payment_id": leg(mixed, "cash"),
            "method_id": str(PaymentMethod.objects.get(type="cash").id),
            "method_name": "Cash",
            "method_type": "cash",
            "amount": 2000,
        }
    ]
    assert payload["lines"] == [] and payload["reason"] == "returned"


def test_the_last_cent_turns_the_sale_refunded(mixed):
    refund(mixed, {"payment_id": leg(mixed, "cash"), "amount": 2000})
    done = refund(mixed, {"payment_id": leg(mixed, "card"), "amount": 5000})
    assert done.fully_refunded is True
    assert Sale.objects.get(pk=mixed.id).status == "refunded"
    with pytest.raises(Conflict) as refusal:
        refund(mixed, {"payment_id": leg(mixed, "card"), "amount": 1})
    assert refusal.value.code == "sale.refund_requires_completed"


def test_a_tender_never_gives_back_more_than_it_has_left(mixed):
    refund(mixed, {"payment_id": leg(mixed, "card"), "amount": 1500})
    with pytest.raises(Conflict) as refusal:
        refund(mixed, {"payment_id": leg(mixed, "card"), "amount": 3501})
    assert refusal.value.code == "sale.refund_exceeds_tender"
    assert "Card" in refusal.value.message
    assert (
        refund(mixed, {"payment_id": leg(mixed, "card"), "amount": 3500}).total == 3500
    )


def test_the_tenders_named_must_be_this_sales_and_once(mixed):
    with pytest.raises(Conflict) as refusal:
        refund(mixed, {"payment_id": str(uuid7()), "amount": 100})
    assert refusal.value.code == "sale.refund_tender_unknown"
    cash = leg(mixed, "cash")
    with pytest.raises(Conflict) as refusal:
        refund(
            mixed,
            {"payment_id": cash, "amount": 100},
            {"payment_id": cash, "amount": 100},
        )
    assert refusal.value.code == "sale.refund_tender_duplicated"


def test_money_goes_back_by_another_method_when_the_original_is_gone(mixed):
    PaymentMethod.objects.filter(type="card").update(is_active=False)
    options = run("sale.refund.options", {"sale_id": str(mixed.id)})
    card_option = next(t for t in options.tenders if t.method_type == "card")
    assert (card_option.refundable, card_option.reason, card_option.remaining) == (
        False,
        "method_unavailable",
        5000,
    )
    with pytest.raises(Conflict) as refusal:
        refund(mixed, {"payment_id": leg(mixed, "card"), "amount": 1000})
    assert refusal.value.code == "sale.refund_tender_not_eligible"
    cash_method = str(PaymentMethod.objects.get(type="cash").id)
    done = refund(
        mixed,
        {"payment_id": leg(mixed, "card"), "amount": 1000, "to_method_id": cash_method},
    )
    assert done.total == 1000
    (payment,) = Refund.objects.get(pk=done.refund_id).payments.all()
    assert (payment.method_type, payment.sale_payment_id) == (
        "cash",
        Sale.objects.get(pk=mixed.id).payments.get(method_type="card").id,
    )
    with pytest.raises(Conflict) as refusal:
        refund(
            mixed,
            {
                "payment_id": leg(mixed, "card"),
                "amount": 1000,
                "to_method_id": str(uuid7()),
            },
        )
    assert refusal.value.code == "sale.refund_method_unavailable"


# ── Lines that come back ────────────────────────────────────────────────────────────────────────


def test_lines_come_back_with_their_units(mixed):
    shampoos = str(mixed.lines[0].id)
    cash = leg(mixed, "cash")
    OutboxEvent.objects.all().delete()
    refund(
        mixed,
        {"payment_id": cash, "amount": 1000},
        lines=[{"line_id": shampoos, "quantity": "1"}],
    )
    (payload,) = events("sale.sale.refunded")
    assert payload["lines"] == [
        {
            "line_id": shampoos,
            "product_id": str(mixed.lines[0].product_id),
            "quantity": "1.000",
        }
    ]
    with pytest.raises(Conflict) as refusal:
        refund(
            mixed,
            {"payment_id": cash, "amount": 100},
            lines=[{"line_id": shampoos, "quantity": "3"}],
        )
    assert refusal.value.code == "sale.refund_line_quantity_exceeded"
    # Without units, all that is left of it.
    refund(mixed, {"payment_id": cash, "amount": 100}, lines=[{"line_id": shampoos}])
    options = run("sale.refund.options", {"sale_id": str(mixed.id)})
    first = next(line for line in options.lines if line.line_id == mixed.lines[0].id)
    assert (first.quantity, first.returned, first.left) == (
        Decimal("3.000"),
        Decimal("3.000"),
        Decimal("0.000"),
    )
    with pytest.raises(Conflict) as refusal:
        refund(
            mixed, {"payment_id": cash, "amount": 100}, lines=[{"line_id": shampoos}]
        )
    assert refusal.value.code == "sale.refund_line_already_returned"


def test_the_lines_named_must_be_this_sales_and_once(mixed):
    cash = leg(mixed, "cash")
    with pytest.raises(Conflict) as refusal:
        refund(
            mixed,
            {"payment_id": cash, "amount": 100},
            lines=[{"line_id": str(uuid7())}],
        )
    assert refusal.value.code == "sale.refund_line_unknown"
    line = str(mixed.lines[1].id)
    with pytest.raises(Conflict) as refusal:
        refund(
            mixed,
            {"payment_id": cash, "amount": 100},
            lines=[{"line_id": line}, {"line_id": line}],
        )
    assert refusal.value.code == "sale.refund_line_duplicated"


def test_a_retry_of_the_same_refund_gives_back_nothing_more(mixed):
    first = refund(
        mixed,
        {"payment_id": leg(mixed, "cash"), "amount": 500},
        idempotency_key="refund-0001",
    )
    again = refund(
        mixed,
        {"payment_id": leg(mixed, "cash"), "amount": 500},
        idempotency_key="refund-0001",
    )
    assert (again.already, again.refund_id, again.total) == (True, first.refund_id, 500)
    assert Sale.objects.get(pk=mixed.id).refunded_total == 500
    assert len(events("sale.sale.refunded")) == 1


def test_a_voided_sale_has_nothing_to_refund(mixed):
    run("sale.sale.void", {"sale_id": str(mixed.id), "reason": "x"})
    with pytest.raises(Conflict) as refusal:
        refund(mixed, {"payment_id": leg(mixed, "cash"), "amount": 100})
    assert refusal.value.code == "sale.refund_requires_completed"


def test_refunding_is_the_managers(mixed):
    with pytest.raises(PermissionDenied):
        refund(
            mixed,
            {"payment_id": leg(mixed, "cash"), "amount": 100},
            ctx=ctx_for("hub_employee"),
        )


def test_a_refund_key_reused_for_another_sale_or_other_lines_is_refused(mixed, catalog):
    other = charge("pos-other-0001", [{"product": "COF"}], [{"method": "card"}])
    cash_leg = leg(mixed, "cash")
    refund(mixed, {"payment_id": cash_leg, "amount": 500}, lines=[{"line_id": str(mixed.lines[1].id), "quantity": "1"}], idempotency_key="refund-key-01")
    with pytest.raises(Conflict) as refusal:
        refund(other, {"payment_id": str(other.payments[0].id), "amount": 100}, idempotency_key="refund-key-01")
    assert refusal.value.code == "sale.idempotency_key_reused"
    with pytest.raises(Conflict) as refusal:
        refund(mixed, {"payment_id": cash_leg, "amount": 500}, lines=[{"line_id": str(mixed.lines[0].id)}], idempotency_key="refund-key-01")
    assert refusal.value.code == "sale.idempotency_key_reused"
