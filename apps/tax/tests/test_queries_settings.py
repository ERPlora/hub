"""The business's tax settings (TAX-F11): ``tax.settings.get`` says its country, the region it keeps and the tax its
sales are declared with."""

import pytest

from apps.tax.schemas.settings import SettingsGetIn

from .conftest import HUB_DB, keep_region, run

pytestmark = HUB_DB


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
