"""The money of a tax and its calculation: ``split_amount``, ``tax.rate.calculate`` and ``calculate_tax``.

The money cases are those of the current product's engine (``handler/src/lib.rs`` and ``erplora_guest_sdk::tax``).
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import DatabaseError, connections
from django.utils import timezone
from live.errors import Conflict
from live.operations import current_alias

from apps.tax import queries

from .conftest import HUB_DB, TODAY, calculate, category, rule

pytestmark = HUB_DB


# Money: whole cents, exact decimals, half up


@pytest.mark.parametrize(
    ("value", "cents"),
    [("52.5", 53), ("52.4999", 52), ("-52.5", -53), ("0.5", 1), ("2100.21", 2100)],
)
def test_round_half_up(value, cents):
    assert queries.calculation.round_half_up(Decimal(value)) == cents


@pytest.mark.parametrize(
    ("amount", "rates", "included", "expected"),
    [
        (10_000, ["10"], False, (10_000, 1_000, [1_000])),
        (250, ["21"], False, (250, 53, [53])),  # 52.5 → 53, never 52.5
        (-250, ["21"], False, (-250, -53, [-53])),  # a refund rounds away from zero too
        (10_000, ["21", "5.2"], False, (10_000, 2_620, [2_100, 520])),
        # Tax included: the base is unwound and the quota is the difference, so the amount charged
        # never moves a cent (101 used to become 100: base 83, 83 × 21 % = 17).
        (101, ["21"], True, (83, 18, [18])),
        (12_620, ["21", "5.2"], True, (10_000, 2_620, [2_100, 520])),
        # The last component absorbs the cent: 12 621 / 1.262 = 10 001; 2 620 − round(10 001 × 21 %).
        (12_621, ["21", "5.2"], True, (10_001, 2_620, [2_100, 520])),
        (5_000, ["0"], True, (5_000, 0, [0])),
        (5_000, [], True, (5_000, 0, [])),
        # Review: the adjusting cent goes to the last component WITH a rate; a component at 0 % never
        # carries a quota (it used to take -1 here: base 98, 98 × 21 % = 21 > 20).
        (118, ["21", "0"], True, (98, 20, [20, 0])),
        (118, ["0", "21", "0"], True, (98, 20, [0, 20, 0])),
        (118, ["0", "0"], True, (118, 0, [0, 0])),
    ],
)
def test_split_amount(amount, rates, included, expected):
    base, tax, quotas = queries.calculation.split_amount(
        amount, [Decimal(r) for r in rates], tax_included=included
    )
    assert (base, tax, quotas) == expected
    assert sum(quotas) == tax


# tax.rate.calculate (TAX-F18) and calculate_tax (TAX-F19)


def test_calculate_a_simple_rate(no_seed):
    food = rule(category("restaurant.food"), "10")
    result = calculate(
        amount=10_000,
        tax_category_key="restaurant.food",
        date=TODAY,
        role="hub_employee",
    )
    assert result.model_dump() == {
        "base": 10_000,
        "tax": 1_000,
        "total": 11_000,
        "tax_category_key": "restaurant.food",
        "tax_rate_pct": Decimal("10.00"),
        "tax_country_code": "ES",
        "tax_region_code": None,
        "tax_rule_id": food.id,
        "tax_kind": "vat",
        "tax_operation_class": "subject",
        "tax_regime_key": "01",
        "tax_exempt_reason": "",
        "tax_included": False,
        "source": "rule",
        "date": TODAY,
        "components": [
            {
                "rule_id": food.id,
                "label": "vat",
                "tax_type": "vat",
                "rate_pct": Decimal("10.00"),
                "base": 10_000,
                "tax": 1_000,
            }
        ],
    }


def test_calculate_with_a_surcharge_and_tax_included(no_seed):
    generic = category()
    root = rule(generic, "21")
    surcharge = rule(
        generic,
        "5.2",
        parent=root,
        tax_type="surcharge",
        component_label="Recargo de equivalencia",
    )
    result = calculate(
        amount=12_621, tax_category_key="product.generic", tax_included=True, date=TODAY
    )
    assert (result.base, result.tax, result.total, result.tax_rate_pct) == (
        10_001,
        2_620,
        12_621,
        Decimal("26.20"),
    )
    assert [(c.rule_id, c.label, c.tax_type, c.tax) for c in result.components] == [
        (root.id, "vat", "vat", 2_100),
        (surcharge.id, "Recargo de equivalencia", "surcharge", 520),
    ]
    assert result.tax_kind == "vat"  # the tax is the root's, not «surcharge»


def test_a_canary_business_is_charged_igic(no_seed):
    generic = category()
    rule(generic, "21")
    canary = rule(generic, "7", region="ES-CN", tax_type="igic", regime_key="01")
    result = calculate(
        amount=10_000,
        tax_category_key="product.generic",
        region_code="ES-CN",
        date=TODAY,
    )
    assert (
        result.tax_rule_id,
        result.tax_kind,
        result.tax,
        result.tax_region_code,
    ) == (canary.id, "igic", 700, "ES-CN")


def test_an_exempt_service_charges_no_tax_and_says_why(no_seed):
    rule(category("service.health"), "0", operation_class="exempt", exempt_reason="E1")
    result = calculate(amount=5_000, tax_category_key="service.health", date=TODAY)
    assert (result.base, result.tax, result.total) == (5_000, 0, 5_000)
    assert (result.tax_operation_class, result.tax_exempt_reason) == ("exempt", "E1")


def test_without_a_rule_no_rate_is_guessed(no_seed):
    category("restaurant.food")
    with pytest.raises(Conflict) as excinfo:
        calculate(amount=10_000, tax_category_key="restaurant.food", date=TODAY)
    assert (excinfo.value.status, excinfo.value.code) == (409, "tax.no_rate")
    assert (
        str(excinfo.value.message)
        == "No tax rule applies to this category in this country."
    )
    # An unknown category is the same answer: there is no rule for it.
    with pytest.raises(Conflict):
        calculate(amount=10_000, tax_category_key="nothing.here", date=TODAY)


def test_zero_only_when_the_caller_asks_for_it(no_seed):
    result = calculate(
        amount=10_000,
        tax_category_key="restaurant.food",
        allow_missing_rate=True,
        date=TODAY,
    )
    assert (result.base, result.tax, result.total, result.tax_rate_pct) == (
        10_000,
        0,
        10_000,
        Decimal("0"),
    )
    assert (result.tax_rule_id, result.source, result.components) == (
        None,
        "fallback_zero",
        [],
    )
    assert (result.tax_operation_class, result.tax_kind, result.tax_regime_key) == (
        "subject",
        "vat",
        "01",
    )


def test_the_date_defaults_to_the_business_today(no_seed):
    today = timezone.localdate()
    rule(category(), "21", valid_from=today + timedelta(days=1))
    with pytest.raises(Conflict):
        calculate(amount=100, tax_category_key="product.generic")
    tomorrow = calculate(
        amount=100, tax_category_key="product.generic", date=today + timedelta(days=1)
    )
    assert tomorrow.tax == 21


def test_when_the_rules_cannot_be_read_the_calculation_stops(no_seed):
    # An outage is not «no rate», and allow_missing_rate must not turn it into 0 %.
    rule(category(), "21")
    with connections[current_alias()].cursor() as cursor:
        cursor.execute("ALTER TABLE tax_taxrule RENAME TO tax_taxrule_hidden")
    try:
        for allow in (False, True):
            with pytest.raises(DatabaseError):
                calculate(
                    amount=10_000,
                    tax_category_key="product.generic",
                    allow_missing_rate=allow,
                    date=TODAY,
                )
    finally:
        with connections[current_alias()].cursor() as cursor:
            cursor.execute("ALTER TABLE tax_taxrule_hidden RENAME TO tax_taxrule")
    assert (
        calculate(amount=10_000, tax_category_key="product.generic", date=TODAY).tax
        == 2_100
    )


def test_the_seeded_spanish_baseline_prices_a_sale():
    result = calculate(
        amount=10_000, tax_category_key="product.generic", country_code="ES", date=TODAY
    )
    assert (result.tax, result.source) == (2_100, "rule")
