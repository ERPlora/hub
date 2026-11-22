"""The business's jurisdiction and the tax family of each territory (TAX-F11): what every calculation reads when it
names no country, and what a line without a category or a rule is declared with."""

from decimal import Decimal

import pytest
from django.utils import translation
from live.errors import InvalidPayload

from apps.tax import queries, schemas
from apps.tax.models import TaxSettings
from apps.tax.schemas import SettingsGetIn

from .conftest import HUB_DB, TODAY, calculate, categories, category, resolve, rule, run

pytestmark = HUB_DB


# The business's jurisdiction (TAX-F11): its country and the region it keeps in Taxes. Every
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
