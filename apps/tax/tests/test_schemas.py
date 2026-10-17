"""Input and output schemas of the tax app: what the API, the live stream and the assistant accept.

Every field carries a description: the schemas are also the JSON Schema of the assistant's tools.
"""

import inspect
import uuid
from datetime import date
from decimal import Decimal

import pydantic
import pytest
from django.utils import translation
from ninja import Schema

from apps.tax import schemas
from apps.tax.schemas import (
    COUNTRY_CODES,
    AliasIn,
    AliasListIn,
    AliasPage,
    AliasResolveIn,
    CalculateIn,
    CalculationOut,
    CategoryGetIn,
    CategoryIn,
    CategoryListIn,
    CategoryOut,
    CategoryPage,
    CategoryRowOut,
    AliasOut,
    Page,
    PageIn,
    RuleBulkIn,
    RuleEndIn,
    RuleIn,
    RuleListIn,
    RulePage,
    RuleRefIn,
    RuleStatusIn,
    SettingsGetIn,
    TaxSettingsIn,
    normalize_text,
)

ID = uuid.uuid7()


def invalid_fields(schema, **data):
    with pytest.raises(pydantic.ValidationError) as excinfo:
        schema(**data)
    return {
        ".".join(str(part) for part in error["loc"]) for error in excinfo.value.errors()
    }


def message(schema, **data):
    with pytest.raises(pydantic.ValidationError) as excinfo:
        schema(**data)
    [error] = excinfo.value.errors()
    return str(error["ctx"]["error"])


RULE = {"country_code": "ES", "tax_category_key": "product.generic", "rate_pct": "21"}


# The assistant's contract: every field says what it is


def schema_classes():
    return [
        value
        for value in vars(schemas).values()
        if inspect.isclass(value)
        and issubclass(value, Schema)
        and value.__module__ == schemas.__name__
    ]


def test_every_field_of_every_schema_has_a_description():
    undescribed = [
        f"{schema.__name__}.{name}"
        for schema in schema_classes()
        for name, info in schema.model_fields.items()
        if not (info.description or "").strip()
    ]
    assert schema_classes() and undescribed == []


# Pages


def test_page_defaults_and_bounds():
    assert PageIn().model_dump() == {"limit": 50, "offset": 0}
    assert PageIn(limit=100).limit == 100
    assert invalid_fields(PageIn, limit=0) == {"limit"}
    assert invalid_fields(PageIn, limit=101) == {"limit"}
    assert invalid_fields(PageIn, offset=-1) == {"offset"}


def test_the_pages_are_the_generic_page():
    assert CategoryPage is Page[CategoryRowOut]
    for page in (CategoryPage, RulePage, AliasPage):
        assert list(page.model_fields) == ["rows", "total", "limit", "offset"]


# Jurisdiction (taxes#41): a closed ISO list, and a real region of that same country


def test_the_country_list_is_the_249_assigned_iso_codes():
    assert len(COUNTRY_CODES) == 249
    assert {"ES", "PT", "FR", "DE", "US"} <= set(COUNTRY_CODES)
    # User-assigned or not countries: a rule for them would never match any business.
    assert not {"ZZ", "EU", "EZ", "UN", "XK"} & set(COUNTRY_CODES)


@pytest.mark.parametrize("country", ["ZZ", "ESP", "E", "", "EU"])
def test_a_country_outside_the_list_is_refused(country):
    assert invalid_fields(RuleIn, **{**RULE, "country_code": country}) == {
        "country_code"
    }


def test_a_country_is_read_in_capitals():
    assert RuleIn(**{**RULE, "country_code": " es "}).country_code == "ES"


@pytest.mark.parametrize("region", ["ES-CN", "es-cn", "ES-ML", "ES-CE", "ES-M"])
def test_a_region_of_the_country(region):
    assert RuleIn(**RULE, region_code=region).region_code == region.upper()


@pytest.mark.parametrize("region", ["CN", "ES-", "ES-ABCD", "ES_CN", "ESP-CN", "ES-XX"])
def test_a_region_is_an_iso_3166_2_subdivision(region):
    # A region no business can hold never matches: the same silence as a country that does not exist.
    assert invalid_fields(RuleIn, **RULE, region_code=region) == {"region_code"}
    with translation.override("en"):
        assert (
            message(RuleIn, **RULE, region_code=region)
            == "Enter an ISO 3166-2 region, such as ES-CN."
        )


def test_a_region_of_another_country_is_refused():
    with translation.override("en"):
        assert (
            message(RuleIn, **RULE, region_code="PT-20")
            == "This region does not belong to the chosen country."
        )


def test_no_region_is_the_whole_country():
    assert RuleIn(**RULE).region_code is None
    assert RuleIn(**RULE, region_code="").region_code is None


# RuleIn


def test_rule_defaults():
    assert RuleIn(**RULE).model_dump() == {
        "country_code": "ES",
        "region_code": None,
        "tax_category_key": "product.generic",
        "operation_class": "subject",
        "rate_pct": Decimal("21"),
        # No family: the one of the rule's territory (TAX-F11), VAT for the whole of Spain.
        "tax_type": None,
        "exempt_reason": None,
        "regime_key": None,
        "valid_from": None,
        "valid_to": None,
        "parent_id": None,
        "component_label": None,
    }


def test_the_category_of_a_rule_may_be_said_by_name():
    # By voice: «Restauración — comida» or an alias; the operation finds the category.
    assert (
        RuleIn(
            **{**RULE, "tax_category_key": " Restauración — comida "}
        ).tax_category_key
        == "Restauración — comida"
    )
    assert invalid_fields(RuleIn, **{**RULE, "tax_category_key": " "}) == {
        "tax_category_key"
    }


@pytest.mark.parametrize("rate", ["-0.01", "100.01", "500", "5.205"])
def test_the_rate_is_0_to_100_with_two_decimals(rate):
    assert invalid_fields(RuleIn, **{**RULE, "rate_pct": rate}) == {"rate_pct"}


@pytest.mark.parametrize("rate", ["0", "5.2", "100"])
def test_valid_rates(rate):
    assert RuleIn(**{**RULE, "rate_pct": rate}).rate_pct == Decimal(rate)


@pytest.mark.parametrize(
    "operation_class",
    ["subject_reverse", "exempt", "not_subject", "not_subject_location"],
)
def test_a_class_that_charges_no_tax_carries_no_rate(operation_class):
    # taxes#59: the till would charge it and the invoice would refuse to seal the sale.
    with translation.override("en"):
        assert message(RuleIn, **{**RULE, "operation_class": operation_class}) == (
            "This operation charges no tax: its rate must be 0 %."
        )
    assert (
        RuleIn(**{**RULE, "operation_class": operation_class, "rate_pct": "0"}).rate_pct
        == 0
    )


def test_the_qualification_is_a_closed_list():
    # A free value would reach the tax agency as a qualification that does not exist.
    assert invalid_fields(RuleIn, **{**RULE, "operation_class": "casi_exento"}) == {
        "operation_class"
    }
    assert invalid_fields(RuleIn, **{**RULE, "tax_type": "gst"}) == {"tax_type"}


def test_the_validity_range_runs_forwards():
    with translation.override("en"):
        assert message(
            RuleIn, **RULE, valid_from="2026-02-01", valid_to="2026-01-31"
        ) == ("The last day cannot be before the first one.")
    same_day = RuleIn(**RULE, valid_from="2026-01-31", valid_to="2026-01-31")
    assert same_day.valid_from == same_day.valid_to == date(2026, 1, 31)


def test_codes_of_the_jurisdiction_are_short_and_in_capitals():
    rule = RuleIn(
        **{**RULE, "rate_pct": "0", "operation_class": "exempt"},
        exempt_reason=" e1 ",
        regime_key="01",
    )
    assert (rule.exempt_reason, rule.regime_key) == ("E1", "01")
    assert invalid_fields(RuleIn, **RULE, exempt_reason="x" * 11) == {"exempt_reason"}
    assert invalid_fields(RuleIn, **RULE, component_label="x" * 121) == {
        "component_label"
    }


# Bulk


def test_bulk_takes_1_to_100_root_rules():
    assert len(RuleBulkIn(rules=[RULE] * 100).rules) == 100
    assert invalid_fields(RuleBulkIn, rules=[]) == {"rules"}
    assert invalid_fields(RuleBulkIn, rules=[RULE] * 101) == {"rules"}


def test_a_bulk_row_is_checked_like_a_single_rule_and_names_its_position():
    rows = [RULE, {**RULE, "operation_class": "exempt"}, {**RULE, "country_code": "ZZ"}]
    assert invalid_fields(RuleBulkIn, rules=rows) == {
        "rules.1.rate_pct",
        "rules.2.country_code",
    }


def test_a_bulk_row_cannot_be_a_component():
    # Components are created one by one: they need their root already saved.
    assert invalid_fields(RuleBulkIn, rules=[{**RULE, "parent_id": str(ID)}]) == {
        "rules.0.parent_id"
    }


# Which rule: its id, or (by voice) its country, region and category


def test_a_rule_is_named_by_its_id_or_by_its_slot():
    assert RuleRefIn(id=str(ID)).id == ID
    by_slot = RuleRefIn(
        country_code="es", tax_category_key="comida", region_code="ES-CN"
    )
    assert (
        by_slot.id,
        by_slot.country_code,
        by_slot.region_code,
        by_slot.tax_category_key,
    ) == (
        None,
        "ES",
        "ES-CN",
        "comida",
    )
    with translation.override("en"):
        assert (
            message(RuleRefIn)
            == "Say which rule: its id, or its country and its category."
        )
        assert (
            message(RuleRefIn, country_code="ES")
            == "Say which rule: its id, or its country and its category."
        )
    assert invalid_fields(RuleRefIn, id="nope") == {"id"}


def test_rule_end():
    assert RuleEndIn(id=str(ID), valid_to="2026-12-31").valid_to == date(2026, 12, 31)
    assert (
        RuleEndIn(
            country_code="ES", tax_category_key="product.generic", valid_to="2026-12-31"
        ).id
        is None
    )
    assert invalid_fields(RuleEndIn, id=str(ID)) == {"valid_to"}


# Lists: the filters, the search and the sort of the current screens


def test_rule_list_filters_and_sort():
    assert RuleListIn().model_dump() == {
        "limit": 50,
        "offset": 0,
        "search": None,
        "country_code": None,
        "region_code": None,
        "tax_category_key": None,
        "tax_type": None,
        "operation_class": None,
        "regime_key": None,
        "parent_id": None,
        "rate_min": None,
        "rate_max": None,
        "status": "active",
        "sort": "tax_category_key",
        "dir": "asc",
    }
    assert RuleListIn(status="all", country_code="pt").country_code == "PT"
    assert invalid_fields(RuleListIn, status="archived") == {"status"}
    assert invalid_fields(RuleListIn, sort="created_at") == {"sort"}
    assert invalid_fields(RuleListIn, dir="up") == {"dir"}
    assert RuleListIn(
        sort="rate_pct", dir="desc", rate_min="4", rate_max="10"
    ).rate_max == Decimal("10")


def test_rule_status_takes_an_optional_country():
    assert RuleStatusIn().country_code is None
    assert RuleStatusIn(country_code="pt").country_code == "PT"


def test_category_list_filters_and_sort():
    params = CategoryListIn()
    assert params.model_dump() == {
        "limit": 50,
        "offset": 0,
        "search": None,
        "key": None,
        "name": None,
        "display_name": None,
        "display_description": None,
        "is_system": None,
        "sort": "key",
        "dir": "asc",
        # No country: the rate column is read in the business's jurisdiction (TAX-F11).
        "country_code": None,
        "region_code": None,
    }
    assert invalid_fields(CategoryListIn, country_code="ES", region_code="PT-20") == {
        "region_code"
    }
    for sort in (
        "key",
        "name",
        "display_name",
        "display_description",
        "is_system",
        "is_active",
        "id",
    ):
        assert CategoryListIn(sort=sort).sort == sort
    assert invalid_fields(CategoryListIn, sort="rate_pct") == {"sort"}


def test_alias_list_filters_and_sort():
    assert AliasListIn().model_dump() == {
        "limit": 50,
        "offset": 0,
        "search": None,
        "alias": None,
        "tax_category_key": None,
        "source": None,
        "sort": "alias",
        "dir": "asc",
    }
    assert invalid_fields(AliasListIn, source="manual") == {"source"}
    for sort in ("alias", "tax_category_key", "source", "is_active", "id"):
        assert AliasListIn(sort=sort).sort == sort


def test_the_rows_carry_the_columns_of_the_screens():
    assert list(CategoryOut.model_fields) == [
        "id", "key", "name", "description", "display_name", "display_description", "is_system", "is_active",
    ]  # fmt: skip
    assert list(CategoryRowOut.model_fields)[-2:] == ["rate_pct", "operation_class"]
    assert list(AliasOut.model_fields) == [
        "id", "alias", "tax_category_key", "tax_category_name", "source", "is_active",
    ]  # fmt: skip


# Categories


def test_category_in():
    category = CategoryIn(key="product.books", name="  Books ")
    assert (category.key, category.name, category.description, category.is_system) == (
        "product.books",
        "Books",
        "",
        False,
    )
    assert invalid_fields(CategoryIn, key="product.books", name=" ") == {"name"}
    assert invalid_fields(CategoryIn, key="product.books", name="x" * 256) == {"name"}
    assert invalid_fields(
        CategoryIn, key="product.books", name="x", description="x" * 1001
    ) == {"description"}


@pytest.mark.parametrize("key", ["Product", "1x", "product-books", "x" * 81, ""])
def test_a_new_category_key_has_the_canonical_shape(key):
    assert invalid_fields(CategoryIn, key=key, name="Books") == {"key"}


def test_a_category_is_looked_up_by_key_name_or_alias():
    assert CategoryGetIn(key=" Restauración — comida ").key == "Restauración — comida"
    assert invalid_fields(CategoryGetIn, key=" ") == {"key"}


# Aliases: normalised the same way at every door


@pytest.mark.parametrize(
    ("text", "normalized"),
    [
        ("Beer", "beer"),
        ("  IVA   10 ", "iva 10"),
        ("Comida\tcasera", "comida casera"),
        ("ÁLCOHOL", "álcohol"),
    ],
)
def test_normalize_text(text, normalized):
    assert normalize_text(text) == normalized


def test_alias_in_is_normalised():
    alias = AliasIn(alias="  Cerveza  Artesana ", tax_category_key="restaurant.alcohol")
    assert (alias.alias, alias.source) == ("cerveza artesana", "learned")
    assert (
        AliasIn(
            alias="beer", tax_category_key="restaurant.alcohol", source="shipped"
        ).source
        == "shipped"
    )
    assert invalid_fields(
        AliasIn, alias="   ", tax_category_key="restaurant.alcohol"
    ) == {"alias"}
    assert invalid_fields(
        AliasIn, alias="x" * 201, tax_category_key="restaurant.alcohol"
    ) == {"alias"}
    assert invalid_fields(
        AliasIn, alias="beer", tax_category_key="restaurant.alcohol", source="manual"
    ) == {"source"}


def test_alias_resolve():
    assert AliasResolveIn(text=" BEER ").text == "beer"
    assert invalid_fields(AliasResolveIn, text="") == {"text"}


# Calculation (TAX-F18)


def test_calculate_in():
    params = CalculateIn(amount=10_000, tax_category_key="product.generic")
    assert params.model_dump() == {
        "amount": 10_000,
        "tax_category_key": "product.generic",
        # No country: the business's jurisdiction, its region included (TAX-F11).
        "country_code": None,
        "region_code": None,
        "date": None,
        "tax_included": False,
        "allow_missing_rate": False,
    }
    # The amount is whole cents and the category is required: no rate is ever guessed.
    assert invalid_fields(CalculateIn, tax_category_key="product.generic") == {"amount"}
    assert invalid_fields(
        CalculateIn, amount="10.5", tax_category_key="product.generic"
    ) == {"amount"}
    assert invalid_fields(CalculateIn, amount=100) == {"tax_category_key"}
    # The caller never brings its own rules (sales#21): there is no field for them.
    assert "rules" not in CalculateIn.model_fields


def test_calculation_out_fields():
    assert list(CalculationOut.model_fields) == [
        "base",
        "tax",
        "total",
        "tax_category_key",
        "tax_rate_pct",
        "tax_country_code",
        "tax_region_code",
        "tax_rule_id",
        "tax_kind",
        "tax_operation_class",
        "tax_regime_key",
        "tax_exempt_reason",
        "tax_included",
        "source",
        "date",
        "components",
    ]


# The business's tax settings (TAX-F11)


def test_tax_settings_in():
    assert TaxSettingsIn().region_code is None
    assert TaxSettingsIn(region_code=" es-cn ").region_code == "ES-CN"
    assert TaxSettingsIn(region_code="").region_code is None
    assert invalid_fields(TaxSettingsIn, region_code="XX-99") == {"region_code"}
    # A field it does not know is refused, never dropped.
    assert invalid_fields(TaxSettingsIn, country_code="PT") == {"country_code"}
    assert invalid_fields(SettingsGetIn, region_code="ES-CN") == {"region_code"}
