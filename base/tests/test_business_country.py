"""``base.operations.business_country``: the country a hub's business is in for every rule by country that an app
reads, such as the country of a phone written without prefix (hub#527, CUSTOMER-F10, CUSTOMER-F11).

It is ``base.business.get``'s country, read as the platform as ``business_currency`` reads the currency (no second
source: PLAN-HUB §21), through base's one reading of a business without one (``base.business.country_or_market``,
hub#682): ERPlora's market, Spain. ERPlora's own hub answers its issuer's country. A scope that is no hub's has no
country: the same ``NotFound`` as the operation, never a silent Spain. Each hub answers its own, never another's.
"""

import pytest
from django.test import override_settings
from django.utils import translation
from live.context import OperationContext, Scope
from live.errors import NotFound, PermissionDenied
from live.operations import get

from base.models import Hub
from base.operations import business_country
from base.schemas import BusinessIn

pytestmark = pytest.mark.django_db

A = Scope("host", "a")
B = Scope("host", "b")
ERPLORA = Scope("host", "erplora")


@pytest.fixture
def hubs():
    """``a`` in Poland and ``b`` in Spain, as the SaaS registered each business."""
    for slug, country in (("a", "PL"), ("b", "ES")):
        Hub.objects.update_or_create(slug=slug, defaults={"status": "ready", "name": slug.upper(), "country": country})


def test_a_hub_s_business_is_in_its_own_country_never_another_hub_s(hubs):
    assert (business_country(A), business_country(B)) == ("PL", "ES")
    Hub.objects.filter(slug="b").update(country="FR")
    assert (business_country(A), business_country(B)) == ("PL", "FR")


def test_a_business_without_a_country_is_in_erplora_s_market(hubs):
    Hub.objects.filter(slug="a").update(country="")
    assert business_country(A) == "ES"


def test_erplora_s_own_hub_is_in_its_issuer_s_country():
    assert not Hub.objects.filter(slug="erplora").exists()  # phase 1: no registry row
    assert business_country(ERPLORA) == "ES"
    with override_settings(PLATFORM_ISSUER_COUNTRY="GB"):
        assert business_country(ERPLORA) == "GB"


def test_a_demo_is_in_its_row_s_country_or_in_erplora_s_market():
    Hub.objects.create(slug="demo-0000c0de", status="ready", is_demo=True)
    Hub.objects.create(slug="demo-0000beef", status="ready", is_demo=True, country="PL")
    assert business_country(Scope("host", "demo-0000c0de")) == "ES"
    assert business_country(Scope("host", "demo-0000beef")) == "PL"


@pytest.mark.parametrize("scope", [Scope("host", "nobody"), Scope("platform", "registry")])
def test_a_scope_that_is_no_hub_s_has_no_country_never_a_silent_spain(scope):
    with translation.override("es"), pytest.raises(NotFound) as refused:
        business_country(scope)
    assert refused.value.message == "No hay ningún negocio aquí."


def test_it_reads_as_the_platform_whatever_the_caller_may_see(hubs):
    """A person who may not see the Home (no ``base.view_home``) still has her phones read in the business's country."""
    clerk = OperationContext(scope=A, actor="clerk", permissions=frozenset({"customer.view"}))
    with pytest.raises(PermissionDenied):
        get("base.business.get")(clerk, BusinessIn())
    assert business_country(clerk.scope) == "PL"
