"""VeriFactu presents every record as the business of the active database (hub#1053)."""

import pytest

from apps.verifactu import queries
from apps.verifactu.models import Config
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from live.context import Scope

pytestmark = [
    pytest.mark.django_db(databases=hubs.HUB_DATABASES),
    pytest.mark.usefixtures("no_test_fallback"),
]

OTHER_NIF = "B00000000"


def test_the_platform_hub_never_presents_another_business_by_its_legacy_config_id(hub_a, hub_b, settings):
    settings.PLATFORM_HUB_SLUG = hub_a.slug
    settings.PLATFORM_ISSUER_TAX_ID = "B27593136"
    with use_hub(hub_a):
        legacy = Config(hub_id=hub_b.id)
        assert queries.presenter(Scope("host", hub_a.slug), legacy, OTHER_NIF) == hub_a.slug
        assert queries.presenter(Scope("host", hub_a.slug), legacy, settings.PLATFORM_ISSUER_TAX_ID) == hub_a.slug


def test_another_config_id_never_redirects_an_ordinary_business(hub_a, hub_b, settings):
    settings.PLATFORM_HUB_SLUG = "erplora"
    with use_hub(hub_b):
        legacy = Config(hub_id=hub_a.id)
        assert queries.presenter(Scope("host", hub_b.slug), legacy, OTHER_NIF) == hub_b.slug
