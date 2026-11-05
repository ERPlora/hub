"""Read operations of the tax app and the one resolution of a rate that sales and invoice share.

The money and resolution cases are those of the current product's engine (``handler/src/lib.rs`` and
``erplora_guest_sdk::tax``); the lists, those of its SQL batteries.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import DatabaseError, connection
from django.utils import timezone, translation
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.operations import get

from apps.tax import queries, schemas
from apps.tax.models import TaxAlias, TaxCategory, TaxRule, TaxSettings
from apps.tax.schemas import (
    AliasListIn,
    AliasPage,
    AliasResolveIn,
    AliasResolveOut,
    CalculateIn,
    CalculationOut,
    CategoryGetIn,
    CategoryListIn,
    CategoryOut,
    CategoryPage,
    RuleCountriesIn,
    RuleCountriesOut,
    RuleListIn,
    RulePage,
    RuleParentIn,
    RuleStatusIn,
    RuleStatusOut,
    SettingsGetIn,
    TaxSettingsOut,
)

from .conftest import ctx_for

pytestmark = pytest.mark.django_db

TODAY = date(2026, 6, 27)


def run(name, data, role="hub_admin", language="en"):
    return get(name)(ctx_for(role, language=language), data)


def category(key="product.generic", name=None, system=False, description=""):
    return TaxCategory.objects.create(
        key=key, name=name or key, is_system=system, description=description
    )


def rule(cat, rate="21", country="ES", region="", **fields):
    return TaxRule.objects.create(
        category=cat,
        country_code=country,
        region_code=region,
        rate_pct=Decimal(rate),
        **fields,
    )


def resolve(key="product.generic", country="ES", region=None, on=TODAY):
    return queries.resolve_tax(
        category_key=key, country_code=country, region_code=region, on=on
    )


# Declarations


@pytest.mark.parametrize(
    ("name", "input", "output", "expose_api"),
    [
        # expose_api as in the current product's manifest: the calculation and the status were not.
        ("tax.category.list", CategoryListIn, CategoryPage, True),
        ("tax.category.get", CategoryGetIn, CategoryOut, True),
        ("tax.rule.list", RuleListIn, RulePage, True),
        ("tax.rule.status", RuleStatusIn, RuleStatusOut, False),
        # The pickers of the rules screen: the roots a component may hang from, the countries in use.
        ("tax.rule.parent_candidates", RuleParentIn, RulePage, False),
        ("tax.rule.countries", RuleCountriesIn, RuleCountriesOut, False),
        ("tax.alias.list", AliasListIn, AliasPage, True),
        ("tax.alias.resolve", AliasResolveIn, AliasResolveOut, True),
        ("tax.rate.calculate", CalculateIn, CalculationOut, False),
        # The business's tax region (TAX-F11): what every calculation reads when it names no country.
        ("tax.settings.get", SettingsGetIn, TaxSettingsOut, False),
    ],
)
def test_declarations(name, input, output, expose_api):
    op = get(name)
    assert (op.kind, op.permission, op.input, op.output, op.expose_api) == (
        "query",
        "tax.view",
        input,
        output,
        expose_api,
    )
    # The assistant sees every read; a read carries no risk.
    assert isinstance(op.ai, dict) and op.ai["description"].strip() and set(op.ai) == {"description"}


def test_an_employee_reads_and_a_role_without_tax_does_not(no_seed):
    category()
    assert run("tax.category.list", CategoryListIn(), role="hub_employee").total == 1
    with pytest.raises(PermissionDenied):
        run("tax.category.list", CategoryListIn(), role="nobody")


# Money: whole cents, exact decimals, half up (ADR-0123 of the current product)


@pytest.mark.parametrize(
    ("value", "cents"),
    [("52.5", 53), ("52.4999", 52), ("-52.5", -53), ("0.5", 1), ("2100.21", 2100)],
)
def test_round_half_up(value, cents):
    assert queries.round_half_up(Decimal(value)) == cents


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
    base, tax, quotas = queries.split_amount(
        amount, [Decimal(r) for r in rates], tax_included=included
    )
    assert (base, tax, quotas) == expected
    assert sum(quotas) == tax


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
    assert queries.pick_root([national], region) is None
    with pytest.raises(Conflict) as refusal:
        queries.calculate_tax(amount=10_000, category_key="product.generic", country_code="ES", region_code=region, on=TODAY)
    assert refusal.value.code == "tax.no_rate"


def test_a_region_without_its_own_tax_and_the_whole_country_keep_the_national_rule(no_seed):
    national = rule(category(), "21")
    assert queries.pick_root([national], "ES-MD") == national
    assert queries.pick_root([national], None) == national
    assert queries.pick_root([national], "PT-20") == national  # the region names another country: VAT


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
    rates = queries.current_rates([generic, food], "ES", region, TODAY)
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
    result = queries.calculate_tax(amount=10_000, category_key="product.generic", country_code="es", on=TODAY)
    assert (result["tax"], result["tax_country_code"], result["tax_region_code"]) == (2_100, "ES", None)
    regional = queries.calculate_tax(
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
    assert queries.pick_root(twins, None) == min(twins, key=lambda r: r.pk.int)


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


# tax.rate.calculate (TAX-F18) and calculate_tax (TAX-F19)


def calculate(role="hub_admin", **params):
    return run("tax.rate.calculate", CalculateIn(**params), role=role)


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
    # taxes#82: an outage is not «no rate», and allow_missing_rate must not turn it into 0 %.
    rule(category(), "21")
    with connection.cursor() as cursor:
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
        with connection.cursor() as cursor:
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


# tax.category.list (TAX-F01)


def categories(language="en", **params):
    return run("tax.category.list", CategoryListIn(**params), language=language)


def test_empty_category_list(no_seed):
    assert categories().model_dump() == {
        "rows": [],
        "total": 0,
        "limit": 50,
        "offset": 0,
    }


def test_the_seeded_categories_with_their_rate_in_spain():
    page = categories(language="es")
    rows = {row.key: row for row in page.rows}
    assert [row.key for row in page.rows] == sorted(rows)  # ordered by key
    assert page.total == 11
    food, health = rows["restaurant.food"], rows["service.health"]
    assert (food.display_name, food.name, food.is_system) == (
        "Restauración — comida",
        "Restaurant — food",
        True,
    )
    assert (food.rate_pct, food.operation_class) == (Decimal("10.00"), "subject")
    assert (health.rate_pct, health.operation_class) == (Decimal("0.00"), "exempt")
    assert health.display_description.startswith("Asistencia prestada")


def test_the_rate_column_follows_the_country_and_the_region(no_seed):
    generic, food = category("product.generic"), category("restaurant.food")
    root = rule(generic, "21")
    rule(generic, "5.2", parent=root, tax_type="surcharge")
    rule(generic, "7", region="ES-CN", tax_type="igic")
    rule(food, "10")
    rates = lambda **where: {row.key: row.rate_pct for row in categories(**where).rows}  # noqa: E731
    assert rates() == {
        "product.generic": Decimal("26.20"),
        "restaurant.food": Decimal("10.00"),
    }
    # The Canary Islands never take the national VAT: a category without its IGIC has no rate there.
    assert rates(region_code="ES-CN") == {
        "product.generic": Decimal("7.00"),
        "restaurant.food": None,
    }
    assert rates(country_code="PT") == {
        "product.generic": None,
        "restaurant.food": None,
    }


def test_the_search_finds_the_stored_and_the_translated_texts(no_seed):
    category("restaurant.food", "Restaurant — food", system=True)
    category("service.health", "Service — healthcare (VAT exempt)", system=True)
    keys = lambda language, search: [  # noqa: E731
        r.key for r in categories(language=language, search=search).rows
    ]
    assert keys("es", "COMIDA") == ["restaurant.food"]  # the translated name, any case
    assert keys("es", "food") == ["restaurant.food"]  # the key (and the stored name)
    assert keys("es", "asistencia") == ["service.health"]  # the translated description
    assert keys("es", "healthcare") == ["service.health"]  # the stored name, as the current search
    assert keys("es", "nada") == []


def test_the_column_filters_read_what_the_column_shows(no_seed):
    # taxes#44: the description column shows the translated text; its filter reads that text.
    category("service.health", "Service — healthcare (VAT exempt)", system=True, description="Assistance by medics")
    category("product.books", "Libros", description="Solo papel")
    keys = lambda **where: [r.key for r in categories(language="es", **where).rows]  # noqa: E731
    assert keys(display_description="asistencia prestada") == ["service.health"]
    assert keys(display_description="Assistance") == []  # the stored English is not what is shown
    assert keys(display_description="papel") == ["product.books"]  # an own category, by its own text
    assert keys(display_name="sanitario") == ["service.health"]
    assert keys(name="healthcare") == ["service.health"]
    assert keys(key="books") == ["product.books"]
    assert keys() == ["product.books", "service.health"]  # no filter, no condition


def test_categories_sort_by_any_column_of_the_screen(no_seed):
    category("product.a", "Zeta")
    category("product.b", "Alfa")
    category("product.c", "Media", system=True)
    keys = lambda **order: [r.key for r in categories(**order).rows]  # noqa: E731
    assert keys() == ["product.a", "product.b", "product.c"]
    assert keys(sort="key", dir="desc") == ["product.c", "product.b", "product.a"]
    assert keys(sort="display_name") == ["product.b", "product.c", "product.a"]
    assert keys(sort="is_system", dir="desc")[0] == "product.c"


def test_only_active_categories_are_listed_and_the_row_says_it(no_seed):
    category("product.a")
    TaxCategory.objects.create(key="product.old", name="Old", is_active=False)
    page = categories()
    assert [(r.key, r.is_active) for r in page.rows] == [("product.a", True)]
    assert page.total == 1


def test_an_own_category_is_found_by_its_own_text(no_seed):
    category("product.books", "Libros y revistas", description="Solo papel")
    category("restaurant.food", "Restaurant — food", system=True)
    assert [r.key for r in categories(language="es", search="revistas").rows] == [
        "product.books"
    ]
    assert [r.key for r in categories(language="es", search="papel").rows] == [
        "product.books"
    ]
    assert [r.key for r in categories(is_system=False).rows] == ["product.books"]
    assert [r.key for r in categories(is_system=True).rows] == ["restaurant.food"]


def test_category_pages_are_stable(no_seed):
    for n in range(5):
        category(f"product.p{n}")
    pages = [categories(limit=2, offset=offset) for offset in (0, 2, 4)]
    assert [row.key for page in pages for row in page.rows] == [
        f"product.p{n}" for n in range(5)
    ]
    assert [(page.total, len(page.rows)) for page in pages] == [(5, 2), (5, 2), (5, 1)]


# tax.category.get


def test_get_a_category_by_its_key():
    food = run(
        "tax.category.get",
        CategoryGetIn(key="restaurant.food"),
        role="hub_employee",
        language="es",
    )
    assert (food.key, food.display_name, food.is_system) == (
        "restaurant.food",
        "Restauración — comida",
        True,
    )


def test_get_a_missing_category(no_seed):
    with pytest.raises(NotFound) as excinfo:
        run("tax.category.get", CategoryGetIn(key="product.books"))
    assert str(excinfo.value.message) == "This tax category does not exist."


# tax.rule.list (TAX-F03)


def rules(language="en", **params):
    return run("tax.rule.list", RuleListIn(**params), language=language)


def test_the_rule_row(no_seed):
    health = category(
        "service.health", "Service — healthcare (VAT exempt)", system=True
    )
    exempt = rule(
        health,
        "0",
        operation_class="exempt",
        exempt_reason="E1",
        valid_from=date(2012, 9, 1),
    )
    [row] = rules(language="es").rows
    assert row.model_dump() == {
        "id": exempt.id,
        "country_code": "ES",
        "region_code": None,
        "tax_category_key": "service.health",
        "tax_category_name": "Servicio — sanitario (exento de IVA)",
        "rate_pct": Decimal("0.00"),
        "tax_type": "vat",
        "operation_class": "exempt",
        "exempt_reason": "E1",
        "regime_key": None,
        "parent_id": None,
        "component_label": None,
        "valid_from": date(2012, 9, 1),
        "valid_to": None,
        "is_active": True,
        "updated_at": exempt.updated_at,
    }


def test_active_rules_by_default_and_the_inactive_on_request(no_seed):
    generic = category()
    active = rule(generic, "21", valid_from=date(2020, 1, 1))
    inactive = rule(generic, "18", valid_to=date(2019, 12, 31), is_active=False)
    assert [row.id for row in rules().rows] == [active.id]
    assert [row.id for row in rules(status="inactive").rows] == [inactive.id]
    assert {row.id for row in rules(status="all").rows} == {active.id, inactive.id}


def test_rule_filters(no_seed):
    generic, food = category("product.generic"), category("restaurant.food")
    spain = rule(generic, "21")
    canary = rule(generic, "7", region="ES-CN", tax_type="igic")
    portugal = rule(generic, "23", country="PT")
    estonia = rule(food, "22", country="EE")
    exempt = rule(food, "0", operation_class="exempt")
    ids = lambda **where: {row.id for row in rules(**where).rows}  # noqa: E731
    assert ids(country_code="ES") == {
        spain.id,
        canary.id,
        exempt.id,
    }  # whole code: never EE
    assert ids(region_code="cn") == {canary.id}  # a fragment of the region
    assert ids(tax_category_key="restaurant.food") == {estonia.id, exempt.id}
    assert ids(tax_type="igic") == {canary.id}
    assert ids(operation_class="exempt") == {exempt.id}
    assert ids() == {
        spain.id,
        canary.id,
        portugal.id,
        estonia.id,
        exempt.id,
    }  # no filter, no condition


def test_rule_search_by_category_or_country(no_seed):
    food = category("restaurant.food", "Restaurant — food", system=True)
    on_food = rule(food, "10")
    on_generic = rule(category("product.generic"), "23", country="PT")
    ids = lambda search, language="en": {
        row.id for row in rules(search=search, language=language).rows
    }  # noqa: E731
    assert ids("food") == {on_food.id}
    assert ids("comida", "es") == {on_food.id}
    assert ids("pt") == {on_generic.id}


def test_a_component_comes_right_after_its_root(no_seed):
    generic = category("product.generic")
    first = rule(generic, "21", valid_to=date(2026, 12, 31))
    second = rule(generic, "22", valid_from=date(2027, 1, 1))
    surcharge = rule(generic, "5.2", parent=first, tax_type="surcharge")
    assert [row.id for row in rules().rows] == [first.id, surcharge.id, second.id]


def test_rule_pages_are_stable(no_seed):
    generic = category()
    created = [
        rule(generic, "21", country=country)
        for country in ("AT", "BE", "DE", "FR", "IT")
    ]
    pages = [rules(limit=2, offset=offset) for offset in (0, 2, 4)]
    assert [row.id for page in pages for row in page.rows] == [r.id for r in created]
    assert pages[0].total == 5


# tax.rule.status (TAX-F17)


def status(**params):
    return run("tax.rule.status", RuleStatusIn(**params))


def test_the_seeded_spanish_baseline_configures_a_spanish_business():
    assert status(country_code="ES").model_dump() == {
        "country_code": "ES",
        "matching_rules": 11,
        "configured": True,
    }
    # Without a stated country, every active root rule counts: no false «you are missing your taxes».
    assert status().model_dump() == {
        "country_code": None,
        "matching_rules": 11,
        "configured": True,
    }
    # A French business carrying only the Spanish rules is not configured.
    assert status(country_code="fr").model_dump() == {
        "country_code": "FR",
        "matching_rules": 0,
        "configured": False,
    }


def test_what_counts_as_configured(no_seed):
    today = timezone.localdate()
    generic = category()
    root = rule(generic, "21", valid_to=today)  # its last day is today: still in force
    rule(
        generic, "5.2", parent=root, tax_type="surcharge"
    )  # a component never counts on its own
    # Expired; with a first day of its own: «since always» is the root above's key (review point 6).
    rule(generic, "18", valid_from=date(2010, 1, 1), valid_to=today - timedelta(days=1))
    rule(generic, "25", valid_from=today + timedelta(days=1))  # not yet
    rule(category("product.x"), "21", is_active=False)
    # Exempt and IGIC rules count: a physiotherapist or a Canary business is configured.
    rule(category("service.health"), "0", operation_class="exempt")
    rule(category("product.y"), "7", region="ES-CN", tax_type="igic")
    spain = status(country_code="ES")
    assert (spain.matching_rules, spain.configured) == (3, True)
    # A country without a rule in force is not configured: the till could not price a sale there.
    portugal = status(country_code="PT")
    assert (portugal.matching_rules, portugal.configured) == (0, False)
    # Without the business's country, any country's rule counts.
    anywhere = status()
    assert (anywhere.matching_rules, anywhere.configured) == (3, True)


def test_nothing_in_force_is_not_configured(no_seed):
    # TAX-F17: no rule at all, or only ones not in force today, is «missing your taxes».
    assert (status().matching_rules, status().configured) == (0, False)
    rule(category(), "21", is_active=False)
    rule(category("product.x"), "21", valid_from=timezone.localdate() + timedelta(days=1))
    assert (status().matching_rules, status().configured) == (0, False)


# tax.alias.list (TAX-F13)


def aliases(**params):
    return run("tax.alias.list", AliasListIn(**params))


def test_the_seeded_aliases():
    page = aliases(limit=100)
    assert page.total == 18
    assert [row.alias for row in page.rows] == sorted(row.alias for row in page.rows)
    beer = next(row for row in page.rows if row.alias == "beer")
    assert (beer.tax_category_key, beer.tax_category_name, beer.source) == (
        "restaurant.alcohol",
        "Restaurant — alcohol",
        "shipped",
    )


def test_alias_search_and_filters(no_seed):
    food, books = category("restaurant.food"), category("product.books")
    TaxAlias.objects.create(alias="meal", category=food, source="shipped")
    TaxAlias.objects.create(alias="comida casera", category=food)
    TaxAlias.objects.create(alias="libros", category=books)
    names = lambda **where: [row.alias for row in aliases(**where).rows]  # noqa: E731
    assert names(search="COMIDA") == ["comida casera"]
    assert names(search="books") == ["libros"]  # the category key
    assert names(tax_category_key="restaurant.food") == ["comida casera", "meal"]
    assert names(source="learned") == ["comida casera", "libros"]


# tax.alias.resolve (TAX-F15): key, then name (in both languages), then alias


def resolved(text, language="en"):
    out = run("tax.alias.resolve", AliasResolveIn(text=text), language=language)
    return (out.text, out.tax_category_key, out.matched_by)


def test_resolve_by_key_name_or_alias():
    assert resolved(" Restaurant.Food ") == (
        "restaurant.food",
        "restaurant.food",
        "key",
    )
    assert resolved("Restaurant — food") == (
        "restaurant — food",
        "restaurant.food",
        "name",
    )
    # The translated name is recognised whatever the language of the reader (a CSV in Spanish).
    assert resolved("restauración — comida", language="en")[1:] == (
        "restaurant.food",
        "name",
    )
    assert resolved("BEER") == ("beer", "restaurant.alcohol", "alias")
    assert resolved("cerveza artesana") == ("cerveza artesana", None, None)


def test_an_own_category_is_recognised_by_its_name(no_seed):
    category("product.books", "Libros  y Revistas")
    assert resolved("libros y revistas")[1:] == ("product.books", "name")


def test_the_key_wins_over_an_alias_with_the_same_text(no_seed):
    generic, food = category("product.generic"), category("restaurant.food")
    TaxAlias.objects.create(alias="product.generic", category=food)
    assert resolved("product.generic")[1:] == (generic.key, "key")


def test_a_text_that_matches_nothing_is_never_a_similar_category(no_seed):
    category("restaurant.food", "Restaurant — food", system=True)
    assert resolved("restaurant")[1:] == (None, None)
    assert resolved(str(uuid.uuid7()))[1:] == (None, None)


# Parity with the current screens: lookups by name, filters, sort and the active rows


def test_get_a_category_by_its_name_or_an_alias():
    for text in ("Restauración — comida", "Restaurant — food", "pizza"):
        assert run("tax.category.get", CategoryGetIn(key=text)).key == "restaurant.food"


def test_calculate_naming_the_category_by_voice():
    result = calculate(amount=10_000, tax_category_key="Restauración — comida", date=TODAY)
    assert (result.tax_category_key, result.tax) == ("restaurant.food", 1_000)


def test_rule_filters_of_the_screen(no_seed):
    generic = category("product.generic")
    root = rule(generic, "21", regime_key="02")
    surcharge = rule(generic, "5.2", parent=root, tax_type="surcharge")
    reduced = rule(category("product.reduced"), "10")
    exempt = rule(category("service.health"), "0", operation_class="exempt", exempt_reason="E1")
    ids = lambda **where: {row.id for row in rules(**where).rows}  # noqa: E731
    assert ids(rate_min="5", rate_max="10") == {surcharge.id, reduced.id}
    assert ids(rate_min="21") == {root.id}
    assert ids(parent_id=root.id) == {surcharge.id}
    assert ids(regime_key="02") == {root.id}
    assert ids(search="exempt") == {exempt.id}  # the qualification is searchable, as before


def test_rules_sort_by_any_column_of_the_screen(no_seed):
    generic = category("product.generic")
    low = rule(generic, "4", country="FR", valid_from=date(2020, 1, 1))
    high = rule(generic, "21", country="ES")
    mid = rule(generic, "10", country="PT", valid_from=date(2010, 1, 1))
    order = lambda **sort: [row.id for row in rules(**sort).rows]  # noqa: E731
    assert order(sort="rate_pct") == [low.id, mid.id, high.id]
    assert order(sort="rate_pct", dir="desc") == [high.id, mid.id, low.id]
    assert order(sort="country_code", dir="desc") == [mid.id, low.id, high.id]
    assert order(sort="valid_from") == [mid.id, low.id, high.id]  # empty («since always») last


def test_aliases_filter_sort_and_only_active(no_seed):
    food, books = category("restaurant.food"), category("product.books")
    TaxAlias.objects.create(alias="meal", category=food, source="shipped")
    TaxAlias.objects.create(alias="comida casera", category=food)
    TaxAlias.objects.create(alias="libros", category=books)
    TaxAlias.objects.create(alias="old", category=books, is_active=False)
    names = lambda **where: [row.alias for row in aliases(**where).rows]  # noqa: E731
    assert names(alias="casera") == ["comida casera"]
    assert names(sort="tax_category_key", dir="desc") == ["comida casera", "meal", "libros"]
    assert names(sort="source") == ["comida casera", "libros", "meal"]
    assert all(row.is_active for row in aliases().rows) and aliases().total == 3


def test_resolve_reads_only_active_categories_and_aliases(no_seed):
    TaxCategory.objects.create(key="product.old", name="Old", is_active=False)
    TaxAlias.objects.create(alias="vieja", category=category("product.new"), is_active=False)
    assert resolved("product.old")[1:] == (None, None)
    assert resolved("old")[1:] == (None, None)
    assert resolved("vieja")[1:] == (None, None)


# tax.rule.parent_candidates (TAX-F06): what the «Root rule» picker offers is what the server accepts


def candidates(**params):
    return run("tax.rule.parent_candidates", RuleParentIn(**params))


def test_the_roots_of_the_slot_whatever_their_dates_and_never_a_component(no_seed):
    food = category("restaurant.food")
    current = rule(food, "10", valid_from=date(2012, 9, 1), valid_to=date(2026, 12, 31))
    # TAX-F07 then TAX-F06: the new rate from 2027 is a root a surcharge may hang from today.
    future = rule(food, "12", valid_from=date(2027, 1, 1))
    deactivated = rule(food, "9", valid_from=date(2000, 1, 1), valid_to=date(2001, 1, 1), is_active=False)
    rule(food, "1.4", parent=current, tax_type="surcharge")  # a component: never a root
    rule(food, "7", region="ES-CN", tax_type="igic")  # another region
    rule(food, "13", country="PT")  # another country
    rule(category("product.generic"), "21")  # another category
    page = candidates(country_code="es", tax_category_key="restaurant.food")
    assert {row.id for row in page.rows} == {current.id, future.id, deactivated.id}
    assert page.total == 3
    # The active ones first, the newest first among them.
    assert [row.id for row in page.rows] == [future.id, current.id, deactivated.id]


def test_a_region_names_its_own_slot_and_a_category_may_be_named_by_its_name(no_seed):
    food = category("restaurant.food", name="Restaurant — food")
    canary = rule(food, "7", region="ES-CN", tax_type="igic")
    rule(food, "10")
    page = candidates(country_code="ES", region_code="es-cn", tax_category_key="Restaurant — food")
    assert [row.id for row in page.rows] == [canary.id]
    assert candidates(country_code="ES", tax_category_key="no such category").total == 0


def test_a_root_without_tax_only_takes_a_component_at_zero(no_seed):
    health = category("service.health")
    exempt = rule(health, "0", operation_class="exempt")
    assert candidates(country_code="ES", tax_category_key="service.health").total == 0
    assert candidates(country_code="ES", tax_category_key="service.health", rate_pct="5.2").total == 0
    zero = candidates(country_code="ES", tax_category_key="service.health", rate_pct="0")
    assert [row.id for row in zero.rows] == [exempt.id]


def test_the_server_accepts_as_a_parent_exactly_what_the_picker_offers(no_seed):
    """One predicate: every root offered takes the component, every root left out is refused (409)."""
    from apps.tax.schemas import RuleIn

    food = category("restaurant.food")
    offered = [rule(food, "10", valid_from=date(2012, 9, 1)), rule(food, "12", valid_from=date(2027, 1, 1))]
    left_out = [
        rule(food, "7", region="ES-CN", tax_type="igic"),
        rule(food, "0", valid_from=date(2000, 1, 1), operation_class="exempt"),
    ]
    page = candidates(country_code="ES", tax_category_key="restaurant.food", rate_pct="1.4")
    assert {row.id for row in page.rows} == {root.id for root in offered}
    for root in offered:
        made = get("tax.rule.create")(
            ctx_for(),
            RuleIn(country_code="ES", tax_category_key="restaurant.food", rate_pct="1.4", tax_type="surcharge", parent_id=root.id),
        )
        assert made.parent_id == root.id
    for root in left_out:
        with pytest.raises(Conflict):
            get("tax.rule.create")(
                ctx_for(),
                RuleIn(country_code="ES", tax_category_key="restaurant.food", rate_pct="1.4", tax_type="surcharge", parent_id=root.id),
            )


# tax.rule.countries (TAX-F03, TAX-F11): the countries the Country filter offers


def test_the_countries_of_the_business_rules_once_each_sorted(no_seed):
    food = category("restaurant.food")
    rule(food, "10")
    rule(food, "7", region="ES-CN", tax_type="igic")
    rule(food, "13", country="PT")
    rule(food, "20", country="FR", is_active=False)
    assert run("tax.rule.countries", RuleCountriesIn()).countries == ["ES", "FR", "PT"]
    assert run("tax.rule.countries", RuleCountriesIn(status="active")).countries == ["ES", "PT"]
    assert run("tax.rule.countries", RuleCountriesIn(status="inactive")).countries == ["FR"]


def test_the_seeded_business_sells_in_spain():
    assert run("tax.rule.countries", RuleCountriesIn(), role="hub_employee").countries == ["ES"]



def test_only_tax_resolves_a_rule():
    # hub#295: the rule of a line was resolved in three places and one charged what another declared.
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


# The business's jurisdiction (TAX-F11, pm#629 VF-17): its country and the region it keeps in Taxes. Every
# calculation that names no country reads it: sales and invoice call these functions without one.


def keep_region(region):
    TaxSettings.objects.update_or_create(singleton=True, defaults={"region_code": region})


def test_the_business_is_the_whole_of_spain_until_it_keeps_a_region(no_seed):
    assert queries.business_jurisdiction() == ("ES", None)
    keep_region("ES-CN")
    assert queries.business_jurisdiction() == ("ES", "ES-CN")


def test_a_calculation_without_a_country_is_in_the_business_jurisdiction(no_seed):
    generic = category()
    national = rule(generic, "21")
    canary = rule(generic, "7", region="ES-CN", tax_type="igic")
    assert queries.resolve_tax(category_key="product.generic", on=TODAY).root == national
    keep_region("ES-CN")
    assert queries.resolve_tax(category_key="product.generic", on=TODAY).root == canary
    result = queries.calculate_tax(amount=10_000, category_key="product.generic", on=TODAY)
    assert (result["tax"], result["tax_kind"], result["tax_country_code"], result["tax_region_code"]) == (
        700,
        "igic",
        "ES",
        "ES-CN",
    )
    # Naming a country asks for that jurisdiction alone: the whole of Spain is the national rule.
    national_only = queries.resolve_tax(category_key="product.generic", country_code="ES", on=TODAY)
    assert national_only.root == national


def test_the_calculation_and_the_rate_column_default_to_the_business_jurisdiction(no_seed):
    generic = category()
    rule(generic, "21")
    rule(generic, "7", region="ES-CN", tax_type="igic")
    keep_region("ES-CN")
    result = calculate(amount=10_000, tax_category_key="product.generic", date=TODAY, role="hub_employee")
    assert (result.tax, result.tax_kind, result.tax_country_code, result.tax_region_code) == (
        700,
        "igic",
        "ES",
        "ES-CN",
    )
    asked = calculate(amount=10_000, tax_category_key="product.generic", country_code="ES", date=TODAY)
    assert (asked.tax, asked.tax_region_code) == (2_100, None)
    assert {row.key: row.rate_pct for row in categories().rows} == {"product.generic": Decimal("7.00")}
    assert {row.key: row.rate_pct for row in categories(country_code="ES").rows} == {
        "product.generic": Decimal("21.00")
    }


def test_read_the_business_tax_settings(no_seed):
    read = run("tax.settings.get", SettingsGetIn(), role="hub_employee")
    assert read.model_dump() == {
        "country_code": "ES",
        "region_code": None,
        "regions": ["ES-CN", "ES-CE", "ES-ML"],
        "tax_kind": "vat",
        "updated_at": None,
    }
    keep_region("ES-ML")
    kept = run("tax.settings.get", SettingsGetIn())
    assert (kept.region_code, kept.tax_kind, kept.updated_at is not None) == ("ES-ML", "ipsi", True)


@pytest.mark.parametrize(
    ("region", "tax_kind"),
    [("ES-CN", "igic"), ("ES-CE", "ipsi"), ("ES-ML", "ipsi"), ("", "vat")],
)
def test_the_settings_say_the_tax_of_the_business_territory(no_seed, region, tax_kind):
    # TAX-F11: the one place every screen reads which tax the business's sales are declared with.
    keep_region(region)
    assert run("tax.settings.get", SettingsGetIn(), role="hub_employee").tax_kind == tax_kind


def test_each_territory_tax_has_its_short_name(no_seed):
    # What a message names a territory's tax by (the till's «Its IGIC is missing»), in the reader's language.
    assert set(schemas.TAX_KIND_NAMES) == {"vat", "igic", "ipsi"}
    with translation.override("en"):
        assert {kind: str(name) for kind, name in schemas.TAX_KIND_NAMES.items()} == {
            "vat": "VAT",
            "igic": "IGIC",
            "ipsi": "IPSI",
        }
    with translation.override("es"):
        assert str(schemas.TAX_KIND_NAMES["vat"]) == "IVA"


def test_a_region_of_another_country_than_the_business_is_a_422_never_the_national_rate(no_seed):
    rule(category(), "21")
    with pytest.raises(InvalidPayload) as refused:
        calculate(amount=10_000, tax_category_key="product.generic", region_code="PT-20", date=TODAY)
    assert (refused.value.status, list(refused.value.fields)) == (422, ["region_code"])
    with pytest.raises(InvalidPayload):
        categories(region_code="PT-20")


# The tax family of a territory (TAX-F11): what a line without a category or a rule is declared with


def test_each_territory_declares_its_own_tax_family(no_seed):
    assert [
        queries.tax_kind_of(country, region)
        for country, region in (
            ("ES", None),
            ("ES", "ES-CN"),
            (" es ", "es-ce"),
            ("ES", "ES-ML"),
            # Madrid charges the national VAT; a region of another country is never Spain's IGIC.
            ("ES", "ES-MD"),
            ("PT", "PT-20"),
            ("PT", "ES-CN"),
        )
    ] == ["vat", "igic", "ipsi", "ipsi", "vat", "vat", "vat"]
    assert queries.business_tax_kind() == "vat"
    keep_region("ES-CN")
    assert queries.business_tax_kind() == "igic"


def test_a_zero_fallback_carries_the_tax_family_of_its_territory(no_seed):
    category()
    keep_region("ES-CE")
    result = queries.calculate_tax(
        amount=10_000, category_key="product.generic", on=TODAY, allow_missing_rate=True
    )
    assert (result["source"], result["tax"], result["tax_kind"], result["tax_region_code"]) == (
        "fallback_zero",
        0,
        "ipsi",
        "ES-CE",
    )


def test_in_a_region_without_its_own_tax_its_rule_still_beats_the_national_one(no_seed):
    # Only the territories outside the VAT (ES-CN, ES-CE, ES-ML) drop the national rule: anywhere else the
    # exact region still wins over the whole country, and the whole country stands in when the region has none.
    generic = category()
    national = rule(generic, "21")
    madrid = rule(generic, "10", region="ES-MD")
    assert resolve(region="ES-MD").root == madrid
    assert queries.pick_root([national, madrid], "ES-MD") == madrid
    assert queries.pick_root([madrid, national], "ES-MD") == madrid
    assert queries.pick_root([national], "ES-MD") == national
