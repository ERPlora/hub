"""Sale and Taxes together, no mocks: every line is charged and declared with tax's own rule and
calculation (``apps.tax.queries.calculate_tax``), on the business day, in the business's country.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.utils import timezone, translation
from live.errors import Conflict

from apps.inventory.models import Product
from apps.sale.apps import SaleConfig
from apps.sale.tests.conftest import ctx_for, run
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


def test_the_breakdown_is_one_entry_per_fiscal_key_closed_once(product):
    # A dish and a drink at 10 % with VAT included are one key: 3.00 € closes once (2.73 + 0.27), never
    # 1.36 + 1.36 by category; an exempt service is its own key, with its cause.
    product("Tapa", "TAP", 150, "restaurant.food")
    product("Cane", "CAN", 150, "restaurant.drink")
    product("Physio", "PHY", 4000, "service.health")
    sale = charge(
        "tax-key-0002", {"product": "TAP"}, {"product": "CAN"}, {"product": "PHY"}
    )
    assert (sale.subtotal, sale.tax_total, sale.total) == (4273, 27, 4300)
    assert [
        (row.qualification, row.exempt_reason, row.regime, row.tax_type, row.rate_pct, row.base, row.tax)
        for row in sale.breakdown
    ] == [
        ("subject", "", "01", "vat", Decimal("10.00"), 273, 27),
        ("exempt", "E1", "01", "vat", Decimal("0.00"), 4000, 0),
    ]
    tapa, cane, _physio = sale.lines
    assert tapa.net_amount + cane.net_amount == 273
    assert tapa.line_total == cane.line_total == 150
    preview = run(
        "sale.checkout.preview",
        {"lines": [{"product": "TAP"}, {"product": "CAN"}]},
    )
    assert [(row.rate_pct, row.base, row.tax) for row in preview.breakdown] == [
        (Decimal("10.00"), 273, 27)
    ]


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


# The business's tax region (TAX-F11, pm#629 VF-17): a business of the Canary Islands charges IGIC and one of
# Ceuta or Melilla IPSI; the regional rule beats the national one, and without a region the national one applies.


def regional_rule(region, rate, tax_type, key="product.generic"):
    return run(
        "tax.rule.create",
        {
            "country_code": "ES",
            "region_code": region,
            "tax_category_key": key,
            "rate_pct": rate,
            "tax_type": tax_type,
        },
    )


@pytest.mark.parametrize(
    ("region", "rate", "tax_type"),
    [("ES-CN", "7", "igic"), ("ES-CE", "4", "ipsi"), ("ES-ML", "4", "ipsi")],
)
def test_a_business_of_a_region_charges_its_regional_rule(product, region, rate, tax_type):
    canary = regional_rule(region, rate, tax_type)
    run("tax.settings.update", {"region_code": region})
    product("Shirt", "SHI", 10000 + int(rate) * 100, "product.generic")
    sale = charge("tax-key-0001", {"product": "SHI"})
    (line,) = sale.lines
    assert (line.tax_rate, line.tax_rule_id, line.tax_country_code, line.tax_region_code) == (
        Decimal(rate),
        canary.id,
        "ES",
        region,
    )
    assert (sale.subtotal, sale.tax_total) == (10000, int(rate) * 100)
    assert [(row.tax_type, row.rate_pct, row.base, row.tax) for row in sale.breakdown] == [
        (tax_type, Decimal(rate), 10000, int(rate) * 100)
    ]


def test_without_a_region_the_business_charges_the_national_rule(product):
    regional_rule("ES-CN", "7", "igic")
    product("Shirt", "SHI", 12100, "product.generic")
    (line,) = charge("tax-key-0001", {"product": "SHI"}).lines
    assert (line.tax_rate, line.tax_region_code) == (Decimal("21.00"), "")


@pytest.mark.parametrize("region", ["ES-CN", "ES-CE", "ES-ML"])
def test_a_category_without_its_territorys_rule_is_not_charged_with_the_national_vat(product, region):
    # Outside the VAT territory the national rule of the category (restaurant.food, 10 % VAT) never stands in for
    # the missing IGIC or IPSI: the till refuses it as a category without any rule in the peninsula.
    from apps.sale.models import Sale

    regional_rule("ES-CN", "7", "igic")
    run("tax.settings.update", {"region_code": region})
    product("Menu", "MNU", 1100, "restaurant.food")
    run("sale.department.create", {"name": "Kitchen", "tax_category_key": "restaurant.food"})
    (section,) = run("sale.department.list", {}).rows
    assert section.tax_rate_pct is None
    for attempt in (
        lambda: run("sale.checkout.preview", {"lines": [{"product": "MNU"}]}),
        lambda: charge("tax-key-0001", {"product": "MNU"}),
    ):
        with pytest.raises(Conflict) as refusal:
            attempt()
        assert refusal.value.code == "sale.no_tax_rule"
    assert not Sale.objects.exists()


def test_the_preview_and_the_sections_follow_the_business_region(product):
    regional_rule("ES-CN", "7", "igic")
    run("tax.settings.update", {"region_code": "ES-CN"})
    run("sale.department.create", {"name": "Clothes", "tax_category_key": "product.generic"})
    (section,) = run("sale.department.list", {}).rows
    assert section.tax_rate_pct == Decimal("7.00")
    product("Shirt", "SHI", 10700, "product.generic")
    preview = run("sale.checkout.preview", {"lines": [{"product": "SHI"}]})
    assert (preview.subtotal, preview.tax_total) == (10000, 700)
    assert [(row.tax_type, row.rate_pct) for row in preview.breakdown] == [("igic", Decimal("7.00"))]


# The tax every sale screen names (the till, the sections, the settings): the business territory's, read from
# the one place that publishes it, Taxes' settings (``tax.settings.get``; Sales has no operation of its own).


@pytest.mark.parametrize("role", sorted(SaleConfig.role_permissions))
def test_every_role_that_sells_reads_the_territorys_tax_from_taxes(db, role):
    run("tax.settings.update", {"region_code": "ES-CN"})
    assert run("tax.settings.get", {}, ctx_for(role)).tax_kind == "igic"


@pytest.mark.parametrize(
    ("region", "language", "missing"),
    [
        (None, "en", "Its VAT is missing."),
        ("ES-CN", "en", "Its IGIC is missing."),
        ("ES-ML", "en", "Its IPSI is missing."),
        (None, "es", "Falta configurar su IVA."),
        ("ES-CN", "es", "Falta configurar su IGIC."),
    ],
)
def test_a_product_without_its_tax_says_the_territorys_tax_is_missing(product, region, language, missing):
    if region:
        run("tax.settings.update", {"region_code": region})
    product("Wax", "WAX", 500, "product.generic")
    Product.objects.filter(sku="WAX").update(tax_category=None)
    with translation.override(language), pytest.raises(Conflict) as refusal:
        run("sale.sale.complete", {"idempotency_key": "tax-key-0001", "lines": [{"product": "WAX"}]})
    assert refusal.value.code == "sale.tax_category_missing"
    assert str(refusal.value.message).endswith(missing)
