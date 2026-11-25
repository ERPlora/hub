"""The jurisdiction a schema takes: a closed ISO list of countries, and a real region of that same country."""

import pytest
from django.utils import translation

from apps.tax.schemas.jurisdiction import COUNTRY_CODES
from apps.tax.schemas.rules import RuleIn

from .schema_checks import RULE, invalid_fields, message


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
