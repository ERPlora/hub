"""What of Taxes travels in an export of the business, a backup or a template (BASE-F35): the tax categories the business
made, each with its rules and their components, read and written through Taxes' own operations; never the factory
catalogue every business already has, which no file touches. What a load brings of it stays, like the rest of the
business's settings: undoing the load does not count it nor remove it, and resetting does not offer it (BASE-F34,
BASE-F37).

Every test runs against the real apps (Taxes, Inventory), in business A's own database, and business B in its own.
"""

from decimal import Decimal

import pytest

from apps.tax.tests.conftest import HUB_DB, in_business_a
from base import blueprint
from base.tenancy.context import use_hub
from base.tenancy.tests.business import A, B
from base.tests.blueprint_round_trip import app_report, call, data_of, exported, loaded_back, owner_of

__all__ = ["in_business_a"]
pytestmark = HUB_DB

BOOKS = "product.books"


@pytest.fixture
def ctx():
    return owner_of(A, "olga")


def own_taxes(ctx):
    """Books at 4 % in Spain with its equivalence surcharge, at 0 % of IGIC in the Canary Islands, and a category of its
    own still without a rate."""
    call(ctx, "tax.category.create", key=BOOKS, name="Books", description="Printed books")
    root = call(ctx, "tax.rule.create", country_code="ES", tax_category_key=BOOKS, rate_pct="4")
    call(ctx, "tax.rule.create", country_code="ES", tax_category_key=BOOKS, rate_pct="0.5", tax_type="surcharge",
         parent_id=root.id, component_label="Equivalence surcharge")
    call(ctx, "tax.rule.create", country_code="ES", region_code="ES-CN", tax_category_key=BOOKS, rate_pct="0",
         tax_type="igic")
    call(ctx, "tax.category.create", key="service.workshop", name="Workshops")


def the_own(ctx) -> dict:
    """Every tax category of the business's own, with its rules as Taxes reads them, without ids or dates of change."""
    own = {}
    for category in call(ctx, "tax.category.list", is_system=False, limit=100).rows:
        rules = call(ctx, "tax.rule.list", tax_category_key=category.key, limit=100).rows
        own[category.key] = (
            category.name,
            category.description,
            sorted(
                (rule.country_code, rule.region_code or "", rule.rate_pct, rule.tax_type, rule.operation_class,
                 rule.component_label or "", rule.parent_id is not None)
                for rule in rules
            ),
        )
    return own


def a_book_of_its_own(ctx) -> str:
    """The file of a business whose atlas is of a tax category of its own, with Inventory and Taxes marked."""
    own_taxes(ctx)
    call(ctx, "inventory.product.create", name="Atlas", sku="ATL", price=2500, tax_category_key=BOOKS)
    return exported(ctx, ["inventory", "tax"])


def factory(ctx) -> int:
    return call(ctx, "tax.category.list", is_system=True, limit=1).total


def test_a_backup_brings_the_own_tax_categories_and_their_rates_into_another_business(ctx, hub_b):
    own_taxes(ctx)
    before = the_own(ctx)
    file = exported(ctx, ["tax"])

    with use_hub(hub_b):
        theirs = owner_of(B, "bea")
        factory_before = factory(theirs)
        report = loaded_back(theirs, file)

        assert the_own(theirs) == before
        assert factory(theirs) == factory_before
    [part] = app_report(report, "tax")["datasets"]
    assert (part["key"], part["status"], part["created"]) == ("tax.category", "applied", 2)


def test_the_file_carries_only_the_own_categories_with_their_rules_and_components(ctx):
    assert "tax.category" not in data_of(ctx, ["tax"])
    own_taxes(ctx)

    books, workshop = data_of(ctx, ["tax"])["tax.category"]

    assert (books["key"], books["name"], workshop["key"], workshop["rules"]) == (BOOKS, "Books", "service.workshop", [])
    spain, canaries = sorted(books["rules"], key=lambda rule: rule["region_code"])
    assert (spain["rate_pct"], spain["tax_type"], canaries["region_code"], canaries["tax_type"]) == ("4.00", "vat", "ES-CN", "igic")
    [surcharge] = spain["components"]
    assert (Decimal(surcharge["rate_pct"]), surcharge["component_label"]) == (Decimal("0.5"), "Equivalence surcharge")
    assert "is_system" not in books


def test_loading_it_again_duplicates_nothing_and_leaves_the_factory_catalogue_alone(ctx):
    own_taxes(ctx)
    before, factory_before = the_own(ctx), factory(ctx)

    report = loaded_back(ctx, exported(ctx, ["tax"]))

    assert (the_own(ctx), factory(ctx)) == (before, factory_before)
    [part] = app_report(report, "tax")["datasets"]
    assert (part["status"], part["already"], part["created"]) == ("already", 2, 0)


def test_a_file_never_touches_a_factory_category_even_if_it_names_one(ctx):
    rows = [{"key": "restaurant.food", "name": "Mine", "rules": [{"country_code": "ES", "rate_pct": "3"}]}]
    bundle = blueprint.archive.Bundle(
        manifest=blueprint.archive.manifest(name="Bar", language="en", country="ES", purpose="backup",
                                            created_at="2026-11-26T10:00:00+00:00", vertical="", apps=["tax"]),
        data={"tax.category": rows},
    )
    before = call(ctx, "tax.rule.list", tax_category_key="restaurant.food", limit=100).total

    blueprint.loading.apply(ctx, bundle, apps=None)

    assert call(ctx, "tax.rule.list", tax_category_key="restaurant.food", limit=100).total == before
    assert the_own(ctx) == {}


def test_a_product_of_an_own_category_loads_after_it_in_another_business(ctx, hub_b):
    file = a_book_of_its_own(ctx)

    with use_hub(hub_b):
        theirs = owner_of(B, "bea")
        loaded_back(theirs, file)

        [atlas] = [row for row in call(theirs, "inventory.product.list", limit=100).rows if row.sku == "ATL"]
    assert atlas.tax_category_key == BOOKS


def test_undoing_the_load_counts_and_removes_only_what_is_not_tax(ctx, hub_b):
    file = a_book_of_its_own(ctx)

    with use_hub(hub_b):
        theirs = owner_of(B, "bea")
        load = call(theirs, "base.blueprint.import", file_base64=file)
        call(theirs, "base.import.undo", id=load.id)

        assert load.rows == 1
        assert call(theirs, "inventory.product.list", limit=1).total == 0
        assert set(the_own(theirs)) == {BOOKS, "service.workshop"}


def test_resetting_does_not_offer_taxes_and_leaves_them(ctx):
    own_taxes(ctx)
    before = the_own(ctx)

    sections = [app["id"] for app in blueprint.removal.reset_plan(ctx)]
    blueprint.removal.reset(ctx, ["tax"])

    assert "tax" not in sections
    assert the_own(ctx) == before


def test_settings_data_lists_the_own_categories_as_what_taxes_lets_travel(ctx):
    own_taxes(ctx)

    apps = {app.id: app for app in call(ctx, "base.dataset.list").apps}

    [part] = apps["tax"].datasets
    assert (part.key, part.label, part.rows, part.personal) == ("tax.category", "Own tax categories", 2, False)


def test_a_backup_of_business_b_carries_its_own_categories_and_none_of_business_a_s(ctx, hub_b):
    own_taxes(ctx)
    with use_hub(hub_b):
        theirs = owner_of(B, "bea")
        call(theirs, "tax.category.create", key="product.wine", name="Wine")

        data = data_of(theirs, ["tax"])

    assert [row["key"] for row in data["tax.category"]] == ["product.wine"]
