"""``base.operations.business_currency``: the currency a hub's business charges in, the one question every app that
charges asks (BASE-F50).

It is ``base.business.get``'s currency, read as the platform: an API key holds only the permissions of what it charges,
so the caller's context never decides whether the currency is known. A hub's business pays in its country's currency;
ERPlora's own hub (without a registry row) in the one of its issuer's country, as its invoices; a demo in its row's
(euros without a country). A scope that is no hub's has no currency: the same ``NotFound`` as the operation, never a
silent euro. Each hub answers its own, never another's.
"""

import pytest
from django.utils import translation
from live.context import OperationContext, Scope
from live.errors import NotFound, PermissionDenied
from live.operations import get

from apps.sale.tests.test_business_currency import platform
from base.models import Hub
from base.operations import business_currency
from base.schemas.business import BusinessIn
from base.tenancy.context import use_hub
from base.tenancy.tests.business import A, B, HUB_DB, in_business_a
from base.tests.businesses import in_each

__all__ = ["in_business_a", "platform"]

pytestmark = HUB_DB


@pytest.fixture
def hubs(hub_b):
    """A in Spain and B in Japan, as the SaaS registered each business; B's row."""
    for slug, country in ((A.key, "ES"), (B.key, "JP")):
        Hub.objects.filter(slug=slug).update(name=slug.upper(), country=country)
    return hub_b


def test_a_hub_s_business_charges_in_its_country_s_currency_never_another_hub_s(hubs):
    assert in_each(business_currency, hubs) == ("EUR", "JPY")
    Hub.objects.filter(slug=B.key).update(country="PL")
    assert in_each(business_currency, hubs) == ("EUR", "PLN")


def test_erplora_s_own_hub_charges_in_its_issuer_s_country_s_currency(platform, settings):
    assert platform.country == ""  # its registry row has no country of its own
    with use_hub(platform):
        assert business_currency(B) == "EUR"
        settings.PLATFORM_ISSUER_COUNTRY = "GB"
        assert business_currency(B) == "GBP"
        settings.PLATFORM_ISSUER_COUNTRY = "CH"
        assert business_currency(B) == "CHF"


def test_erplora_s_own_hub_is_the_one_its_setting_names(platform, settings):
    settings.PLATFORM_ISSUER_COUNTRY = "JP"
    Hub.objects.filter(slug=A.key).update(country="ES")
    with use_hub(platform):
        assert business_currency(B) == "JPY"
    assert business_currency(A) == "EUR"


def test_a_demo_charges_in_its_row_s_currency(hub_b):
    Hub.objects.filter(slug__in=(A.key, B.key)).update(is_demo=True)
    Hub.objects.filter(slug=B.key).update(country="PL")
    assert in_each(business_currency, hub_b) == ("EUR", "PLN")  # no country: euros


@pytest.mark.parametrize("scope", [A, Scope("platform", "registry")])
def test_a_scope_that_is_no_hub_s_has_no_currency_never_a_silent_euro(scope):
    Hub.objects.filter(slug=A.key).update(slug="moved")  # no registry row holds A's address any more
    with translation.override("es"), pytest.raises(NotFound) as refused:
        business_currency(scope)
    assert refused.value.message == "No hay ningún negocio aquí."


def test_it_reads_as_the_platform_whatever_the_caller_may_see(hubs):
    """An API key that only charges (no ``base.view_home``) is refused the business, yet charges in its currency."""
    key = OperationContext(scope=B, actor="key", permissions=frozenset({"sale.charge"}))
    with use_hub(hubs):
        with pytest.raises(PermissionDenied):
            get("base.business.get")(key, BusinessIn())
        assert business_currency(key.scope) == "JPY"
