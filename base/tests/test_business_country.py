"""``base.operations.business_country``: the country a hub's business is in for every rule by country that an app
reads, such as the country of a phone written without prefix (hub#527, CUSTOMER-F10, CUSTOMER-F11).

It is ``base.business.get``'s country, read as the platform as ``business_currency`` reads the currency (no second
source), through base's one reading of a business without one (``base.business.country_or_market``,
hub#682): ERPlora's market, Spain. ERPlora's own hub answers its issuer's country. A scope that is no hub's has no
country: the same ``NotFound`` as the operation, never a silent Spain. Each hub answers its own, never another's.
"""

import pytest
from django.conf import settings
from django.test import override_settings
from django.utils import translation
from live.context import OperationContext, Scope
from live.errors import NotFound, PermissionDenied
from live.operations import get

from base.models import Hub
from base.operations import business_country, current_business_country, current_business_scope
from base.schemas import BusinessIn
from base.tenancy.context import HubContextMissing, use_control, use_hub
from base.tenancy.tests.hubs import HUB_DATABASES

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
    assert not Hub.objects.filter(slug="erplora").exists()  # it answers even without a registry row
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


# ── The business at work, for a reading with no scope at hand (hub#996) ─────────────────────────────────────────────
# Taxes resolves a rate deep inside Sales and Invoices, where no context is passed down: it asks for the country of the
# business whose database is at work (``use_hub``), read by the same rule as above, never a second source.


@pytest.mark.django_db(databases=HUB_DATABASES)
def test_the_business_at_work_is_in_its_own_country_never_another_hub_s(hub_a, hub_b, no_test_fallback):
    Hub.objects.filter(pk=hub_a.pk).update(country="PT")
    Hub.objects.filter(pk=hub_b.pk).update(country="PL")
    with use_hub(hub_a):
        assert current_business_country() == "PT"
    with use_hub(hub_b):
        assert current_business_country() == "PL"
    Hub.objects.filter(pk=hub_b.pk).update(country="")
    with use_hub(hub_b):
        assert current_business_country() == "ES"


def test_erplora_s_own_hub_at_work_is_in_its_issuer_s_country():
    with use_hub(Hub(slug=settings.PLATFORM_HUB_SLUG)), override_settings(PLATFORM_ISSUER_COUNTRY="GB"):
        assert current_business_country() == "GB"


def test_where_no_business_is_at_work_it_is_erplora_s_market(no_test_fallback):
    with use_control():
        assert current_business_country() == "ES"


# ── The scope of the business at work, to ask another app as the platform (hub#1459) ────────────────────────────────
# Price Lists, which does not require Services, asks Services which service stands for one of a separate copy's while
# the copy is given back: no caller is at hand there, only the business whose database is at work.


@pytest.mark.django_db(databases=HUB_DATABASES)
def test_the_scope_at_work_is_its_business_s_never_another_hub_s(hub_a, hub_b, no_test_fallback):
    with use_hub(hub_a):
        assert current_business_scope() == Scope("host", hub_a.slug)
    with use_hub(hub_b):
        assert current_business_scope() == Scope("host", hub_b.slug)


def test_where_no_business_is_at_work_there_is_no_scope_to_ask_in(no_test_fallback):
    with use_control(), pytest.raises(HubContextMissing):
        current_business_scope()
