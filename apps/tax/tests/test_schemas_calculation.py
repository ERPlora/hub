"""The calculation of the tax of an amount (TAX-F18)."""

from apps.tax.schemas.calculation import CalculateIn, CalculationOut

from .schema_checks import invalid_fields


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
    # The caller never brings its own rules: there is no field for them.
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
