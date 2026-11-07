"""The labels of the countries a tax rule is set for (hub#678): the 249 ISO 3166-1 codes the schemas take
(``country_code``) are a closed list no field of the models labels, so the app declares them (``LiveAppConfig.choices``)
and the assistant's card says each one by its name — «Alemania» in Spanish, «Germany» in English —, never the code it
sends. The names are CLDR's, the ones the Rules screen's country picker shows (``Intl.DisplayNames``)."""

import pytest
from django.apps import apps
from django.utils import translation

from apps.tax.choices import CHOICES, COUNTRY_LABELS
from apps.tax.schemas import COUNTRY_CODES
from base.business import country_name


def test_every_country_a_rule_takes_is_declared():
    """A code the schemas take and the app does not label would reach the card as its code."""
    assert [code for code, _ in COUNTRY_LABELS] == list(COUNTRY_CODES)
    assert CHOICES == {"country_code": COUNTRY_LABELS}


def test_the_app_declares_them_for_the_assistant():
    assert apps.get_app_config("tax").choices == CHOICES


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", {"ES": "Spain", "DE": "Germany", "PT": "Portugal", "US": "United States"}),
        ("es", {"ES": "España", "DE": "Alemania", "PT": "Portugal", "US": "Estados Unidos"}),
    ],
)
def test_a_country_is_said_by_its_name_in_the_language_of_whoever_reads(language, expected):
    labels = dict(COUNTRY_LABELS)
    with translation.override(language):
        assert {code: str(labels[code]) for code in expected} == expected


@pytest.mark.parametrize("language", ["en", "es"])
def test_every_country_has_a_name_and_it_is_the_platforms(language):
    """Each label is the name the platform gives that country in that language (``base.business.country_name``, CLDR,
    as the screen's picker): never the code, never blank."""
    with translation.override(language):
        said = {code: str(label) for code, label in COUNTRY_LABELS}
    assert said == {code: country_name(code, language) for code in COUNTRY_CODES}
    assert not [code for code, name in said.items() if not name.strip() or name == code]
