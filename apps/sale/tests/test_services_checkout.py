"""Charging (SALE-F01–F06, F09, F14, F22, F26): ``sale.sale.complete`` and its manager door.

The amounts are tax's real calculation over the factory catalogue (Spain): restaurant.drink and
restaurant.food at 10 %, product.generic at 21 %.
"""

import datetime as dt
from decimal import Decimal
from uuid import uuid7

import pytest
from django.utils import timezone
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent

from apps.sale.models import Order, OrderLine, PaymentMethod, Sale, SaleCounter
from apps.sale.tests.conftest import ctx_for, run

pytestmark = pytest.mark.django_db

EMPLOYEE = "hub_employee"
KEY = "pos-attempt-0001"


def events(prefix: str = "sale.") -> list[tuple[str, dict]]:
    return [
        (e.name, e.payload)
        for e in OutboxEvent.objects.filter(name__startswith=prefix).order_by(
            "created_at", "id"
        )
    ]


def names() -> list[str]:
    return [name for name, _payload in events()]


@pytest.fixture
def catalog(product):
    product("Coffee", "COF", 121, "product.generic", cost=40)
    product("Water", "WAT", 110, "restaurant.drink", cost=20)
    product("Steak", "STK", 1800, "restaurant.food", cost=700)
    product("Gold", "GLD", 60000, "product.generic")


def complete(ctx=None, key: str = KEY, **data):
    return run("sale.sale.complete", {"idempotency_key": key, **data}, ctx)


def cash(tendered: int | None = None, **more) -> dict:
    return {
        "method": "cash",
        **({"tendered": tendered} if tendered is not None else {}),
        **more,
    }


def open_order(*lines, **more):
    return run("sale.order.open", {"lines": list(lines), **more})


def settings(**values) -> None:
    run("sale.settings.update", values)


# ── A counter sale in cash ──────────────────────────────────────────────────────────────────────


def test_a_counter_sale_in_cash_with_change(catalog):
    sale = complete(
        lines=[{"product": "COF", "quantity": "2"}, {"product": "WAT"}],
        payments=[cash(2000)],
    )
    today = timezone.localdate()
    assert sale.number == f"{today:%Y%m%d}-0001" and sale.business_day == today
    assert (sale.status, sale.document_type, sale.tax_included) == (
        "completed",
        "ticket",
        True,
    )
    assert (sale.total, sale.subtotal, sale.tax_total, sale.discount_amount) == (
        352,
        300,
        52,
        0,
    )
    assert (sale.tendered_total, sale.change_total, sale.payment_method_name) == (
        2000,
        1648,
        "Cash",
    )
    (leg,) = sale.payments
    assert (leg.method_type, leg.amount, leg.tendered, leg.change) == (
        "cash",
        352,
        2000,
        1648,
    )
    coffee, water = sale.lines
    assert (
        coffee.net_amount,
        coffee.tax_amount,
        coffee.line_total,
        coffee.tax_rate,
    ) == (200, 42, 242, Decimal("21.00"))
    assert (
        coffee.tax_category_key,
        coffee.tax_country_code,
        coffee.tax_rule_id is not None,
    ) == ("product.generic", "ES", True)
    assert (water.net_amount, water.tax_amount, water.line_total) == (100, 10, 110)
    assert [(b.rate_pct, b.base, b.tax) for b in sale.breakdown] == [
        (Decimal("21.00"), 200, 42),
        (Decimal("10.00"), 100, 10),
    ]
    # A counter sale is a check opened and charged in the same step.
    order = Order.objects.get(pk=sale.order_id)
    assert (order.status, order.source) == ("completed", "counter")
    assert set(
        OrderLine.objects.filter(order=order).values_list("sale_id", flat=True)
    ) == {sale.id}
    assert names() == [
        "sale.order.opened",
        "sale.sale.completed",
        "sale.order.completed",
    ]


def test_the_sale_event_carries_what_inventory_and_customer_read(catalog, customer):
    ana = customer("Ana López", phone="600111222", tax_id="12345678Z")
    staff = uuid7()
    sale = complete(
        lines=[
            {"product": "COF", "quantity": "2"},
            {"product": "WAT", "is_gift": True},
        ],
        payments=[cash(1000)],
        customer_id=str(ana.id),
        staff_id=str(staff),
    )
    ((_, payload),) = [event for event in events() if event[0] == "sale.sale.completed"]
    assert payload["sale_id"] == str(sale.id) and payload["sale_number"] == sale.number
    assert (
        payload["total"],
        payload["subtotal"],
        payload["tax_amount"],
        payload["currency"],
    ) == (242, 200, 42, "EUR")
    assert (
        payload["customer_id"],
        payload["customer_name"],
        payload["customer_tax_id"],
    ) == (str(ana.id), "Ana López", "12345678Z")
    assert payload["staff_id"] == str(staff) and payload["document_type"] == "ticket"
    assert payload["purchased_at"] and payload["gift_total"] == 20
    assert payload["payments"] == [
        {
            "method_id": str(sale.payments[0].method_id),
            "method_name": "Cash",
            "method_type": "cash",
            "amount": 242,
            "tendered": 1000,
            "change": 758,
            "reference": "",
        }
    ]
    coffee, water = payload["items"]
    assert (
        coffee["product_id"]
        and coffee["quantity"] == "2.000"
        and coffee["is_service"] is False
    )
    assert (
        coffee["components"] == []
        and coffee["is_gift"] is False
        and coffee["line_total"] == 242
    )
    assert water["is_gift"] is True and water["line_total"] == 0
    assert payload["items_count"] == 2


def test_numbers_follow_the_business_day(catalog):
    first = complete(lines=[{"product": "COF"}])
    second = complete(key="pos-attempt-0002", lines=[{"product": "COF"}])
    assert second.number.endswith("-0002") and first.number.endswith("-0001")
    assert SaleCounter.objects.get(day=timezone.localdate()).last == 2


def test_the_same_attempt_charges_once(catalog):
    first = complete(lines=[{"product": "COF"}], payments=[cash(500)])
    OutboxEvent.objects.all().delete()
    again = complete(lines=[{"product": "COF"}], payments=[cash(500)])
    assert again.id == first.id and again.already is True and first.already is False
    assert Sale.objects.count() == 1 and events() == []


def test_without_payments_it_is_cash_for_the_exact_amount(catalog):
    sale = complete(lines=[{"product": "COF"}])
    assert [(p.method_type, p.amount, p.tendered, p.change) for p in sale.payments] == [
        ("cash", 121, 121, 0)
    ]


# ── Other methods and split payments ────────────────────────────────────────────────────────────


def test_a_card_charges_the_exact_amount(catalog):
    sale = complete(
        lines=[{"product": "STK"}],
        payments=[{"method": "card", "tendered": 5000, "reference": "AUTH-7788"}],
    )
    (leg,) = sale.payments
    assert (leg.method_name, leg.amount, leg.tendered, leg.change, leg.reference) == (
        "Card",
        1800,
        1800,
        0,
        "AUTH-7788",
    )


def test_a_split_payment_takes_the_change_out_of_the_cash(catalog):
    sale = complete(
        lines=[{"product": "STK"}],
        payments=[
            {"method": "cash", "amount": 1000, "tendered": 2000},
            {"method": "card"},
        ],
    )
    assert [(p.method_type, p.amount, p.tendered, p.change) for p in sale.payments] == [
        ("cash", 1000, 2000, 1000),
        ("card", 800, 800, 0),
    ]
    assert (sale.payment_method_name, sale.tendered_total, sale.change_total) == (
        "Cash",
        2800,
        1000,
    )


def test_payments_must_add_up_to_the_total(catalog):
    with pytest.raises(Conflict) as refusal:
        complete(
            lines=[{"product": "STK"}], payments=[{"method": "card", "amount": 1000}]
        )
    assert refusal.value.code == "sale.payments_do_not_match_total"
    with pytest.raises(Conflict) as refusal:
        complete(
            lines=[{"product": "STK"}],
            payments=[
                {"method": "card", "amount": 1000},
                {"method": "cash", "amount": 1000},
            ],
        )
    assert refusal.value.code == "sale.payments_do_not_match_total"


def test_short_cash_is_refused(catalog):
    with pytest.raises(Conflict) as refusal:
        complete(lines=[{"product": "STK"}], payments=[cash(1000)])
    assert refusal.value.code == "sale.insufficient_tendered"
    assert Sale.objects.count() == 0 and not SaleCounter.objects.exists()


def test_no_cash_from_one_thousand_euros_in_spain(catalog):
    gold = [{"product": "GLD", "quantity": "2"}]  # 1.200 €
    with pytest.raises(Conflict) as refusal:
        complete(lines=gold, payments=[cash(120000)])
    assert refusal.value.code == "sale.cash_limit_exceeded"
    # One cent of cash is enough to refuse a mixed payment.
    with pytest.raises(Conflict) as refusal:
        complete(
            lines=gold, payments=[{"method": "cash", "amount": 1}, {"method": "card"}]
        )
    assert refusal.value.code == "sale.cash_limit_exceeded"
    assert complete(lines=gold, payments=[{"method": "card"}]).total == 120000


def test_just_under_the_cash_limit_is_fine(product):
    product("Almost", "ALM", 99999, "product.generic")
    assert (
        complete(lines=[{"product": "ALM"}], payments=[cash(100000)]).change_total == 1
    )


def test_a_method_is_named_by_id_name_or_type_and_never_guessed(catalog):
    card = PaymentMethod.objects.get(type="card")
    assert (
        complete(
            lines=[{"product": "COF"}], payments=[{"method_id": str(card.id)}]
        ).payment_method_name
        == "Card"
    )
    assert (
        complete(
            key="pos-attempt-0002",
            lines=[{"product": "COF"}],
            payments=[{"method": "Tarjeta"}],
        ).payment_method_name
        == "Card"
    )
    # Named by its type, «cash» fits two methods once the factory one is renamed.
    PaymentMethod.objects.filter(type="cash").update(name="Till")
    run("sale.payment_method.create", {"name": "Petty cash", "type": "cash"})
    with pytest.raises(Conflict) as refusal:
        complete(
            key="pos-attempt-0003",
            lines=[{"product": "COF"}],
            payments=[{"method": "cash"}],
        )
    assert refusal.value.code == "sale.payment_method_ambiguous"
    with pytest.raises(Conflict) as refusal:
        complete(
            key="pos-attempt-0003",
            lines=[{"product": "COF"}],
            payments=[{"method": "bitcoin"}],
        )
    assert refusal.value.code == "sale.payment_method_not_available"


def test_the_settings_decide_which_methods_charge(catalog):
    settings(allow_card=False)
    with pytest.raises(Conflict) as refusal:
        complete(lines=[{"product": "COF"}], payments=[{"method": "card"}])
    assert refusal.value.code == "sale.payment_method_not_available"
    # With every method turned off, every active one is allowed again.
    settings(allow_cash=False)
    assert (
        complete(
            lines=[{"product": "COF"}], payments=[{"method": "card"}]
        ).payment_method_name
        == "Card"
    )


def test_an_inactive_method_does_not_charge(catalog):
    PaymentMethod.objects.filter(type="card").update(is_active=False)
    with pytest.raises(Conflict) as refusal:
        complete(lines=[{"product": "COF"}], payments=[{"method": "card"}])
    assert refusal.value.code == "sale.payment_method_not_available"


# ── Ticket or invoice, and the customer ─────────────────────────────────────────────────────────


def test_an_invoice_needs_the_customers_name_tax_id_and_address(catalog):
    with pytest.raises(Conflict) as refusal:
        complete(
            lines=[{"product": "COF"}],
            document_type="invoice",
            customer_name="Bar Manolo",
        )
    assert refusal.value.code == "sale.invoice_recipient_incomplete"
    sale = complete(
        lines=[{"product": "COF"}],
        document_type="invoice",
        customer_name="Bar Manolo",
        customer_tax_id="B12345674",
        customer_address="C/ Mayor 1",
    )
    assert (sale.document_type, sale.customer_name) == ("invoice", "Bar Manolo")


def recipient_refusal(**recipient) -> dict:
    with pytest.raises(InvalidPayload) as refusal:
        complete(
            lines=[{"product": "COF"}],
            document_type="invoice",
            customer_name="Bar Manolo",
            customer_address="C/ Mayor 1",
            **recipient,
        )
    assert Sale.objects.count() == 0
    return refusal.value.fields


def test_an_invoice_to_a_spanish_tax_id_that_does_not_check_is_refused_on_its_field(catalog):
    # SALE-F04: a NIF, NIE or CIF is read the one way Customers reads it (apps.customer.tax_ids).
    assert recipient_refusal(customer_tax_id="B12345678") == {
        "customer_tax_id": "That tax ID is not valid."
    }


def test_an_invoice_abroad_says_what_kind_of_document_its_tax_id_is(catalog):
    # VeriFactu declares a foreign tax ID as IDOtro, which the tax agency refuses without its IDType.
    assert recipient_refusal(customer_tax_id="AB123456", customer_country="GB") == {
        "customer_id_type": "Say what kind of document a foreign tax ID is (EU VAT number, passport, tax ID of their "
        "country…)."
    }
    # An EU VAT number (02) is checked; any other kind is taken as written.
    assert recipient_refusal(
        customer_tax_id="FR00000000000", customer_country="FR", customer_id_type="02"
    ) == {"customer_tax_id": "That tax ID is not valid."}
    sale = complete(
        lines=[{"product": "COF"}],
        document_type="invoice",
        customer_name="Durand SARL",
        customer_tax_id="40 303 265 045",
        customer_address="1 rue de Rivoli, Paris",
        customer_country="FR",
        customer_id_type="02",
    )
    ((_, payload),) = [event for event in events() if event[0] == "sale.sale.completed"]
    assert (payload["customer_tax_id"], payload["customer_country"], payload["customer_id_type"]) == (
        "FR40303265045",
        "FR",
        "02",
    )
    assert sale.document_type == "invoice"
    passport = complete(
        key="pos-attempt-0099",
        lines=[{"product": "COF"}],
        document_type="invoice",
        customer_name="John Smith",
        customer_tax_id="P1234567",
        customer_address="10 Downing St, London",
        customer_country="GB",
        customer_id_type="03",
    )
    assert passport.document_type == "invoice"


def test_an_invoice_to_a_card_whose_tax_id_does_not_check_is_refused(catalog, customer):
    ana = customer("Ana López", address="C/ Sol 2", city="Madrid")
    from apps.customer.models import Customer

    Customer.objects.filter(pk=ana.id).update(tax_id="12345678A")
    with pytest.raises(InvalidPayload) as refusal:
        complete(lines=[{"product": "COF"}], document_type="invoice", customer_id=str(ana.id))
    assert refusal.value.fields == {"customer_tax_id": "That tax ID is not valid."}


def test_a_ticket_does_not_check_a_tax_id_it_does_not_declare(catalog):
    sale = complete(lines=[{"product": "COF"}], customer_tax_id="whatever")
    assert sale.document_type == "ticket"


def test_an_invoice_takes_the_cards_details_by_default(catalog, customer):
    ana = customer("Ana López", tax_id="12345678Z", address="C/ Sol 2", city="Madrid")
    sale = complete(
        lines=[{"product": "COF"}], document_type="invoice", customer_id=str(ana.id)
    )
    assert (sale.document_type, sale.customer_id, sale.customer_name) == (
        "invoice",
        ana.id,
        "Ana López",
    )


def test_a_ticket_is_up_to_three_thousand_euros(product):
    product("Watch", "WCH", 300000, "product.generic")
    product("Watch plus", "WCP", 300001, "product.generic")
    assert (
        complete(
            lines=[{"product": "WCH"}], payments=[{"method": "card"}]
        ).document_type
        == "ticket"
    )
    with pytest.raises(Conflict) as refusal:
        complete(
            key="pos-attempt-0002",
            lines=[{"product": "WCP"}],
            payments=[{"method": "card"}],
        )
    assert refusal.value.code == "sale.ticket_over_limit"


def test_the_default_document_comes_from_the_settings(catalog):
    settings(default_document_type="invoice")
    with pytest.raises(Conflict) as refusal:
        complete(lines=[{"product": "COF"}])
    assert refusal.value.code == "sale.invoice_recipient_incomplete"
    assert (
        complete(lines=[{"product": "COF"}], document_type="ticket").document_type
        == "ticket"
    )


def test_a_business_that_requires_a_customer(catalog, customer):
    settings(require_customer=True)
    with pytest.raises(Conflict) as refusal:
        complete(lines=[{"product": "COF"}])
    assert refusal.value.code == "sale.customer_required"
    customer("Ana López", phone="600111222")
    sale = complete(lines=[{"product": "COF"}], customer="600 111 222")
    assert sale.customer_name == "Ana López"


def test_a_customer_named_aloud_must_be_one(catalog, customer):
    # Two cards of the same name: the till never picks one for the cashier.
    customer("Ana López", phone="600111222")
    customer("Ana López", phone="600333444")
    with pytest.raises(Conflict) as refusal:
        complete(lines=[{"product": "COF"}], customer="Ana López")
    assert refusal.value.code == "customer.customer_ambiguous"
    assert complete(lines=[{"product": "COF"}], customer="600333444").customer_name == "Ana López"
    with pytest.raises(NotFound):
        complete(key="pos-attempt-0002", lines=[{"product": "COF"}], customer="Nobody")


# ── An open check ───────────────────────────────────────────────────────────────────────────────


def test_charging_a_whole_check_closes_it(catalog):
    order = open_order({"product": "COF", "quantity": "2"}, {"product": "WAT"})
    OutboxEvent.objects.all().delete()
    sale = complete(
        order_id=str(order.id), order_version=order.version, payments=[cash(500)]
    )
    assert (sale.total, sale.order_id) == (352, order.id)
    assert Order.objects.get(pk=order.id).status == "completed"
    assert set(
        OrderLine.objects.filter(order_id=order.id).values_list("sale_id", flat=True)
    ) == {sale.id}
    assert names() == ["sale.sale.completed", "sale.order.completed"]


def test_a_check_is_charged_at_its_own_discounts(catalog):
    order = open_order({"product": "STK"}, {"product": "WAT"})
    run(
        "sale.order.set_line_discount",
        {
            "order_id": str(order.id),
            "line_id": str(order.lines[0].id),
            "discount_percent": "10",
        },
    )
    order = run(
        "sale.order.set_discount",
        {"order_id": str(order.id), "discount_percent": "10", "discount_amount": 100},
    )
    sale = complete(order_id=str(order.id), payments=[{"method": "card"}])
    # Steak 1800 × 0.9 × 0.9 = 1458, water 110 × 0.9 = 99; then 100 off by weight.
    assert sale.total == 1458 + 99 - 100
    assert sale.discount_amount == 1910 - sale.total
    assert (sale.discount_percent, sale.lines[0].discount_percent) == (
        Decimal("10.00"),
        Decimal("10.00"),
    )


def test_paying_part_of_a_check_leaves_the_rest_open(catalog):
    order = open_order({"product": "STK"}, {"product": "WAT"})
    steak, water = order.lines
    OutboxEvent.objects.all().delete()
    first = complete(
        order_id=str(order.id), line_ids=[str(steak.id)], payments=[{"method": "card"}]
    )
    assert first.total == 1800 and [line.name for line in first.lines] == ["Steak"]
    left = run("sale.order.get", {"order_id": str(order.id)})
    assert left.status == "open" and [line.name for line in left.lines] == ["Water"]
    assert names() == ["sale.sale.completed"]
    second = complete(
        key="pos-attempt-0002",
        order_id=str(order.id),
        line_ids=[str(water.id)],
        payments=[cash(110)],
    )
    assert second.total == 110 and Order.objects.get(pk=order.id).status == "completed"
    assert Order.objects.get(pk=order.id).sales.count() == 2


def test_a_fixed_ticket_amount_only_comes_off_the_charge_that_closes_the_check(catalog):
    order = open_order({"product": "STK"}, {"product": "WAT"})
    run(
        "sale.order.set_discount",
        {"order_id": str(order.id), "discount_percent": "0", "discount_amount": 50},
    )
    first = complete(
        order_id=str(order.id),
        line_ids=[str(order.lines[0].id)],
        payments=[{"method": "card"}],
    )
    assert first.total == 1800
    second = complete(
        key="pos-attempt-0002", order_id=str(order.id), payments=[{"method": "card"}]
    )
    assert second.total == 60


def test_a_check_that_changed_since_the_screen_read_it_is_not_charged(catalog):
    order = open_order({"product": "STK"})
    run(
        "sale.order.update_line",
        {"order_id": str(order.id), "line_id": str(order.lines[0].id), "quantity": "2"},
    )
    with pytest.raises(Conflict) as refusal:
        complete(
            order_id=str(order.id),
            order_version=order.version,
            payments=[{"method": "card"}],
        )
    assert refusal.value.code == "sale.order_changed"
    assert Sale.objects.count() == 0 and not SaleCounter.objects.exists()
    current = run("sale.order.get", {"order_id": str(order.id)})
    assert (
        complete(
            order_id=str(order.id),
            order_version=current.version,
            payments=[{"method": "card"}],
        ).total
        == 3600
    )


def test_a_charge_of_lines_that_are_gone_is_refused(catalog):
    order = open_order({"product": "STK"}, {"product": "WAT"})
    steak, water = order.lines
    run("sale.order.remove_line", {"order_id": str(order.id), "line_id": str(water.id)})
    with pytest.raises(Conflict) as refusal:
        complete(
            order_id=str(order.id),
            line_ids=[str(water.id)],
            payments=[{"method": "card"}],
        )
    assert refusal.value.code == "sale.order_changed"
    with pytest.raises(Conflict) as refusal:
        complete(
            order_id=str(order.id),
            line_ids=[str(uuid7())],
            payments=[{"method": "card"}],
        )
    assert refusal.value.code == "sale.order_changed"


def test_a_closed_or_empty_check_is_not_charged(catalog):
    order = open_order({"product": "STK"})
    run("sale.order.void", {"order_id": str(order.id)})
    with pytest.raises(Conflict) as refusal:
        complete(order_id=str(order.id), payments=[{"method": "card"}])
    assert refusal.value.code == "sale.order_changed"
    with pytest.raises(Conflict) as refusal:
        complete(
            key="pos-attempt-0002",
            order_id=str(open_order().id),
            payments=[{"method": "card"}],
        )
    assert refusal.value.code == "sale.empty_sale"
    with pytest.raises(NotFound):
        complete(
            key="pos-attempt-0003", order_id=str(uuid7()), payments=[{"method": "card"}]
        )


def test_charging_a_check_with_an_appointment_says_so(catalog):
    appointment, staff = uuid7(), uuid7()
    order = open_order({"product": "STK"}, appointment_id=str(appointment))
    OutboxEvent.objects.all().delete()
    sale = complete(
        order_id=str(order.id), staff_id=str(staff), payments=[{"method": "card"}]
    )
    assert (sale.appointment_id, sale.staff_id) == (appointment, staff)
    assert (
        "sale.sale.created_from_appointment",
        {
            "sale_id": str(sale.id),
            "appointment_id": str(appointment),
            "staff_id": str(staff),
            "total": 1800,
        },
    ) in events()


def test_a_line_keeps_its_professional_and_the_sale_takes_the_one_charged_with(catalog):
    line_staff, sale_staff = uuid7(), uuid7()
    sale = complete(
        lines=[{"product": "STK", "staff_id": str(line_staff)}, {"product": "WAT"}],
        staff_id=str(sale_staff),
        payments=[{"method": "card"}],
    )
    assert [line.staff_id for line in sale.lines] == [line_staff, None]
    assert sale.staff_id == sale_staff


# ── Discounts at the charge ─────────────────────────────────────────────────────────────────────


def test_discounts_are_checked_again_when_charging(catalog):
    order = open_order({"product": "STK"})
    run(
        "sale.order.set_discount", {"order_id": str(order.id), "discount_percent": "50"}
    )
    settings(max_discount_percent=10)
    with pytest.raises(Conflict) as refusal:
        complete(order_id=str(order.id), payments=[{"method": "card"}])
    assert refusal.value.code == "sale.discount_over_limit"
    # The manager's door charges it.
    sale = run(
        "sale.sale.complete_over_limit",
        {
            "idempotency_key": KEY,
            "order_id": str(order.id),
            "payments": [{"method": "card"}],
        },
    )
    assert sale.total == 900


def test_a_discount_the_manager_approved_is_not_asked_again(catalog):
    settings(max_discount_percent=10)
    order = open_order({"product": "STK"})
    run(
        "sale.order.set_discount_over_limit",
        {"order_id": str(order.id), "discount_percent": "50"},
    )
    sale = complete(
        ctx_for(EMPLOYEE), order_id=str(order.id), payments=[{"method": "card"}]
    )
    assert sale.total == 900


def test_a_counter_discount_over_the_cap_or_with_discounts_off(catalog):
    settings(max_discount_percent=10)
    with pytest.raises(Conflict) as refusal:
        complete(
            lines=[{"product": "STK"}],
            discount_percent="20",
            payments=[{"method": "card"}],
        )
    assert refusal.value.code == "sale.discount_over_limit"
    settings(max_discount_percent=100, allow_discounts=False)
    with pytest.raises(Conflict) as refusal:
        complete(
            lines=[{"product": "STK"}],
            discount_amount=100,
            payments=[{"method": "card"}],
        )
    assert refusal.value.code == "sale.discounts_not_allowed"


def test_a_check_with_a_discount_when_discounts_were_turned_off(catalog):
    order = open_order({"product": "STK"})
    run("sale.order.set_discount", {"order_id": str(order.id), "discount_percent": "5"})
    settings(allow_discounts=False)
    with pytest.raises(Conflict) as refusal:
        complete(order_id=str(order.id), payments=[{"method": "card"}])
    assert refusal.value.code == "sale.discounts_not_allowed"


# ── Who charges ─────────────────────────────────────────────────────────────────────────────────


def test_an_employee_charges(catalog):
    sale = complete(ctx_for(EMPLOYEE, actor="ana"), lines=[{"product": "COF"}])
    assert Sale.objects.get(pk=sale.id).created_by == "ana"


def test_an_open_price_charged_loose_needs_its_permission(catalog):
    run(
        "sale.department.create",
        {"name": "Fruit", "tax_category_key": "product.super_reduced"},
    )
    with pytest.raises(PermissionDenied):
        complete(
            ctx_for(EMPLOYEE), open_lines=[{"department": "Fruit", "unit_price": 250}]
        )
    sale = complete(open_lines=[{"department": "Fruit", "unit_price": 250}])
    assert (sale.lines[0].name, sale.lines[0].tax_rate, sale.total) == (
        "Fruit",
        Decimal("4.00"),
        250,
    )


def test_charging_needs_its_permission(catalog):
    without = ctx_for(EMPLOYEE)
    without = type(without)(
        scope=without.scope,
        actor="x",
        permissions=frozenset({"sale.view_sale", "sale.add_sale"}),
    )
    with pytest.raises(PermissionDenied):
        complete(without, lines=[{"product": "COF"}])


# ── Prices without VAT, comps ───────────────────────────────────────────────────────────────────


def test_prices_without_vat_add_it_on_top(catalog):
    settings(default_tax_included=False)
    sale = complete(lines=[{"product": "STK"}], payments=[{"method": "card"}])
    assert (sale.subtotal, sale.tax_total, sale.total, sale.tax_included) == (
        1800,
        180,
        1980,
        False,
    )


def test_a_comp_charges_nothing_and_keeps_its_cost(catalog):
    sale = complete(
        lines=[
            {"product": "STK", "is_gift": True, "gift_reason": "birthday"},
            {"product": "WAT"},
        ]
    )
    steak, water = sale.lines
    assert (steak.line_total, steak.is_gift, steak.gift_reason) == (0, True, "birthday")
    assert (sale.total, sale.gift_total) == (110, 700)


def test_an_all_comp_charge_has_a_zero_payment(catalog):
    sale = complete(lines=[{"product": "STK", "is_gift": True}])
    assert sale.total == 0 and sale.payments == []


def test_a_rule_missing_for_a_category_refuses_the_charge(product):
    from apps.tax.models import TaxRule

    product("Book", "BOK", 2000, "product.super_reduced")
    TaxRule.objects.filter(category__key="product.super_reduced").update(
        is_active=False
    )
    with pytest.raises(Conflict) as refusal:
        complete(lines=[{"product": "BOK"}])
    assert refusal.value.code == "sale.no_tax_rule"


def test_a_bad_reference_is_refused_on_its_field(catalog):
    with pytest.raises(InvalidPayload):
        complete(open_lines=[{"department": "Ghost", "unit_price": 1}])


def test_a_sale_day_is_the_local_one(catalog, monkeypatch):
    # 00:30 in Madrid on the 19th is the 18th in UTC: the sale belongs to the 19th.
    instant = dt.datetime(2026, 9, 18, 22, 30, tzinfo=dt.UTC)
    monkeypatch.setattr(timezone, "now", lambda: instant)
    sale = complete(lines=[{"product": "COF"}])
    assert sale.number.startswith("20260919-") and sale.business_day == dt.date(
        2026, 9, 19
    )


# ── The attempt key belongs to one charge ───────────────────────────────────────────────────────


def test_an_attempt_key_reused_for_another_check_is_refused(catalog):
    first = open_order({"product": "COF"})
    second = open_order({"product": "WAT"})
    complete(order_id=str(first.id), payments=[{"method": "card"}])
    with pytest.raises(Conflict) as refusal:
        complete(order_id=str(second.id), payments=[{"method": "card"}])
    assert refusal.value.code == "sale.idempotency_key_reused"
    assert Order.objects.get(pk=second.id).status == "open"


def test_an_attempt_key_reused_for_other_lines_of_the_same_check_is_refused(catalog):
    order = open_order({"product": "COF"}, {"product": "WAT"})
    coffee, water = order.lines
    complete(order_id=str(order.id), line_ids=[str(coffee.id)], payments=[{"method": "card"}])
    with pytest.raises(Conflict) as refusal:
        complete(order_id=str(order.id), line_ids=[str(water.id)], payments=[{"method": "card"}])
    assert refusal.value.code == "sale.idempotency_key_reused"
    # The same lines again: the very sale.
    again = complete(order_id=str(order.id), line_ids=[str(coffee.id)], payments=[{"method": "card"}])
    assert again.already is True


def test_an_attempt_key_of_a_counter_sale_is_not_one_of_a_check(catalog):
    complete(lines=[{"product": "COF"}])
    with pytest.raises(Conflict) as refusal:
        complete(order_id=str(open_order({"product": "WAT"}).id))
    assert refusal.value.code == "sale.idempotency_key_reused"
    order = open_order({"product": "WAT"})
    complete(key="pos-attempt-0002", order_id=str(order.id))
    with pytest.raises(Conflict) as refusal:
        complete(key="pos-attempt-0002", lines=[{"product": "WAT"}])
    assert refusal.value.code == "sale.idempotency_key_reused"


# ── The cash limit of a check charged in parts (Ley 7/2012, art. 7.Uno.1, párrafo 2) ────────────


def test_no_cash_on_any_part_of_a_check_of_one_thousand_euros(product):
    product("Watch", "WCH", 60000, "product.generic")
    order = open_order({"product": "WCH"}, {"product": "WCH"})
    first, second = order.lines
    preview = run("sale.checkout.preview", {"order_id": str(order.id), "line_ids": [str(first.id)]})
    # The operation is the whole check: 1,200 €, though this part is 600 €.
    assert (preview.total, preview.operation_total) == (60000, 120000)
    with pytest.raises(Conflict) as refusal:
        complete(order_id=str(order.id), line_ids=[str(first.id)], payments=[cash(60000)])
    assert refusal.value.code == "sale.cash_limit_exceeded"
    complete(order_id=str(order.id), line_ids=[str(first.id)], payments=[{"method": "card"}])
    # What was charged counts too: the last part cannot go in cash either.
    with pytest.raises(Conflict) as refusal:
        complete(key="pos-attempt-0002", order_id=str(order.id), payments=[cash(60000)])
    assert refusal.value.code == "sale.cash_limit_exceeded"


def test_a_check_under_one_thousand_euros_takes_cash_in_parts(product):
    product("Ring", "RNG", 40000, "product.generic")
    order = open_order({"product": "RNG"}, {"product": "RNG"})
    first = order.lines[0]
    assert complete(order_id=str(order.id), line_ids=[str(first.id)], payments=[cash(40000)]).total == 40000
    assert complete(key="pos-attempt-0002", order_id=str(order.id), payments=[cash(40000)]).total == 40000
