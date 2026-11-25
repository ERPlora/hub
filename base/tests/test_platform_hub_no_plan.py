"""ERPlora's own hub is nobody's customer: it has no plan, and never will. Whoever is in it sees what it uses with no
promise of a plan, and is offered nothing to buy; the pages of erplora.com that run it and its people stay. A business
(``hub_a``) is offered the same as always, beside it.
"""

import pytest

from base.models import Hub
from base.tenancy.tests.business import A, HUB_DB
from base.tests.test_access_pin import door
from base.tests.test_auth_views import callback
from base.tests.test_platform_hub_host import erp
from base.tests.test_platform_hub_people import A_HOST, ANA, ERP, arrives, member, send
from base.tests.test_saas_pass import ask, read_as_the_saas, the_pass
from base.tests.test_spa import json_block

__all__ = ["erp"]

pytestmark = [HUB_DB, pytest.mark.usefixtures("spa_manifest", "erp", "hub_a")]

SAAS = "http://localhost:8001"
#: What erplora.com says of a business that owes a payment, in a photo of ERPlora's own hub.
OWING = {"status": "past_due", "plan": {"slug": "free", "max_users": 1, "max_devices": 1, "max_apps": 1}}


@pytest.fixture
def enter(client, fake_saas):
    """Enters a host as its owner, with the account of erplora.com."""

    def enter_at(host: str):
        fake_saas(body=arrives(ANA, "hub_owner"))
        assert callback(client, {"code": "c1", "next": "/"}, host=host).status_code == 302
        return client

    return enter_at


def home_of(client, host: str) -> dict:
    return json_block(client.get("/", HTTP_HOST=host, HTTP_ACCEPT="text/html"), "hub-home")[1]


def api(client, path: str, host: str) -> dict:
    answer = client.get(path, HTTP_HOST=host)
    assert answer.status_code == 200, answer.content[:300]
    return answer.json()


class TestNothingToBuy:
    def test_its_menu_gets_no_address_of_a_plan(self, enter):
        assert home_of(enter(ERP), ERP)["plan_url"] == ""

    def test_it_keeps_its_people_and_its_panel_on_erplora_com(self, enter, erp):
        home = home_of(enter(ERP), ERP)

        assert home["account_url"] == f"{SAAS}/dashboard/account"
        assert home["manage_url"] == f"{SAAS}/dashboard/businesses/{erp.id}"
        assert home["members_url"] == f"{SAAS}/dashboard/businesses/{erp.id}/members"

    def test_its_apps_get_no_address_of_the_store_nor_of_a_plan(self, enter):
        listed = api(enter(ERP), "/api/apps", ERP)

        assert (listed["store_url"], listed["plan_url"], listed["max_apps"]) == ("", "", None)

    def test_its_entrance_gets_no_address_of_a_plan(self, client):
        assert door(client, ERP)["plan_url"] == ""

    def test_its_whatsapp_gets_no_address_of_a_plan(self, enter):
        assert api(enter(ERP), "/api/whatsapp_inbox/channel", ERP)["plans_url"] == ""

    def test_no_pass_leads_to_a_plan_it_does_not_have(self, enter):
        refused = ask(enter(ERP), "plan", ERP)

        assert (refused.status_code, refused.json()["error"]["code"]) == (409, "base.saas_pass_no_plan")
        assert "url" not in refused.json()

    @pytest.mark.parametrize(
        ("locale", "said"), [("en", "This business has no plan."), ("es", "Este negocio no tiene plan.")]
    )
    def test_the_refusal_speaks_the_person_s_language(self, client, fake_saas, locale, said):
        fake_saas(body={**arrives(ANA, "hub_owner"), "locale": locale})
        callback(client, {"code": "c1", "next": "/"}, host=ERP)

        assert ask(client, "plan", ERP).json()["error"]["message"] == said

    def test_the_pass_to_its_panel_is_signed(self, enter):
        said = read_as_the_saas(the_pass(ask(enter(ERP), "business", ERP)))

        assert (said["hub"], said["next"]) == ("erp", "business")


class TestItsUsage:
    def test_it_says_it_is_erplora_s_own_and_no_plan_is_known(self, enter):
        usage = api(enter(ERP), "/api/system/plan", ERP)

        assert (usage["platform"], usage["known"], usage["plan_slug"], usage["demo"]) == (True, False, None, False)
        limits = {thing: usage[thing]["limit"] for thing in ("people", "devices", "apps", "files")}
        assert limits == {"people": None, "devices": None, "apps": None, "files": None}

    def test_it_says_what_it_uses(self, enter):
        usage = api(enter(ERP), "/api/system/plan", ERP)

        assert (usage["people"]["used"], usage["devices"]["used"]) == (1, 1)

    def test_a_photo_with_a_plan_and_a_debt_brings_neither(self, enter, client, erp):
        enter(ERP)
        assert send(client, erp, 1, member(ANA, "hub_owner"), **OWING).json()["applied"] is True

        usage = api(client, "/api/system/plan", ERP)
        assert (usage["platform"], usage["known"]) == (True, False)
        notices = api(client, "/api/home/bell", ERP)
        assert {row["key"] for row in notices["counters"]} & {"base.plan_limits", "base.payment_pending"} == set()


class TestAnyOtherBusiness:
    def test_is_offered_to_buy_as_always(self, enter, hub_a):
        client = enter(A_HOST)
        store = f"{SAAS}/dashboard/store"

        assert home_of(client, A_HOST)["plan_url"] == f"{store}/plans?business={hub_a.id}"
        listed = api(client, "/api/apps", A_HOST)
        assert listed["store_url"] == f"{store}/modules?business={hub_a.id}"
        assert listed["plan_url"] == f"{store}/plans?business={hub_a.id}"
        assert door(client, A_HOST)["plan_url"] == f"{store}/plans"
        assert read_as_the_saas(the_pass(ask(client, "plan", A_HOST)))["next"] == "plan"

    def test_whose_plan_has_not_come_yet_is_no_hub_of_erplora_s(self, enter):
        Hub.objects.filter(slug=A.key).update(state={})

        usage = api(enter(A_HOST), "/api/system/plan", A_HOST)

        assert (usage["platform"], usage["known"]) == (False, False)

    def test_on_a_plan_is_no_hub_of_erplora_s_either(self, enter):
        plan = {"slug": "starter", "max_users": 3, "max_devices": 2}
        Hub.objects.filter(slug=A.key).update(state={"plan": plan})

        usage = api(enter(A_HOST), "/api/system/plan", A_HOST)

        assert (usage["platform"], usage["known"], usage["plan_slug"]) == (False, True, "starter")
