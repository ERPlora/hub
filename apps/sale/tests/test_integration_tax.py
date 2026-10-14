"""Sale and Taxes together, no mocks: every line is charged and declared with tax's own rule and
calculation (``apps.tax.queries.calculate_tax``), on the business day, in the business's country.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.sale.tests.conftest import run
from apps.tax.models import TaxRule

pytestmark = pytest.mark.django_db


def charge(key, *lines, **more):
    return run(
        "sale.sale.complete",
        {
            "idempotency_key": key,
            "lines": list(lines),
            "payments": [{"method": "card"}],
            **more,
        },
    )


def test_each_factory_rate_of_spain(product):
    product("Bread", "BRD", 104, "product.super_reduced")
    product("Menu", "MNU", 1100, "restaurant.food")
    product("Physio", "PHY", 4000, "service.health")
    product("Shirt", "SHI", 2420, "product.generic")
    sale = charge(
        "tax-key-0001",
        {"product": "BRD"},
        {"product": "MNU"},
        {"product": "PHY"},
        {"product": "SHI"},
    )
    rows = [
        (line.name, line.tax_rate, line.net_amount, line.tax_amount)
        for line in sale.lines
    ]
    assert rows == [
        ("Bread", Decimal("4.00"), 100, 4),
        ("Menu", Decimal("10.00"), 1000, 100),
        # An exempt service charges no tax.
        ("Physio", Decimal("0.00"), 4000, 0),
        ("Shirt", Decimal("21.00"), 2000, 420),
    ]
    assert sale.total == 104 + 1100 + 4000 + 2420
    assert all(
        line.tax_rule_id is not None and line.tax_country_code == "ES"
        for line in sale.lines
    )


def test_the_rule_in_force_on_the_business_day_is_the_one_charged(product):
    run("tax.category.create", {"key": "product.books", "name": "Books"})
    today = timezone.localdate()
    run(
        "tax.rule.create",
        {
            "country_code": "ES",
            "tax_category_key": "product.books",
            "rate_pct": "10",
            "valid_to": str(today - dt.timedelta(days=1)),
        },
    )
    new = run(
        "tax.rule.create",
        {
            "country_code": "ES",
            "tax_category_key": "product.books",
            "rate_pct": "4",
            "valid_from": str(today),
        },
    )
    product("Novel", "NOV", 2080, "product.books")
    (line,) = charge("tax-key-0001", {"product": "NOV"}).lines
    assert (line.tax_rate, line.tax_rule_id, line.net_amount) == (
        Decimal("4.00"),
        new.id,
        2000,
    )


def test_an_equivalence_surcharge_is_a_second_rate_of_the_breakdown(product):
    root = TaxRule.objects.get(
        country_code="ES", category__key="product.generic", parent__isnull=True
    )
    run(
        "tax.rule.create",
        {
            "country_code": "ES",
            "tax_category_key": "product.generic",
            "rate_pct": "5.2",
            "parent_id": str(root.id),
            "tax_type": "surcharge",
            "component_label": "RE",
        },
    )
    product("Shirt", "SHI", 12620, "product.generic")
    sale = charge("tax-key-0001", {"product": "SHI"})
    assert (sale.subtotal, sale.tax_total, sale.total) == (10000, 2620, 12620)
    assert [(row.rate_pct, row.base, row.tax) for row in sale.breakdown] == [
        (Decimal("21.00"), 10000, 2100),
        (Decimal("5.20"), 10000, 520),
    ]


def test_prices_without_vat_get_it_from_the_same_rule(product):
    run("sale.settings.update", {"default_tax_included": False})
    product("Shirt", "SHI", 2000, "product.generic")
    sale = charge("tax-key-0001", {"product": "SHI", "quantity": "3"})
    assert (sale.subtotal, sale.tax_total, sale.total) == (6000, 1260, 7260)


def test_the_preview_and_the_charge_agree_to_the_cent(product):
    product("Coffee", "COF", 99, "product.generic")
    product("Water", "WAT", 110, "restaurant.drink")
    order = run(
        "sale.order.open",
        {
            "lines": [
                {"product": "COF", "quantity": "3"},
                {"product": "WAT", "quantity": "7"},
            ]
        },
    )
    run(
        "sale.order.set_discount",
        {"order_id": str(order.id), "discount_percent": "7.5", "discount_amount": 13},
    )
    preview = run("sale.checkout.preview", {"order_id": str(order.id)})
    sale = run(
        "sale.sale.complete",
        {
            "idempotency_key": "tax-key-0001",
            "order_id": str(order.id),
            "payments": [{"method": "card"}],
        },
    )
    assert (
        preview.total,
        preview.subtotal,
        preview.tax_total,
        preview.discount_amount,
    ) == (sale.total, sale.subtotal, sale.tax_total, sale.discount_amount)
    assert (
        sum(line.line_total for line in sale.lines)
        == sale.total
        == sale.subtotal + sale.tax_total
    )
