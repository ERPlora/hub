"""Models of the tax app: categories with a unique key, rules with their database guards, aliases."""

from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import translation

from apps.tax.models import SYSTEM_CATEGORY_LABELS, TaxAlias, TaxCategory, TaxRule, TaxSettings

CANONICAL_KEYS = {
    "restaurant.food",
    "restaurant.drink",
    "restaurant.alcohol",
    "retail.alcohol",
    "restaurant.delivery",
    "service.generic",
    "service.health",
    "service.education",
    "product.generic",
    "product.reduced",
    "product.super_reduced",
}


def category(key="product.books", name="Books", **fields):
    return TaxCategory.objects.create(key=key, name=name, **fields)


def rule(cat, rate="21", country="ES", **fields):
    return TaxRule.objects.create(
        category=cat, country_code=country, rate_pct=Decimal(rate), **fields
    )


def violates(constraint, create):
    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        create()
    return constraint in str(excinfo.value)


# Keys and defaults


@pytest.mark.django_db
def test_keys_are_uuid7(no_seed):
    cat = category()
    root = rule(cat)
    alias = TaxAlias.objects.create(alias="books", category=cat)
    assert (cat.pk.version, root.pk.version, alias.pk.version) == (7, 7, 7)


@pytest.mark.django_db
def test_defaults(no_seed):
    cat = category()
    root = rule(cat)
    alias = TaxAlias.objects.create(alias="books", category=cat)
    for row in (cat, root, alias):
        row.refresh_from_db()
    # Active, as in the current product's tables (the «Active» column of the screens).
    assert (cat.description, cat.is_system, cat.is_active) == ("", False, True)
    assert (root.region_code, root.tax_type, root.operation_class, root.is_active) == (
        "",
        "vat",
        "subject",
        True,
    )
    assert (root.exempt_reason, root.regime_key, root.parent, root.component_label) == (
        "",
        "",
        None,
        "",
    )
    assert (root.valid_from, root.valid_to) == (None, None)
    assert (alias.source, alias.is_active) == (TaxAlias.Source.LEARNED, True)


def test_choices():
    assert TaxRule.TaxType.values == [
        "vat", "igic", "ipsi", "surcharge", "sales_tax", "withholding", "excise", "import_duty",
    ]  # fmt: skip
    assert TaxRule.OperationClass.values == [
        "subject", "subject_reverse", "exempt", "not_subject", "not_subject_location",
    ]  # fmt: skip
    assert TaxAlias.Source.values == ["shipped", "learned"]


# TaxCategory: the linkable key of inventory and service


@pytest.mark.django_db
def test_the_key_is_unique(no_seed):
    category("product.books")
    assert violates("tax_taxcategory_key", lambda: category("product.books", "Other"))


@pytest.mark.parametrize(
    "key", ["Product", "1product", "product-books", "product books", "", "x" * 81]
)
def test_a_key_has_the_canonical_shape(key):
    with pytest.raises(ValidationError) as excinfo:
        TaxCategory(key=key, name="x").full_clean(validate_unique=False)
    assert "key" in excinfo.value.message_dict


@pytest.mark.parametrize("key", ["product.books", "a", "service.health_2", "x" * 80])
def test_canonical_keys_are_valid(key):
    TaxCategory(key=key, name="x").full_clean(validate_unique=False)


def test_the_labels_are_those_of_the_canonical_categories():
    assert set(SYSTEM_CATEGORY_LABELS) == CANONICAL_KEYS


def test_a_system_category_shows_its_name_in_the_language_of_the_reader():
    food = TaxCategory(key="restaurant.food", name="Restaurant — food", is_system=True)
    health = TaxCategory(
        key="service.health", name="Service — healthcare (VAT exempt)", is_system=True
    )
    with translation.override("es"):
        assert food.display_name == "Restauración — comida"
        assert food.display_description == ""
        assert health.display_name == "Servicio — sanitario (exento de IVA)"
        assert health.display_description == (
            "Asistencia prestada por profesionales médicos o sanitarios — art. 20.Uno.3 (ES)"
        )
    with translation.override("en"):
        assert food.display_name == "Restaurant — food"


def test_an_own_category_keeps_the_text_that_was_typed():
    books = TaxCategory(
        key="product.books", name="Libros y revistas", description="Solo papel"
    )
    # Even with a canonical key, a category the business created is its own: it is not translated.
    own_food = TaxCategory(key="restaurant.food", name="Comida de la casa")
    with translation.override("en"):
        assert (books.display_name, books.display_description) == (
            "Libros y revistas",
            "Solo papel",
        )
        assert own_food.display_name == "Comida de la casa"


@pytest.mark.django_db
def test_a_category_with_rules_or_aliases_is_never_deleted(no_seed):
    with_rule, with_alias = category("product.a"), category("product.b")
    rule(with_rule)
    TaxAlias.objects.create(alias="b", category=with_alias)
    for cat in (with_rule, with_alias):
        with pytest.raises(ProtectedError):
            cat.delete()


# TaxRule: what the database refuses whatever door the row comes through


@pytest.mark.django_db
def test_the_rate_keeps_two_decimals(no_seed):
    surcharge = rule(category(), rate="5.2")
    surcharge.refresh_from_db()
    assert surcharge.rate_pct == Decimal("5.20")


@pytest.mark.django_db
@pytest.mark.parametrize("rate", ["-0.01", "100.01"])
def test_the_rate_is_between_0_and_100(no_seed, rate):
    cat = category()
    assert violates("tax_rule_rate_range", lambda: rule(cat, rate=rate))


@pytest.mark.django_db
def test_0_and_100_are_rates(no_seed):
    cat = category()
    rule(cat, rate="0", valid_to=date(2020, 1, 1))
    rule(cat, rate="100", valid_from=date(2020, 1, 2))
    assert cat.rules.count() == 2


@pytest.mark.django_db
@pytest.mark.parametrize(
    "operation_class",
    ["subject_reverse", "exempt", "not_subject", "not_subject_location"],
)
def test_a_class_that_charges_no_tax_has_no_rate(no_seed, operation_class):
    cat = category()
    assert violates(
        "tax_rule_no_rate_without_tax",
        lambda: rule(cat, rate="21", operation_class=operation_class),
    )
    rule(cat, rate="0", operation_class=operation_class)  # at 0 % it is legitimate


@pytest.mark.django_db
def test_the_validity_range_runs_forwards(no_seed):
    cat = category()
    backwards = {"valid_from": date(2026, 2, 1), "valid_to": date(2026, 1, 31)}
    assert violates("tax_rule_valid_range", lambda: rule(cat, **backwards))
    rule(
        cat, valid_from=date(2026, 1, 31), valid_to=date(2026, 1, 31)
    )  # one single day is a range


@pytest.mark.parametrize(
    ("valid_from", "valid_to", "day", "in_force"),
    [
        (None, None, date(1990, 1, 1), True),
        (date(2012, 9, 1), None, date(2012, 9, 1), True),  # the first day counts
        (date(2012, 9, 1), None, date(2012, 8, 31), False),
        (None, date(2026, 12, 31), date(2026, 12, 31), True),  # the last day counts
        (None, date(2026, 12, 31), date(2027, 1, 1), False),
    ],
)
def test_in_force_on_is_inclusive_and_open_when_empty(
    valid_from, valid_to, day, in_force
):
    assert (
        TaxRule(valid_from=valid_from, valid_to=valid_to).in_force_on(day) is in_force
    )


@pytest.mark.django_db
def test_a_root_with_components_is_never_deleted(no_seed):
    cat = category()
    root = rule(cat)
    rule(cat, rate="5.2", parent=root, tax_type="surcharge")
    with pytest.raises(ProtectedError):
        root.delete()
    assert list(root.components.values_list("rate_pct", flat=True)) == [Decimal("5.20")]


def test_a_component_is_labelled_by_its_label_or_its_tax_type():
    assert (
        TaxRule(component_label="Recargo de equivalencia", tax_type="surcharge").label
        == "Recargo de equivalencia"
    )
    assert TaxRule(tax_type="vat").label == "vat"
    assert TaxRule().is_root and not TaxRule(parent_id=TaxRule().pk).is_root


# TaxAlias


@pytest.mark.django_db
def test_an_alias_is_unique(no_seed):
    cat = category()
    TaxAlias.objects.create(alias="books", category=cat)
    assert violates(
        "tax_taxalias_alias",
        lambda: TaxAlias.objects.create(alias="books", category=cat),
    )


@pytest.mark.django_db
def test_how_a_rule_reads(no_seed):
    cat = category("restaurant.food")
    assert str(rule(cat, rate="7", region_code="ES-CN")) == "ES ES-CN · restaurant.food · 7 %"
    assert str(rule(cat, rate="10")) == "ES · restaurant.food · 10 %"


# The natural key of a root rule (the current product's ix_tax_rule_root_natural): one root per
# country, region, category and first day, deactivated ones included.


@pytest.mark.django_db
def test_a_root_twin_of_a_deactivated_root_is_refused(no_seed):
    cat = category()
    rule(cat, valid_from=date(2026, 1, 1), is_active=False)
    assert violates("tax_rule_root_natural_key", lambda: rule(cat, rate="22", valid_from=date(2026, 1, 1)))


@pytest.mark.django_db
def test_since_always_twice_is_the_same_root(no_seed):
    # An empty first day means «since always»: two of them are the same key (NULLs not distinct).
    cat = category()
    rule(cat, is_active=False)
    assert violates("tax_rule_root_natural_key", lambda: rule(cat, rate="22"))


@pytest.mark.django_db
def test_other_first_days_regions_countries_and_components_are_other_keys(no_seed):
    cat = category()
    root = rule(cat, valid_from=date(2026, 1, 1), is_active=False)
    rule(cat, valid_from=date(2027, 1, 1))
    rule(cat, region_code="ES-CN", valid_from=date(2026, 1, 1))
    rule(cat, country="PT", valid_from=date(2026, 1, 1))
    # Components share their root's slot by design.
    rule(cat, rate="5.2", parent=root, valid_from=date(2026, 1, 1))
    rule(cat, rate="1.4", parent=root, valid_from=date(2026, 1, 1))
    assert TaxRule.objects.count() == 6


def test_the_two_alcohol_categories_say_where_the_drink_is_drunk():
    served = TaxCategory(key="restaurant.alcohol", name="Restaurant — alcohol", is_system=True)
    to_take_away = TaxCategory(key="retail.alcohol", name="Retail — alcohol to take away", is_system=True)
    with translation.override("es"):
        assert served.display_description == (
            "Bebidas alcohólicas servidas para consumir en el local — art. 91.Uno.2.2 (ES)"
        )
        assert to_take_away.display_name == "Venta — alcohol para llevar"


# The business's tax settings (TAX-F11): one row at most, the whole country until a region is kept


@pytest.mark.django_db
def test_the_tax_settings_are_one_row_of_the_whole_country():
    kept = TaxSettings.objects.create()
    assert (kept.pk.version, kept.region_code, kept.updated_by) == (7, "", "")
    assert violates("tax_settings_single_row", lambda: TaxSettings.objects.create(region_code="ES-CN"))
