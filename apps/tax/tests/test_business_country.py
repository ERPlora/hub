"""Taxes charges each business in the country erplora.com registered for it (hub#996, PLAN-HUB round 2026-11-07;
TAX-F11, TAX-F17, TAX-F18, TAX-F19).

Taxes reads the country of the business at work as Customers and VeriFactu read it (``base.operations``: the registry's,
ERPlora's market, Spain, without one). Only Spain comes with factory rules (TAX-F16): a business of another country has
them in its database too, but they never apply to it. Each category it sells without a rule of its own country is
refused (409 ``tax.no_rate``, ``sale.no_tax_rule``, ``invoice.no_tax_rule``), never charged Spanish VAT; «Your taxes»
counts only its country's rules and says that country brings none; its region counts only if it is one of that
country's. Two businesses with their own databases in every test: one never reads the other's country.
"""

import importlib
from decimal import Decimal

import pytest
from live.context import OperationContext, Scope
from live.errors import Conflict, InvalidPayload
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get

from apps.invoice.tests.conftest import ISSUER
from apps.sale.models import Sale
from apps.tax import queries
from apps.tax.models import TaxRule, TaxSettings
from apps.tax.schemas import FACTORY_COUNTRIES
from base.models import Hub
from base.schemas import SetupStatusIn
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs

pytestmark = pytest.mark.django_db(databases=hubs.HUB_DATABASES)

GENERIC = "product.generic"
#: 100.00, without the tax.
HUNDRED = 10_000
#: The rules the factory catalogue plants for Spain (TAX-F16): every one a root in force today.
SPANISH_FACTORY_RULES = 11
PORTUGUESE_RULE = {"country_code": "PT", "tax_category_key": GENERIC, "rate_pct": "23"}


@pytest.fixture(autouse=True)
def as_production(no_test_fallback):
    """Without ``use_hub`` a hub's model fails: nothing falls back on a database the two businesses share."""


def registered(hub, country: str):
    """``hub``'s business as erplora.com registered it (``PUT /internal/hubs/{id}``)."""
    Hub.objects.filter(pk=hub.pk).update(country=country)
    return hub


@pytest.fixture
def portugal(hub_a):
    return registered(hub_a, "PT")


@pytest.fixture
def spain(hub_b):
    return registered(hub_b, "ES")


def person(hub, role: str = "hub_owner") -> OperationContext:
    return OperationContext(
        scope=Scope("host", hub.slug), actor="ana", permissions=permissions_for_role(all_live_app_configs(), role)
    )


def run(hub, name: str, data: dict):
    op = get(name)
    with use_hub(hub):
        return op(person(hub), op.input.model_validate(data))


def refusal(hub, name: str, data: dict) -> str:
    with pytest.raises(Conflict) as refused:
        run(hub, name, data)
    return refused.value.code


def charged(hub) -> tuple:
    """What 100.00 of a generic product is charged in ``hub``'s business: ``(country, tax)``."""
    with use_hub(hub):
        result = queries.calculate_tax(amount=HUNDRED, category_key=GENERIC)
    return result["tax_country_code"], result["tax"]


def jurisdiction(hub) -> tuple:
    with use_hub(hub):
        return queries.business_jurisdiction()


def status(hub, **asked) -> tuple:
    found = run(hub, "tax.rule.status", asked)
    return found.country_code, found.matching_rules, found.configured, found.factory_rules


# ── The country (TAX-F11) ──────────────────────────────────────────────────────────────────────────────────────────


def test_each_business_is_in_the_country_erplora_com_registered(portugal, spain):
    assert (jurisdiction(portugal), jurisdiction(spain)) == (("PT", None), ("ES", None))


@pytest.mark.parametrize("country", ["ES", ""], ids=["spain", "no-country"])
def test_spain_and_a_business_without_a_country_are_charged_spanish_vat(portugal, hub_b, country):
    """A business without a country (a demo, ERPlora's own hub) is in ERPlora's market, Spain: nothing changes there."""
    registered(hub_b, country)
    assert charged(hub_b) == ("ES", 2_100)
    with use_hub(portugal), pytest.raises(Conflict) as refused:
        queries.calculate_tax(amount=HUNDRED, category_key=GENERIC)
    assert refused.value.code == "tax.no_rate"


# ── A country without rules is refused, never charged Spain's (TAX-F18, TAX-F19) ──────────────────────────────────


def test_the_spanish_factory_rules_never_apply_to_a_business_of_another_country(portugal, spain):
    with use_hub(portugal):
        assert TaxRule.objects.filter(country_code="ES", category__key=GENERIC, is_active=True).exists()
    assert refusal(portugal, "tax.rate.calculate", {"amount": HUNDRED, "tax_category_key": GENERIC}) == "tax.no_rate"
    asked = run(spain, "tax.rate.calculate", {"amount": HUNDRED, "tax_category_key": GENERIC})
    assert (asked.tax_country_code, asked.tax) == ("ES", 2_100)
    # A 0 % asked for on purpose is its own country's, with its VAT: never Spain's.
    zero = run(portugal, "tax.rate.calculate", {"amount": HUNDRED, "tax_category_key": GENERIC, "allow_missing_rate": True})
    assert (zero.tax_country_code, zero.tax, zero.source, zero.tax_kind) == ("PT", 0, "fallback_zero", "vat")
    # Naming a country still asks for that one alone.
    named = run(portugal, "tax.rate.calculate", {"amount": HUNDRED, "tax_category_key": GENERIC, "country_code": "ES"})
    assert (named.tax_country_code, named.tax) == ("ES", 2_100)


def test_the_business_s_own_rules_charge_it(portugal, spain):
    run(portugal, "tax.rule.create", PORTUGUESE_RULE)
    assert (charged(portugal), charged(spain)) == (("PT", 2_300), ("ES", 2_100))


def test_the_categories_show_no_rate_of_another_country(portugal, spain):
    """Categories and the sections of Sales show the rate a sale would be charged: none where it would be refused."""
    rates = {row.key: row.rate_pct for row in run(portugal, "tax.category.list", {"limit": 100}).rows}
    assert rates[GENERIC] is None
    rates = {row.key: row.rate_pct for row in run(spain, "tax.category.list", {"limit": 100}).rows}
    assert rates[GENERIC] == Decimal("21.00")


def test_a_sale_and_an_invoice_in_portugal_are_refused_never_charged_spanish_vat(portugal, spain):
    sale = {"idempotency_key": "pt-sale-0001", "lines": [{"product": "SHI"}], "payments": [{"method": "card"}]}
    line = {"description": "Shirt", "quantity": "1", "unit_price": HUNDRED, "tax_category_key": GENERIC}
    invoice = {
        "lines": [line],
        "customer_name": "Talleres Pérez SL",
        "customer_tax_id": "B12345674",
        "customer_address": "Calle Luna 3, 28004 Madrid",
    }
    for hub in (portugal, spain):
        run(hub, "inventory.product.create", {"name": "Shirt", "sku": "SHI", "price": 12_100, "tax_category_key": GENERIC})
        run(hub, "invoice.issuer.update", ISSUER)
    assert refusal(portugal, "sale.checkout.preview", {"lines": [{"product": "SHI"}]}) == "sale.no_tax_rule"
    assert refusal(portugal, "sale.sale.complete", sale) == "sale.no_tax_rule"
    assert refusal(portugal, "invoice.invoice.create", invoice) == "invoice.no_tax_rule"
    with use_hub(portugal):
        assert not Sale.objects.exists()
    (charged_line,) = run(spain, "sale.sale.complete", sale).lines
    assert (charged_line.tax_country_code, charged_line.tax_rate, charged_line.tax_amount) == ("ES", Decimal("21.00"), 2_100)
    (declared,) = run(spain, "invoice.invoice.create", invoice).tax_breakdown
    assert (declared.tax, declared.rate, declared.quota) == ("vat", Decimal("21.00"), 2_100)


# ── The region counts only in its own country (TAX-F11) ────────────────────────────────────────────────────────────


def test_a_region_counts_only_if_it_is_of_the_business_s_country(portugal, spain):
    # The Canary Islands, kept while every business was taken for a Spanish one.
    for hub in (portugal, spain):
        with use_hub(hub):
            TaxSettings.objects.update_or_create(singleton=True, defaults={"region_code": "ES-CN"})
    assert (jurisdiction(portugal), jurisdiction(spain)) == (("PT", None), ("ES", "ES-CN"))
    shown = run(portugal, "tax.settings.get", {})
    assert (shown.country_code, shown.region_code, shown.regions, shown.tax_kind) == ("PT", None, [], "vat")
    with pytest.raises(InvalidPayload) as refused:
        run(portugal, "tax.settings.update", {"region_code": "ES-CN"})
    assert refused.value.code == "tax.region_not_available"
    assert run(spain, "tax.settings.get", {}).region_code == "ES-CN"


# ── «Your taxes» counts only the business's country (TAX-F17) ──────────────────────────────────────────────────────


def test_your_taxes_counts_only_the_rules_of_the_business_s_country(portugal, spain):
    assert status(portugal) == ("PT", 0, False, False)
    assert status(spain) == ("ES", SPANISH_FACTORY_RULES, True, True)
    run(portugal, "tax.rule.create", PORTUGUESE_RULE)
    assert status(portugal) == ("PT", 1, True, False)


def test_a_rule_of_another_country_does_not_set_up_spain(portugal, spain):
    with use_hub(spain):
        TaxRule.objects.filter(country_code="ES").update(is_active=False)
    run(spain, "tax.rule.create", PORTUGUESE_RULE)
    assert status(spain) == ("ES", 0, False, True)
    assert status(portugal) == ("PT", 0, False, False)


def test_a_country_asked_for_is_counted_alone(portugal):
    assert status(portugal, country_code="ES") == ("ES", SPANISH_FACTORY_RULES, True, True)


def test_the_home_s_step_your_taxes_follows_the_business_s_country(portugal, spain):
    def step(hub) -> str:
        with use_hub(hub):
            items = get("base.setup.status")(person(hub), SetupStatusIn()).model_dump(mode="json")["items"]
        (found,) = [item for item in items if item["key"] == "tax.rules"]
        return found["state"]

    assert (step(portugal), step(spain)) == ("pending", "done")


def test_spain_is_the_one_country_with_factory_rules():
    """What «Your taxes» says a country brings is what the factory catalogue plants (TAX-F16): Spain's rules only."""
    catalogue = importlib.import_module("apps.tax.migrations.0002_factory_catalogue")
    assert FACTORY_COUNTRIES == frozenset({catalogue.SPAIN})
