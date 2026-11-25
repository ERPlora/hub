"""The one resolution of a rate that sales and invoice share: which root rule applies to a country, a region, a
category and a date.

The cases are those of the current product's engine (``handler/src/lib.rs`` and ``erplora_guest_sdk::tax``).
"""

from datetime import date
from decimal import Decimal

import pytest
from live.errors import Conflict

from apps.tax import queries
from apps.tax.models import TaxRule

from .conftest import HUB_DB, TODAY, category, resolve, rule

pytestmark = HUB_DB


# Resolution: which root rule applies to (country, region, category, date)


def test_resolves_by_category(no_seed):
    rule(category("restaurant.food"), "10")
    generic = rule(category("product.generic"), "21")
    resolved = resolve("product.generic")
    assert resolved.root == generic
    assert resolved.rate_pct == Decimal("21.00")


def test_the_region_beats_the_country(no_seed):
    generic = category()
    national = rule(generic, "21")
    canary = rule(generic, "7", region="ES-CN", tax_type="igic")
    assert resolve(region="ES-CN").root == canary
    assert (
        resolve(region="ES-MD").root == national
    )  # a region without its own rule: the national one
    assert (
        resolve(region=None).root == national
    )  # without a region, a regional rule is never used


def test_a_rule_of_another_region_is_never_used(no_seed):
    # Spain holds VAT, IGIC and IPSI: another territory's rule is the wrong tax, not a worse answer.
    rule(category(), "7", region="ES-CN", tax_type="igic")
    assert resolve(region="ES-ML") is None
    assert resolve(region=None) is None


TERRITORIES_WITH_OWN_TAX = ["ES-CN", "ES-CE", "ES-ML"]


@pytest.mark.parametrize("region", TERRITORIES_WITH_OWN_TAX)
def test_a_territory_with_its_own_tax_never_takes_the_national_vat(no_seed, region):
    # The Canary Islands (IGIC), Ceuta and Melilla (IPSI) are outside the VAT territory: without a rule of
    # their own, a category has no rule there, as one without any rule in the peninsula, never the 21 % VAT.
    national = rule(category(), "21")
    assert resolve(region=region) is None
    assert queries.resolution.pick_root([national], region) is None
    with pytest.raises(Conflict) as refusal:
        queries.calculation.calculate_tax(amount=10_000, category_key="product.generic", country_code="ES", region_code=region, on=TODAY)
    assert refusal.value.code == "tax.no_rate"


def test_a_region_without_its_own_tax_and_the_whole_country_keep_the_national_rule(no_seed):
    national = rule(category(), "21")
    assert queries.resolution.pick_root([national], "ES-MD") == national
    assert queries.resolution.pick_root([national], None) == national
    assert queries.resolution.pick_root([national], "PT-20") == national  # the region names another country: VAT


@pytest.mark.parametrize(
    ("region", "expected"),
    [
        (None, {"product.generic": "21.00", "restaurant.food": "10.00"}),
        ("ES-MD", {"product.generic": "21.00", "restaurant.food": "10.00"}),
        ("ES-CN", {"product.generic": "7.00", "restaurant.food": None}),
        ("ES-CE", {"product.generic": None, "restaurant.food": None}),
        ("ES-ML", {"product.generic": None, "restaurant.food": None}),
    ],
)
def test_current_rates_never_fill_a_territory_with_the_national_vat(no_seed, region, expected):
    generic, food = category("product.generic"), category("restaurant.food")
    rule(generic, "21")
    rule(generic, "7", region="ES-CN", tax_type="igic")
    rule(food, "10")
    rates = queries.resolution.current_rates([generic, food], "ES", region, TODAY)
    found = {cat.key: (str(rates[cat.id].rate_pct) if rates[cat.id] else None) for cat in (generic, food)}
    assert found == expected


def test_the_country_must_match(no_seed):
    rule(category(), "21", country="ES")
    assert resolve(country="PT") is None


def test_country_and_region_are_read_in_any_case(no_seed):
    # Review: sales and invoice call these functions directly, without the schemas' capitals; the
    # current product did not tell «es» from «ES» either.
    generic = category()
    rule(generic, "21")
    canary = rule(generic, "7", region="ES-CN", tax_type="igic")
    assert resolve(country=" es ", region="es-cn").root == canary
    result = queries.calculation.calculate_tax(amount=10_000, category_key="product.generic", country_code="es", on=TODAY)
    assert (result["tax"], result["tax_country_code"], result["tax_region_code"]) == (2_100, "ES", None)
    regional = queries.calculation.calculate_tax(
        amount=10_000, category_key="product.generic", country_code="es", region_code="es-cn", on=TODAY
    )
    assert (regional["tax"], regional["tax_region_code"]) == (700, "ES-CN")


def test_validity_is_inclusive_and_picks_the_rule_of_the_date(no_seed):
    generic = category()
    old = rule(generic, "18", valid_from=date(2010, 7, 1), valid_to=date(2012, 8, 31))
    new = rule(generic, "21", valid_from=date(2012, 9, 1))
    assert resolve(on=TODAY).root == new
    assert resolve(on=date(2012, 9, 1)).root == new
    assert resolve(on=date(2012, 8, 31)).root == old
    assert resolve(on=date(2010, 6, 30)) is None


def test_an_inactive_rule_or_a_component_is_never_the_root(no_seed):
    generic = category()
    root = rule(generic, "21", is_active=False)
    rule(generic, "5.2", parent=root, tax_type="surcharge")
    assert resolve() is None


def test_inside_a_level_the_newest_start_wins_then_the_lowest_id(no_seed):
    # Overlaps cannot be saved through the operations; the order stays deterministic anyway.
    generic = category()
    rule(generic, "10")  # since always: the oldest start
    newest = rule(generic, "21", valid_from=date(2020, 1, 1))
    assert resolve().root == newest
    # Two roots of one slot with the same first day cannot be saved any more (the natural key
    # tax_rule_root_natural_key, review point 6): the id tie-break is checked on unsaved rows.
    twins = [TaxRule(valid_from=date(2020, 1, 1)) for _ in range(3)]
    assert queries.resolution.pick_root(twins, None) == min(twins, key=lambda r: r.pk.int)


def test_the_root_expands_into_its_components(no_seed):
    generic = category()
    root = rule(generic, "21", component_label="IVA")
    surcharge = rule(
        generic,
        "5.2",
        parent=root,
        tax_type="surcharge",
        component_label="Recargo de equivalencia",
    )
    rule(generic, "1", parent=root, tax_type="surcharge", is_active=False)
    rule(generic, "2", parent=root, tax_type="surcharge", valid_to=date(2020, 1, 1))
    resolved = resolve()
    assert resolved.components == [root, surcharge]
    assert resolved.rate_pct == Decimal("26.20")


def test_the_qualification_is_the_roots(no_seed):
    health = category("service.health")
    root = rule(
        health, "0", operation_class="exempt", exempt_reason="E1", tax_type="vat"
    )
    rule(health, "0", parent=root, tax_type="surcharge", operation_class="not_subject")
    resolved = resolve("service.health")
    assert (
        resolved.tax_kind,
        resolved.operation_class,
        resolved.regime_key,
        resolved.exempt_reason,
    ) == (
        "vat",
        "exempt",
        "01",  # an empty regime is the general one
        "E1",
    )


def test_the_exemption_cause_only_travels_on_an_exempt_rule(no_seed):
    rule(category(), "21", exempt_reason="E1", regime_key="02")
    resolved = resolve()
    assert (resolved.operation_class, resolved.regime_key, resolved.exempt_reason) == (
        "subject",
        "02",
        "",
    )


def test_only_tax_resolves_a_rule():
    # The rule of a line was resolved in three places and one charged what another declared.
    # Sales and Invoicing call resolve_tax / calculate_tax; no other app looks rules up by itself (a
    # frozen rule read back by its id is not a lookup).
    import re
    from pathlib import Path

    apps_dir = Path(__file__).resolve().parents[2]
    lookup = re.compile(r"TaxRule\.objects\.(?!in_bulk\b)\w+")
    offenders = [
        f"{path.relative_to(apps_dir)}:{number}"
        for path in sorted(apps_dir.glob("*/**/*.py"))
        if path.parts[len(apps_dir.parts)] != "tax" and "tests" not in path.parts
        for number, line in enumerate(path.read_text().splitlines(), 1)
        if lookup.search(line)
    ]
    assert offenders == []
