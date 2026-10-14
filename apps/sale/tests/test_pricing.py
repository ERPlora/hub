"""The valuation of a charge (pricing.py): one rounding per magnitude, exact decimals, whole cents.

The closing of each tax category is tax's own (``calculate_tax``); here a fake closer built on tax's
pure ``split_amount`` keeps the arithmetic tests off the database, and the last tests run the real one.
"""

from decimal import Decimal
from fractions import Fraction

import pytest
from live.errors import Conflict

from apps.sale.pricing import (
    LineIn,
    allocate,
    half_up,
    line_amount,
    price_ratio,
    value,
)
from apps.tax.queries import split_amount

RATES = {
    "product.generic": [Decimal("21")],
    "restaurant.food": [Decimal("10")],
    "restaurant.drink": [Decimal("10")],
}


def fake_close(category_key: str, amount: int, tax_included: bool) -> dict:
    """What ``calculate_tax`` answers, for the categories of ``RATES`` (one component each but surcharge)."""
    if category_key == "with.surcharge":
        rates = [Decimal("21"), Decimal("5.2")]
    elif category_key in RATES:
        rates = RATES[category_key]
    else:
        raise Conflict(
            "No tax rule applies to this category in this country.", code="tax.no_rate"
        )
    base, tax, quotas = split_amount(amount, rates, tax_included=tax_included)
    return {
        "base": base,
        "tax": tax,
        "total": base + tax,
        "tax_category_key": category_key,
        "tax_rate_pct": sum(rates, Decimal(0)),
        "tax_country_code": "ES",
        "tax_region_code": None,
        "tax_rule_id": None,
        "components": [
            {
                "rule_id": None,
                "label": "vat" if i == 0 else "surcharge",
                "tax_type": "vat",
                "rate_pct": rate,
                "base": base,
                "tax": quota,
            }
            for i, (rate, quota) in enumerate(zip(rates, quotas, strict=True))
        ],
    }


def line(price: int, quantity="1", category="product.generic", **more) -> LineIn:
    return LineIn(
        key=more.pop("key", None),
        unit_price=price,
        ratio=Fraction(Decimal(quantity)),
        tax_category_key=category,
        **more,
    )


# ── The pieces ──────────────────────────────────────────────────────────────────────────────────


def test_half_up_rounds_a_half_away_from_zero():
    assert half_up(Fraction(5, 2)) == 3
    assert half_up(Fraction(49, 10)) == 5
    assert half_up(Fraction(41, 10)) == 4
    assert half_up(Fraction(0)) == 0


def test_allocate_by_largest_remainder_and_ties_to_the_earlier():
    assert allocate(10, [1, 1, 1]) == [4, 3, 3]
    assert allocate(100, [50, 30, 20]) == [50, 30, 20]
    assert allocate(1, [0, 5, 5]) == [0, 1, 0]
    assert allocate(7, [0, 0]) == [0, 0]
    assert sum(allocate(301, [123, 456, 789])) == 301


def test_the_price_ratio_converts_units_and_the_price_quantity():
    # 0.5 kg of something priced per kilo.
    assert price_ratio(Decimal("0.5"), (1, 1), (1, 1), Decimal("1")) == Fraction(1, 2)
    # 250 g of something priced per kilo: a gram is 1/1000 of the kilo.
    assert price_ratio(Decimal("250"), (1, 1000), (1, 1), Decimal("1")) == Fraction(
        1, 4
    )
    # 3 units of «0.37 € per 100 ud».
    assert price_ratio(Decimal("3"), (1, 1), (1, 1), Decimal("100")) == Fraction(3, 100)
    # 90 minutes priced per hour: a minute is 1/60 h.
    assert price_ratio(Decimal("90"), (1, 1), (60, 1), Decimal("1")) == Fraction(3, 2)


def test_a_line_amount_is_one_rounding_of_price_by_quantity_and_discounts():
    # Prawns at 12.00 €/kg × 0.5 kg.
    assert line_amount(1200, Fraction(1, 2)) == 600
    # 10 % off 1.80 is 1.62.
    assert line_amount(180, Fraction(1), line_percent=Decimal("10")) == 162
    # Line and ticket discounts compound: 1000 × 0.9 × 0.8.
    assert (
        line_amount(
            1000, Fraction(1), line_percent=Decimal("10"), ticket_percent=Decimal("20")
        )
        == 720
    )
    # 33.33 % off 5.00: 333.35 → 333.
    assert line_amount(500, Fraction(1), line_percent=Decimal("33.33")) == 333
    assert line_amount(900, Fraction(2), is_gift=True) == 0


# ── The valuation ───────────────────────────────────────────────────────────────────────────────


def test_prices_with_vat_split_each_category_once_and_every_line_squares():
    # A coffee at 1.21 × 2 at 21 % and a water at 1.10 at 10 %.
    result = value(
        [line(121, "2"), line(110, category="restaurant.drink")],
        tax_included=True,
        close=fake_close,
    )
    assert (result.total, result.subtotal, result.tax_total) == (352, 300, 52)
    coffee, water = result.lines
    assert (coffee.net_amount, coffee.tax_amount, coffee.line_total) == (200, 42, 242)
    assert (water.net_amount, water.tax_amount, water.line_total) == (100, 10, 110)
    assert result.breakdown == [
        {"rate_pct": Decimal("21"), "label": "vat", "base": 200, "tax": 42},
        {"rate_pct": Decimal("10"), "label": "vat", "base": 100, "tax": 10},
    ]
    assert result.discount_amount == 0 and result.gift_total == 0


def test_prices_without_vat_add_the_tax_on_top():
    result = value(
        [line(1000), line(500, category="restaurant.food")],
        tax_included=False,
        close=fake_close,
    )
    assert (result.subtotal, result.tax_total, result.total) == (1500, 260, 1760)
    assert [
        (item.net_amount, item.tax_amount, item.line_total) for item in result.lines
    ] == [(1000, 210, 1210), (500, 50, 550)]


def test_lines_of_one_category_share_its_base_by_weight():
    # Three 0.99 lines at 21 %: the category's base is rounded once (297 / 1.21 = 245.45 → 245).
    result = value([line(99), line(99), line(99)], tax_included=True, close=fake_close)
    assert result.subtotal == 245 and result.tax_total == 52 and result.total == 297
    assert sum(item.net_amount for item in result.lines) == 245
    assert all(
        item.net_amount + item.tax_amount == item.line_total == 99
        for item in result.lines
    )


def test_a_surcharge_is_a_second_component_over_the_same_base():
    result = value(
        [line(12620, category="with.surcharge")], tax_included=True, close=fake_close
    )
    (item,) = result.lines
    assert (item.net_amount, item.tax_amount, item.line_total) == (10000, 2620, 12620)
    assert [(c["rate_pct"], c["tax"]) for c in item.tax_components] == [
        (Decimal("21"), 2100),
        (Decimal("5.2"), 520),
    ]
    assert result.breakdown == [
        {"rate_pct": Decimal("21"), "label": "vat", "base": 10000, "tax": 2100},
        {"rate_pct": Decimal("5.2"), "label": "surcharge", "base": 10000, "tax": 520},
    ]


def test_a_ticket_percent_comes_off_every_line_and_is_reported_as_discount():
    result = value(
        [line(1000), line(500)],
        tax_included=True,
        ticket_percent=Decimal("10"),
        close=fake_close,
    )
    assert result.total == 1350
    assert result.discount_amount == 150


def test_a_fixed_ticket_amount_is_shared_by_weight_after_the_percents():
    # 3 × 1.00: 30 cents off, 10 each.
    result = value(
        [line(100), line(100), line(100)],
        tax_included=True,
        ticket_amount=30,
        close=fake_close,
    )
    assert [item.line_total for item in result.lines] == [90, 90, 90]
    assert result.total == 270 and result.discount_amount == 30
    # 10 cents over 3 lines: largest remainder, ties to the earlier one.
    result = value(
        [line(100), line(100), line(100)],
        tax_included=True,
        ticket_amount=10,
        close=fake_close,
    )
    assert [item.line_total for item in result.lines] == [96, 97, 97]


def test_a_fixed_amount_bigger_than_the_check_is_refused():
    with pytest.raises(Conflict) as refusal:
        value([line(100)], tax_included=True, ticket_amount=101, close=fake_close)
    assert refusal.value.code == "sale.discount_out_of_range"


def test_a_comp_is_charged_at_zero_and_its_cost_is_kept():
    result = value(
        [line(900, "2", cost=400, is_gift=True), line(250)],
        tax_included=True,
        close=fake_close,
    )
    comp, beer = result.lines
    assert (comp.net_amount, comp.tax_amount, comp.line_total) == (0, 0, 0)
    assert comp.tax_rate == Decimal("21")
    assert result.gift_total == 800
    assert result.total == 250
    # A comp is no discount and takes no share of a fixed amount.
    result = value(
        [line(900, is_gift=True), line(250)],
        tax_included=True,
        ticket_amount=50,
        close=fake_close,
    )
    assert [item.line_total for item in result.lines] == [0, 200]
    assert result.discount_amount == 50


def test_a_line_discount_counts_in_the_discount_amount():
    result = value(
        [line(1000, line_percent=Decimal("50"))], tax_included=True, close=fake_close
    )
    assert result.total == 500 and result.discount_amount == 500


def test_a_category_without_rule_is_refused_naming_the_line():
    with pytest.raises(Conflict) as refusal:
        value(
            [line(100, category="nowhere", name="Mystery")],
            tax_included=True,
            close=fake_close,
        )
    assert refusal.value.code == "sale.no_tax_rule"
    assert "Mystery" in refusal.value.message


def test_an_empty_charge_is_refused():
    with pytest.raises(Conflict) as refusal:
        value([], tax_included=True, close=fake_close)
    assert refusal.value.code == "sale.empty_sale"


@pytest.mark.django_db
def test_the_real_closing_of_tax():
    from apps.sale.pricing import tax_closer

    close = tax_closer()
    result = value(
        [line(121, "2"), line(110, category="restaurant.drink")],
        tax_included=True,
        close=close,
    )
    assert (result.total, result.subtotal, result.tax_total) == (352, 300, 52)
    coffee, water = result.lines
    assert coffee.tax_rule_id is not None and coffee.tax_country_code == "ES"
    assert water.tax_rate == Decimal("10.00")
