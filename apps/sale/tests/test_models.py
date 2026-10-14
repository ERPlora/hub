"""Models of the sale app: what the database itself refuses, and the small helpers the models carry."""

import datetime as dt
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import translation

from apps.sale.models import (
    Department,
    Order,
    OrderLine,
    PaymentMethod,
    QuickNote,
    Sale,
    SaleCounter,
    Settings,
    sale_number,
)
from apps.tax.models import TaxCategory

pytestmark = pytest.mark.django_db


def refused(make):
    with pytest.raises(IntegrityError), transaction.atomic():
        make()


def a_sale(**more) -> Sale:
    values = {
        "number": "20261014-0001",
        "business_day": dt.date(2026, 10, 14),
        "sequence": 1,
        "idempotency_key": "key-0001",
        "total": 100,
        "subtotal": 91,
        "tax_total": 9,
    }
    return Sale.objects.create(**(values | more))


def test_the_sale_number_is_the_day_and_a_counter_of_at_least_four_digits():
    day = dt.date(2026, 9, 1)
    assert sale_number(day, 7) == "20260901-0007"
    assert sale_number(day, 1000) == "20260901-1000"
    # A minimum width, never a ceiling: the 10.000th sale is not rewritten as 1000.
    assert sale_number(day, 10000) == "20260901-10000"
    assert sale_number(day, 1000000) == "20260901-1000000"


def test_a_sale_number_and_an_attempt_key_are_unique():
    a_sale()
    refused(lambda: a_sale(idempotency_key="other"))
    refused(lambda: a_sale(number="20261014-0002", sequence=2))


def test_amounts_are_never_negative():
    refused(lambda: a_sale(total=-1))
    refused(lambda: a_sale(subtotal=-1, number="x-2", idempotency_key="k2"))


def test_one_counter_per_business_day():
    SaleCounter.objects.create(day=dt.date(2026, 10, 14), last=1)
    refused(lambda: SaleCounter.objects.create(day=dt.date(2026, 10, 14), last=1))


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


def test_only_one_settings_row():
    Settings.objects.create()
    refused(lambda: Settings.objects.create())


def test_a_settings_row_has_the_factory_values():
    settings = Settings()
    assert (settings.allow_cash, settings.allow_card, settings.allow_transfer) == (
        True,
        True,
        False,
    )
    assert (settings.show_products, settings.show_services) == (True, True)
    assert settings.require_customer is False
    assert settings.allow_discounts is True
    assert settings.max_discount_percent == 100
    assert settings.enable_parked_tickets is True
    assert settings.default_tax_included is True
    assert settings.auto_invoice_with_tax_id is False
    assert settings.default_document_type == "ticket"
    assert settings.receipt_header == settings.receipt_footer == ""


def test_the_discount_cap_is_a_percentage():
    refused(lambda: Settings.objects.create(max_discount_percent=101))


def test_factory_payment_methods_read_in_the_active_language_until_renamed():
    cash = PaymentMethod.objects.get(is_system=True, type=PaymentMethod.Type.CASH)
    with translation.override("es"):
        assert cash.display_name == "Efectivo"
        cash.name = "Caja chica"
        assert cash.display_name == "Caja chica"
    own = PaymentMethod(name="Bizum", type=PaymentMethod.Type.OTHER)
    assert own.display_name == "Bizum"


def test_cash_takes_change_and_the_other_types_do_not():
    assert PaymentMethod(type=PaymentMethod.Type.CASH).requires_change is True
    for kind in (
        PaymentMethod.Type.CARD,
        PaymentMethod.Type.TRANSFER,
        PaymentMethod.Type.OTHER,
    ):
        assert PaymentMethod(type=kind).requires_change is False


def test_departments_and_quick_notes_are_deleted_logically():
    category = TaxCategory.objects.get(key="product.reduced")
    department = Department.objects.create(
        name="Fruit", tax_category=category, sort_order=10
    )
    note = QuickNote.objects.create(text="no salt", sort_order=10)
    assert department.is_deleted is False and department.deleted_at is None
    assert note.is_deleted is False and note.deleted_at is None
    # Two departments may share one tax category.
    Department.objects.create(name="Veg", tax_category=category)


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
