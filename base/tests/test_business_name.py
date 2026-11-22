"""``base.operations.business_name``: the name a hub's business goes by, as erplora.com registered it (Settings ›
Business), for an app that shows it, such as the website's page when its own bar names nobody (hub#2084).

It is ``base.business.get``'s name, read as the platform as ``business_currency`` reads the currency: one source, and
each hub answers its own. ERPlora's own hub answers its issuer's legal name; a demo, which has no business on
erplora.com, none.
"""

import pytest
from live.context import OperationContext
from live.errors import PermissionDenied
from live.operations import get

from apps.sale.tests.test_business_currency import platform
from base.models import Hub
from base.operations import business_name
from base.schemas.business import BusinessIn
from base.tenancy.tests.business import A, B, HUB_DB, in_business_a
from base.tests.businesses import in_each

__all__ = ["in_business_a", "platform"]

pytestmark = HUB_DB


def test_a_hub_s_business_goes_by_its_own_name_never_another_hub_s(hub_b):
    Hub.objects.filter(slug=A.key).update(name="Salón Aurora")
    Hub.objects.filter(slug=B.key).update(name="Bar Pepe")
    assert in_each(business_name, hub_b) == ("Salón Aurora", "Bar Pepe")
    Hub.objects.filter(slug=B.key).update(name="Bar Pepe e Hijos")
    assert in_each(business_name, hub_b) == ("Salón Aurora", "Bar Pepe e Hijos")


def test_erplora_s_own_hub_goes_by_its_issuer_s_legal_name(platform, settings):
    settings.PLATFORM_ISSUER_LEGAL_NAME = "ERPlora S.L."
    assert in_each(business_name, platform)[1] == "ERPlora S.L."


def test_a_demo_has_no_name():
    Hub.objects.filter(slug=A.key).update(is_demo=True, name="")
    assert business_name(A) == ""


def test_it_reads_as_the_platform_whatever_the_caller_may_see():
    Hub.objects.filter(slug=A.key).update(name="Salón Aurora")
    clerk = OperationContext(scope=A, actor="clerk", permissions=frozenset({"website.manage"}))
    with pytest.raises(PermissionDenied):
        get("base.business.get")(clerk, BusinessIn())
    assert business_name(clerk.scope) == "Salón Aurora"
