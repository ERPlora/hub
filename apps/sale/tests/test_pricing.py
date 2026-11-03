"""The valuation of a charge (pricing.py): one rounding per magnitude, exact decimals, whole cents.

The closing of each fiscal key is tax's own (``calculate_tax``); here a fake closer built on tax's
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
    "zero.subject": [Decimal("0")],
    "service.health": [Decimal("0")],
}
#: The rule each category resolves to: its own id, and the qualification of the operation.
RULES = {key: f"rule-{key}" for key in [*RATES, "with.surcharge"]}
EXEMPT = {"service.health": "E1"}


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
    rule = RULES[category_key]
    return {
        "base": base,
        "tax": tax,
        "total": base + tax,
        "tax_category_key": category_key,
        "tax_rate_pct": sum(rates, Decimal(0)),
        "tax_country_code": "ES",
        "tax_region_code": None,
        "tax_rule_id": rule,
        "tax_kind": "vat",
        "tax_operation_class": "exempt" if category_key in EXEMPT else "subject",
        "tax_regime_key": "01",
        "tax_exempt_reason": EXEMPT.get(category_key, ""),
        "components": [
            {
                "rule_id": f"{rule}-{i}",
                "label": "vat" if i == 0 else "surcharge",
                "tax_type": "vat" if i == 0 else "surcharge",
                "rate_pct": rate,
                "base": base,
                "tax": quota,
            }
            for i, (rate, quota) in enumerate(zip(rates, quotas, strict=True))
        ],
    }


def entry(rate, base, tax, *, label="vat", tax_type="vat", qualification="subject", exempt_reason=""):
    """A row of the breakdown: one per fiscal key and component."""
    return {
        "rate_pct": Decimal(rate),
        "label": label,
        "tax_type": tax_type,
        "regime": "01",
        "qualification": qualification,
        "exempt_reason": exempt_reason,
        "base": base,
        "tax": tax,
    }


def line(price: int, quantity="1", category="product.generic", **more) -> LineIn:
    return LineIn(
        key=more.pop("key", None),
        unit_price=price,
        ratio=more.pop("ratio", Fraction(Decimal(quantity))),
        quantity=Decimal(quantity),
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
    assert result.breakdown == [entry("21", 200, 42), entry("10", 100, 10)]
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


def test_two_categories_of_one_fiscal_key_close_once_with_vat_included():
    # A 1.50 € dish (restaurant.food) and a 1.50 € drink (restaurant.drink), both at 10 %: one key (VAT,
    # general regime, subject, 10 %), one rounding over 3.00 € — base 2.73, VAT 0.27, as Invoicing
    # declares it — never 1.36 + 1.36 = 2.72 by category.
    result = value(
        [line(150, category="restaurant.food"), line(150, category="restaurant.drink")],
        tax_included=True,
        close=fake_close,
    )
    assert (result.total, result.subtotal, result.tax_total) == (300, 273, 27)
    assert result.breakdown == [entry("10", 273, 27)]
    dish, drink = result.lines
    assert dish.net_amount + drink.net_amount == 273
    assert all(item.net_amount + item.tax_amount == item.line_total == 150 for item in result.lines)
    # Each line keeps the rule of its own category.
    assert (dish.tax_rule_id, drink.tax_rule_id) == (
        "rule-restaurant.food",
        "rule-restaurant.drink",
    )
    assert [c["rule_id"] for c in drink.tax_components] == ["rule-restaurant.drink-0"]


def test_with_vat_included_each_line_takes_its_share_of_the_base_and_the_rest_is_its_tax():
    # As Invoicing closes a charge (fiscal.close_charged): the key's base is shared by the lines' amounts
    # (largest remainder, ties to the earlier) and each line's tax is its amount less its base. 273 over
    # two 1.50 € lines → 137 + 136, so the taxes are 13 + 14 (sharing the 27 of tax instead would give
    # 14 + 13 and bases 136 + 137: the same totals, other lines than the invoice's).
    result = value(
        [line(150, category="restaurant.food"), line(150, category="restaurant.drink")],
        tax_included=True,
        close=fake_close,
    )
    assert [(item.net_amount, item.tax_amount) for item in result.lines] == [(137, 13), (136, 14)]
    assert [item.tax_components[0]["tax"] for item in result.lines] == [13, 14]


def test_with_vat_included_and_a_surcharge_the_main_quota_goes_by_weight_and_the_surcharge_takes_the_rest():
    # 3.00 € at 21 % + 5.2 %: base 238, tax 62 (VAT 50, surcharge 12), over lines of 1.00 and 2.00.
    result = value(
        [line(100, category="with.surcharge"), line(200, category="with.surcharge")],
        tax_included=True,
        close=fake_close,
    )
    assert [(item.net_amount, item.tax_amount) for item in result.lines] == [(79, 21), (159, 41)]
    assert [[c["tax"] for c in item.tax_components] for item in result.lines] == [[17, 4], [33, 8]]


def test_two_categories_of_one_fiscal_key_close_once_without_vat():
    # 0.15 € + 0.15 € at 10 % on top: 0.02 + 0.02 by category, 0.03 once for the key.
    result = value(
        [line(15, category="restaurant.food"), line(15, category="restaurant.drink")],
        tax_included=False,
        close=fake_close,
    )
    assert (result.subtotal, result.tax_total, result.total) == (30, 3, 33)
    assert sum(item.tax_amount for item in result.lines) == 3
    assert result.breakdown == [entry("10", 30, 3)]


def test_the_same_rate_with_another_qualification_is_another_key():
    # 0 % subject and 0 % exempt (E1) are two entries of the breakdown, never one «0 %».
    result = value(
        [line(1000, category="zero.subject"), line(4000, category="service.health")],
        tax_included=True,
        close=fake_close,
    )
    assert result.breakdown == [
        entry("0", 1000, 0),
        entry("0", 4000, 0, qualification="exempt", exempt_reason="E1"),
    ]


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
        entry("21", 10000, 2100),
        entry("5.2", 10000, 520, label="surcharge", tax_type="surcharge"),
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


def test_the_ticket_discount_amount_is_what_the_ticket_discount_takes_off_be_it_a_percent_or_fixed():
    # hub#457: 2 × 1.50 + 5.50 with 10 % off the check: the ticket discount takes 0.85 off, not 0.
    result = value(
        [line(150, "2", "restaurant.drink"), line(550, category="restaurant.food")],
        tax_included=True,
        ticket_percent=Decimal("10"),
        close=fake_close,
    )
    assert (result.total, result.ticket_discount_amount) == (765, 85)
    # A fixed amount takes off just that.
    result = value([line(100), line(100), line(100)], tax_included=True, ticket_amount=30, close=fake_close)
    assert result.ticket_discount_amount == 30
    # Both: the percent first, then the fixed amount on what is left.
    result = value([line(1000), line(500)], tax_included=True, ticket_percent=Decimal("10"), ticket_amount=50, close=fake_close)
    assert (result.total, result.ticket_discount_amount) == (1300, 200)
    # Without a ticket discount there is nothing to say.
    assert value([line(1000)], tax_included=True, close=fake_close).ticket_discount_amount == 0


def test_the_ticket_discount_amount_leaves_out_the_line_discounts_comps_and_vouchers():
    # A line's own −50 % is the line's (it is already in its row); the ticket's 10 % comes off what is left.
    result = value(
        [line(1000, line_percent=Decimal("50")), line(1000)],
        tax_included=True,
        ticket_percent=Decimal("10"),
        close=fake_close,
    )
    assert (result.total, result.discount_amount, result.ticket_discount_amount) == (1350, 650, 150)
    # A comp and a line a voucher pays are worth nothing: the ticket takes nothing off them.
    result = value(
        [line(900, cost=400, is_gift=True), line(2500, covered=True), line(1000)],
        tax_included=True,
        ticket_percent=Decimal("10"),
        close=fake_close,
    )
    assert (result.total, result.ticket_discount_amount) == (900, 100)
    # Without VAT in the prices it is said as the lines are, before tax: 10 % of 10.00 + 5.00.
    result = value([line(1000), line(500)], tax_included=False, ticket_percent=Decimal("10"), close=fake_close)
    assert (result.subtotal, result.ticket_discount_amount) == (1350, 150)


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


def test_a_comp_keeps_its_cost_by_the_quantity_in_its_stock_unit_not_by_the_price_ratio():
    # «0.37 € per 100 ud» costing 0.20 € a unit: three comped are 0.60 € at cost, not 0.01 €.
    screws = line(37, "3", cost=20, is_gift=True, ratio=Fraction(3, 100))
    assert value([screws, line(100)], tax_included=True, close=fake_close).gift_total == 60
    # 250 g sold by the gram, priced per kilo, costing 0.01 € a gram: 2.50 € at cost.
    saffron = line(900, "250", cost=1, is_gift=True, ratio=Fraction(1, 4))
    assert value([saffron, line(100)], tax_included=True, close=fake_close).gift_total == 250


def test_a_line_paid_with_a_voucher_is_worth_nothing_and_is_neither_discount_nor_comp():
    # SALE-F27: the voucher was taxed when it was sold; the line it pays goes at 0,00 €.
    result = value(
        [line(2500, covered=True, cost=900), line(1000)],
        tax_included=True,
        close=fake_close,
    )
    haircut, shampoo = result.lines
    assert (haircut.net_amount, haircut.tax_amount, haircut.line_total) == (0, 0, 0)
    assert haircut.tax_rate == Decimal("21")
    assert (result.total, result.discount_amount, result.gift_total) == (1000, 0, 0)
    # It takes no share of a fixed ticket amount, and a ticket percent does not count it as a discount.
    result = value(
        [line(2500, covered=True), line(1000)],
        tax_included=True,
        ticket_amount=100,
        ticket_percent=Decimal("10"),
        close=fake_close,
    )
    assert [item.line_total for item in result.lines] == [0, 800]
    assert result.discount_amount == 200


def test_a_charge_paid_whole_with_vouchers_is_zero():
    result = value([line(2500, covered=True)], tax_included=True, close=fake_close)
    assert (result.total, result.subtotal, result.tax_total) == (0, 0, 0)


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


@pytest.mark.django_db
def test_the_real_closing_of_tax_closes_once_per_fiscal_key():
    from apps.sale.pricing import tax_closer

    result = value(
        [line(150, category="restaurant.food"), line(150, category="restaurant.drink")],
        tax_included=True,
        close=tax_closer(),
    )
    assert (result.total, result.subtotal, result.tax_total) == (300, 273, 27)
    (row,) = result.breakdown
    assert (row["rate_pct"], row["qualification"], row["regime"], row["base"], row["tax"]) == (
        Decimal("10.00"),
        "subject",
        "01",
        273,
        27,
    )
