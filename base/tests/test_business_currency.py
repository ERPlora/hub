"""``base.operations.business_currency``: the currency a hub's business charges in, the one question every app that
charges asks (BASE-F50; FIX-HUB-BASE-BUSINESS-CURRENCY-IN-PYTHON-AND-ERPLORAS-OWN-HUB).

It is ``base.business.get``'s currency, read as the platform: an API key holds only the permissions of what it charges,
so the caller's context never decides whether the currency is known. A hub's business pays in its country's currency;
ERPlora's own hub (phase 1: no registry row) in the one of its issuer's country, as its invoices; a demo in its row's
(euros without a country). A scope that is no hub's has no currency: the same ``NotFound`` as the operation, never a
silent euro. Each hub answers its own, never another's.
"""

import pytest
from django.test import override_settings
from django.utils import translation
from live.context import OperationContext, Scope
from live.errors import NotFound, PermissionDenied
from live.operations import get

from base.models import Hub
from base.operations import business_currency
from base.schemas import BusinessIn

pytestmark = pytest.mark.django_db

A = Scope("host", "a")
B = Scope("host", "b")
ERPLORA = Scope("host", "erplora")


@pytest.fixture
def hubs():
    """``a`` in Spain and ``b`` in Japan, as the SaaS registered each business."""
    for slug, country in (("a", "ES"), ("b", "JP")):
        Hub.objects.update_or_create(slug=slug, defaults={"status": "ready", "name": slug.upper(), "country": country})


def test_a_hub_s_business_charges_in_its_country_s_currency_never_another_hub_s(hubs):
    assert (business_currency(A), business_currency(B)) == ("EUR", "JPY")
    Hub.objects.filter(slug="b").update(country="PL")
    assert (business_currency(A), business_currency(B)) == ("EUR", "PLN")


def test_erplora_s_own_hub_charges_in_its_issuer_s_country_s_currency():
    assert not Hub.objects.filter(slug="erplora").exists()  # phase 1: no registry row
    assert business_currency(ERPLORA) == "EUR"
    with override_settings(PLATFORM_ISSUER_COUNTRY="GB"):
        assert business_currency(ERPLORA) == "GBP"
    with override_settings(PLATFORM_ISSUER_COUNTRY="CH"):
        assert business_currency(ERPLORA) == "CHF"


@override_settings(PLATFORM_HUB_SLUG="erplora-pre", PLATFORM_ISSUER_COUNTRY="JP")
def test_erplora_s_own_hub_is_the_one_its_setting_names(hubs):
    assert business_currency(Scope("host", "erplora-pre")) == "JPY"
    assert business_currency(A) == "EUR"


def test_a_demo_charges_in_its_row_s_currency():
    Hub.objects.create(slug="demo-0000c0de", status="ready", is_demo=True)
    Hub.objects.create(slug="demo-0000beef", status="ready", is_demo=True, country="PL")
    assert business_currency(Scope("host", "demo-0000c0de")) == "EUR"  # no country: euros
    assert business_currency(Scope("host", "demo-0000beef")) == "PLN"


@pytest.mark.parametrize("scope", [Scope("host", "nobody"), Scope("platform", "registry")])
def test_a_scope_that_is_no_hub_s_has_no_currency_never_a_silent_euro(scope):
    with translation.override("es"), pytest.raises(NotFound) as refused:
        business_currency(scope)
    assert refused.value.message == "No hay ningún negocio aquí."


def test_it_reads_as_the_platform_whatever_the_caller_may_see(hubs):
    """An API key that only charges (no ``base.view_home``) is refused the business, yet charges in its currency."""
    key = OperationContext(scope=B, actor="key", permissions=frozenset({"sale.charge"}))
    with pytest.raises(PermissionDenied):
        get("base.business.get")(key, BusinessIn())
    assert business_currency(key.scope) == "JPY"
