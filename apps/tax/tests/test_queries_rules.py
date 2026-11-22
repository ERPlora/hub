"""The tax rules the screens read: ``tax.rule.list``, ``tax.rule.status``, ``tax.rule.parent_candidates`` and
``tax.rule.countries``.

The lists are those of the current product's SQL batteries.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from live.errors import Conflict
from live.operations import get

from apps.tax.schemas import RuleCountriesIn, RuleParentIn, RuleStatusIn

from .conftest import HUB_DB, category, ctx_for, rule, rules, run

pytestmark = HUB_DB


# tax.rule.list (TAX-F03)


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
        "factory_rules": True,
    }
    # Without a stated country, the business's (hub#996): Spain, for one without a country registered.
    assert status().model_dump() == {
        "country_code": "ES",
        "matching_rules": 11,
        "configured": True,
        "factory_rules": True,
    }
    # A French business carrying only the Spanish rules is not configured, and France brings no rules of its own.
    assert status(country_code="fr").model_dump() == {
        "country_code": "FR",
        "matching_rules": 0,
        "configured": False,
        "factory_rules": False,
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
    # Without a stated country, the business's own (Spain here, with no country registered): another country's
    # rule never counts (hub#996).
    rule(category("product.z"), "23", country="PT")
    business = status()
    assert (business.country_code, business.matching_rules, business.configured) == ("ES", 3, True)


def test_nothing_in_force_is_not_configured(no_seed):
    # TAX-F17: no rule at all, or only ones not in force today, is «missing your taxes».
    assert (status().matching_rules, status().configured) == (0, False)
    rule(category(), "21", is_active=False)
    rule(category("product.x"), "21", valid_from=timezone.localdate() + timedelta(days=1))
    assert (status().matching_rules, status().configured) == (0, False)


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
