"""``base.operations.business_country``: the country a hub's business is in for every rule by country that an app
reads, such as the country of a phone written without prefix (hub#527, CUSTOMER-F10, CUSTOMER-F11).

It is ``base.business.get``'s country, read as the platform as ``business_currency`` reads the currency (no second
source), through base's one reading of a business without one (``base.business.country_or_market``,
hub#682): ERPlora's market, Spain. ERPlora's own hub answers its issuer's country. A scope that is no hub's has no
country: the same ``NotFound`` as the operation, never a silent Spain. Each hub answers its own, never another's.
"""

import pytest
from django.utils import translation
from live.context import OperationContext, Scope
from live.errors import NotFound, PermissionDenied
from live.operations import get

from apps.sale.tests.test_business_currency import platform
from base.models import Hub
from base.operations import business_country, current_business_country, current_business_scope
from base.schemas import BusinessIn
from base.tenancy.context import HubContextMissing, use_control, use_hub
from base.tenancy.tests.business import A, B, HUB_DB, in_business_a
from base.tests.businesses import in_each

__all__ = ["in_business_a", "platform"]

pytestmark = HUB_DB


@pytest.fixture
def hubs(hub_b):
    """A in Poland and B in Spain, as the SaaS registered each business; B's row."""
    for slug, country in ((A.key, "PL"), (B.key, "ES")):
        Hub.objects.filter(slug=slug).update(name=slug.upper(), country=country)
    return hub_b


def test_a_hub_s_business_is_in_its_own_country_never_another_hub_s(hubs):
    assert in_each(business_country, hubs) == ("PL", "ES")
    Hub.objects.filter(slug=B.key).update(country="FR")
    assert in_each(business_country, hubs) == ("PL", "FR")


def test_a_business_without_a_country_is_in_erplora_s_market(hubs):
    Hub.objects.filter(slug=A.key).update(country="")
    assert business_country(A) == "ES"


def test_erplora_s_own_hub_is_in_its_issuer_s_country(platform, settings):
    assert platform.country == ""  # its registry row has no country of its own
    with use_hub(platform):
        assert business_country(B) == "ES"
        settings.PLATFORM_ISSUER_COUNTRY = "GB"
        assert business_country(B) == "GB"


def test_a_demo_is_in_its_row_s_country_or_in_erplora_s_market(hub_b):
    Hub.objects.filter(slug__in=(A.key, B.key)).update(is_demo=True)
    Hub.objects.filter(slug=B.key).update(country="PL")
    assert in_each(business_country, hub_b) == ("ES", "PL")


@pytest.mark.parametrize("scope", [A, Scope("platform", "registry")])
def test_a_scope_that_is_no_hub_s_has_no_country_never_a_silent_spain(scope):
    Hub.objects.filter(slug=A.key).update(slug="moved")  # no registry row holds A's address any more
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


def test_the_business_at_work_is_in_its_own_country_never_another_hub_s(hub_a, hub_b):
    Hub.objects.filter(pk=hub_a.pk).update(country="PT")
    Hub.objects.filter(pk=hub_b.pk).update(country="PL")
    with use_hub(hub_a):
        assert current_business_country() == "PT"
    with use_hub(hub_b):
        assert current_business_country() == "PL"
    Hub.objects.filter(pk=hub_b.pk).update(country="")
    with use_hub(hub_b):
        assert current_business_country() == "ES"


def test_erplora_s_own_hub_at_work_is_in_its_issuer_s_country(platform, settings):
    settings.PLATFORM_ISSUER_COUNTRY = "GB"
    with use_hub(platform):
        assert current_business_country() == "GB"


def test_where_no_business_is_at_work_it_is_erplora_s_market():
    with use_control():
        assert current_business_country() == "ES"


# ── The scope of the business at work, to ask another app as the platform (hub#1459) ────────────────────────────────
# Price Lists, which does not require Services, asks Services which service stands for one of a separate copy's while
# the copy is given back: no caller is at hand there, only the business whose database is at work.


def test_the_scope_at_work_is_its_business_s_never_another_hub_s(hub_a, hub_b):
    with use_hub(hub_a):
        assert current_business_scope() == Scope("host", hub_a.slug)
    with use_hub(hub_b):
        assert current_business_scope() == Scope("host", hub_b.slug)


def test_where_no_business_is_at_work_there_is_no_scope_to_ask_in():
    with use_control(), pytest.raises(HubContextMissing):
        current_business_scope()
