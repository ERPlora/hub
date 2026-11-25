"""The business's tax settings (TAX-F11)."""

from apps.tax.schemas.settings import SettingsGetIn, TaxSettingsIn

from .schema_checks import invalid_fields


def test_tax_settings_in():
    assert TaxSettingsIn().region_code is None
    assert TaxSettingsIn(region_code=" es-cn ").region_code == "ES-CN"
    assert TaxSettingsIn(region_code="").region_code is None
    assert invalid_fields(TaxSettingsIn, region_code="XX-99") == {"region_code"}
    # A field it does not know is refused, never dropped.
    assert invalid_fields(TaxSettingsIn, country_code="PT") == {"country_code"}
    assert invalid_fields(SettingsGetIn, region_code="ES-CN") == {"region_code"}
