"""What the current product's screens offer, read the same way: lookups by name, filters, sort and only the active
rows."""

from datetime import date

import pytest

from apps.tax.models import TaxAlias, TaxCategory
from apps.tax.schemas import AliasListIn, CategoryGetIn, CategoryListIn, RuleListIn

from base.tests.ordering import assert_reads_backwards, listed_with

from .conftest import HUB_DB, TODAY, aliases, calculate, category, resolved, rule, rules, run

pytestmark = HUB_DB


# Parity with the current screens: lookups by name, filters, sort and the active rows


def test_get_a_category_by_its_name_or_an_alias():
    for text in ("Restauración — comida", "Restaurant — food", "pizza"):
        assert run("tax.category.get", CategoryGetIn(key=text)).key == "restaurant.food"


def test_calculate_naming_the_category_by_voice():
    result = calculate(amount=10_000, tax_category_key="Restauración — comida", date=TODAY)
    assert (result.tax_category_key, result.tax) == ("restaurant.food", 1_000)


def _tied_categories():
    return [category(f"tied.{n}").id for n in range(4)]


def _tied_aliases():
    tied = category("tied.category")
    return [
        TaxAlias.objects.create(alias=f"alias {n}", category=tied).id for n in range(4)
    ]


def _tied_rules():
    tied = category("tied.category")
    return [rule(tied, "21", valid_from=date(2026, n, 1)).id for n in range(1, 5)]


@pytest.mark.parametrize(
    ("operation", "schema", "tied", "column"),
    [
        ("tax.category.list", CategoryListIn, _tied_categories, "is_active"),
        ("tax.alias.list", AliasListIn, _tied_aliases, "source"),
        ("tax.rule.list", RuleListIn, _tied_rules, "country_code"),
    ],
)
def test_ties_read_backwards_in_a_descending_list(no_seed, operation, schema, tied, column):
    """hub#768 (as in Customers): a descending list is the ascending one read backwards, ties
    included, and its pages neither repeat nor lose rows. Each list breaks a tie by its natural key, then the id."""
    listed = listed_with(run, operation, column, schema=schema, by_dir=True)
    assert_reads_backwards(listed, tied())


def test_a_rule_with_no_end_date_stays_last_in_both_directions(no_seed):
    tied = category("tied.category")
    open_ended = rule(tied, "21", valid_from=date(2026, 1, 1))
    earlier = rule(tied, "10", valid_from=date(2025, 1, 1), valid_to=date(2025, 6, 30))
    later = rule(tied, "4", valid_from=date(2025, 7, 1), valid_to=date(2025, 12, 31))

    def listed(direction):
        return [row.id for row in rules(sort="valid_to", dir=direction).rows]

    assert listed("asc") == [earlier.id, later.id, open_ended.id]
    assert listed("desc") == [later.id, earlier.id, open_ended.id]


def test_a_component_stays_right_under_its_root_in_a_descending_list(no_seed):
    """TAX: «a component comes right under its root»: the list reads backwards, groups and components too, and the
    root still leads its group, because that is how a component is recognised."""
    tied = category("tied.category")
    first = rule(tied, "21", valid_from=date(2026, 1, 1))
    first_a = rule(tied, "5.2", parent=first, tax_type="surcharge")
    first_b = rule(tied, "1.4", parent=first, tax_type="surcharge")
    second = rule(tied, "10", valid_from=date(2026, 2, 1))
    second_a = rule(tied, "2.6", parent=second, tax_type="surcharge")

    def listed(direction):
        return [row.id for row in rules(sort="country_code", dir=direction).rows]

    assert listed("asc") == [first.id, first_a.id, first_b.id, second.id, second_a.id]
    assert listed("desc") == [second.id, second_a.id, first.id, first_b.id, first_a.id]


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
    assert names(sort="tax_category_key", dir="desc") == ["meal", "comida casera", "libros"]
    assert names(sort="source") == ["comida casera", "libros", "meal"]
    assert all(row.is_active for row in aliases().rows) and aliases().total == 3


def test_resolve_reads_only_active_categories_and_aliases(no_seed):
    TaxCategory.objects.create(key="product.old", name="Old", is_active=False)
    TaxAlias.objects.create(alias="vieja", category=category("product.new"), is_active=False)
    assert resolved("product.old")[1:] == (None, None)
    assert resolved("old")[1:] == (None, None)
    assert resolved("vieja")[1:] == (None, None)
