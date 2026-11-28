"""The open checks and their lines: what the database refuses, how a check starts and when a line is live."""

from decimal import Decimal
from uuid import uuid7

from apps.sale.models.orders import Order, OrderLine
from apps.sale.tests.conftest import HUB_DB, refused

pytestmark = HUB_DB


def test_an_order_discount_is_a_percentage_and_a_line_quantity_is_positive():
    refused(lambda: Order.objects.create(discount_percent=Decimal("100.01")))
    order = Order.objects.create()
    refused(
        lambda: OrderLine.objects.create(
            order=order,
            position=1,
            name="Coffee",
            quantity=Decimal("0"),
            unit_price=150,
            tax_category_key="x",
        )
    )


def test_an_order_starts_open_at_version_one():
    order = Order.objects.create()
    assert order.status == Order.Status.OPEN
    assert order.version == 1
    assert order.provisional_total == 0


def test_an_order_line_is_live_until_removed_and_unpaid_until_a_sale_takes_it():
    order = Order.objects.create()
    line = OrderLine.objects.create(
        order=order,
        position=1,
        name="Coffee",
        quantity=Decimal("1"),
        unit_price=150,
        tax_category_key="restaurant.drink",
    )
    assert line.is_live and not line.is_fired and line.sale_id is None
    assert list(OrderLine.objects.live().unpaid()) == [line]


def test_a_line_may_be_a_service_and_may_be_paid_with_a_voucher_session():
    order = Order.objects.create()
    line = OrderLine.objects.create(
        order=order, position=1, name="Haircut", quantity=1, unit_price=2500, tax_category_key="service.generic"
    )
    assert (line.service_id, line.voucher_session_id, line.voucher_grant_id) == (None, None, None)
    assert (line.voucher_name, line.voucher_remaining, line.voucher_hold_until) == ("", None, None)
    assert line.paid_by_voucher is False
    line.voucher_session_id = uuid7()
    assert line.paid_by_voucher is True
