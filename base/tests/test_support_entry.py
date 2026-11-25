"""ERPlora's support comes into a business only while the business lets it (BASE-F126).

erplora.com gives a person of its support a code with the role ``hub_support`` for a business they are not a member
of. With the business's support access on, the Hub opens their session on a copy of their own (``saas-support:<id>``),
with what an administrator may do but owning the business, and notes the entry among the support visits; it leaves no
trace among the business's people: not in Employees, nor among who can give access, nor in the plan's use, nor as a
device. With it off, the code opens nothing and a page of the Hub says why; turning it off ends the support sessions
open in the business, and nobody else's.

As in production, every business is on a database of its own: the business is ``hub_a``, another one ``hub_b``.
"""

import json

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.test import Client
from django.utils import timezone
from live.context import Scope, system_context
from live.models import OutboxEvent

from apps.staff.queries.accounts import list_accounts
from apps.staff.schemas.accounts import AccountListIn
from apps.whatsapp_inbox.queries.agents import team_roles
from base import access as access_rules
from base import auth, meter, queries, services
from base.models import Hub, HubUser, Membership
from base.models.access import Credential, TrustedDevice
from base.models.sessions import SessionOwner
from base.models.support_access import SupportAccess, SupportVisit
from base.permissions import permissions_of_role
from base.tenancy.context import use_hub
from base.tests.test_auth_views import A, B, B_HOST, HOST, ON_HUB_A, callback, me
from control.models import HubVisit

pytestmark = ON_HUB_A

SUPPORT_ID = "0199c4b0-0000-7000-8000-000000000901"
SUPPORT = {"user_id": SUPPORT_ID, "email": "sam@erplora.com", "name": "Sam", "locale": "en", "role": "hub_support"}
SUPPORT_COPY = f"saas-support:{SUPPORT_ID}"
ENTERED = "base.support_access.entered"


def turn(client, enabled: bool, host=HOST):
    body = json.dumps({"enabled": enabled})
    return client.post("/api/support-access/update", body, content_type="application/json", HTTP_HOST=host)


def api(client, path, host=HOST):
    response = client.get(f"/api{path}", HTTP_HOST=host)
    assert response.status_code == 200, response.content
    return response.json()


def support_enters(client, fake_saas, *, locale="en", next_path="/"):
    fake_saas(body={**SUPPORT, "locale": locale})
    return callback(client, {"code": "c1", "next": next_path})


def access(hub, *, enabled: bool) -> None:
    with use_hub(hub):
        SupportAccess.objects.create(enabled=enabled)


@pytest.fixture
def access_on(hub_a):
    access(hub_a, enabled=True)


@pytest.fixture
def owner(make_user):
    """Olga, the owner, signed in on another browser."""
    browser = Client()
    browser.force_login(make_user("saas:1", host=A, role=Membership.Role.OWNER, first_name="Olga"))
    return browser


class TestTheCode:
    def test_a_member_s_door_takes_the_support_role(self, fake_saas):
        fake_saas(body=SUPPORT)
        result = auth.redeem_code("c1", A)
        assert result.ok, result.error
        assert result.user.role == "hub_support"

    def test_the_hub_admin_never_takes_it(self, fake_saas):
        fake_saas(body=SUPPORT)
        result = auth.redeem_code("c1", A, audience=auth.HUB_ADMIN_AUDIENCE)
        assert (result.ok, result.error) == (False, auth.NOT_PLATFORM_STAFF)


class TestWithTheAccessOff:
    @pytest.mark.parametrize("saved", [False, True], ids=["never-set", "turned-off"])
    def test_the_entry_is_refused_with_a_page_and_opens_nothing(self, client, fake_saas, hub_a, saved):
        if saved:
            access(hub_a, enabled=False)
        response = support_enters(client, fake_saas)
        assert response.status_code == 403
        page = response.content.decode()
        assert "This business does not let support in" in page
        assert 'href="/auth/login?next=%2F"' in page
        assert me(client)["user"] is None
        assert not SessionOwner.objects.exists()
        assert not get_user_model().objects.filter(username=SUPPORT_COPY).exists()
        with use_hub(hub_a):
            assert not SupportVisit.objects.exists()
            assert not OutboxEvent.objects.filter(name=ENTERED).exists()

    def test_the_page_speaks_the_language_of_the_account(self, client, fake_saas):
        page = support_enters(client, fake_saas, locale="es").content.decode()
        assert "Este negocio no deja entrar a soporte" in page

    def test_another_business_s_access_does_not_open_this_one(self, client, fake_saas, hub_b):
        access(hub_b, enabled=True)
        assert support_enters(client, fake_saas).status_code == 403


@pytest.mark.usefixtures("access_on")
class TestWithTheAccessOn:
    def test_support_comes_in_as_an_administrator_who_does_not_own_the_business(self, client, fake_saas, hub_b):
        response = support_enters(client, fake_saas, next_path="/inventory")
        assert (response.status_code, response["Location"]) == (302, "/inventory")
        session = me(client)
        permissions = session["permissions"]
        assert session["role"] == "ERPlora support"
        assert permissions == sorted(permissions_of_role(Membership.Role.ADMIN))
        assert "base.administer_hub" in permissions and "base.own_business" not in permissions
        copy = get_user_model().objects.get(username=SUPPORT_COPY)
        assert (copy.is_staff, copy.is_superuser, copy.email) == (False, False, "sam@erplora.com")
        assert Membership.objects.get(user=copy).role == "hub_support"
        assert SessionOwner.objects.get().credential == "support"
        assert me(client, B_HOST)["permissions"] == []

    def test_each_entry_is_noted_among_the_visits_and_heard_live(self, client, fake_saas, owner, hub_a):
        support_enters(client, fake_saas)
        support_enters(Client(), fake_saas)
        with use_hub(hub_a):
            assert list(SupportVisit.objects.values_list("username", "name", "email")) == [
                (SUPPORT_COPY, "Sam", "sam@erplora.com")
            ] * 2
            assert OutboxEvent.objects.filter(name=ENTERED).count() == 2
        assert [visit["person"] for visit in api(owner, "/support-access")["visits"]] == ["Sam", "Sam"]

    def test_support_is_none_of_the_business_s_people(self, client, fake_saas, owner, make_user):
        support_enters(client, fake_saas)
        assert [person["id"] for person in api(owner, "/people")["people"]] == ["saas:1"]
        employee = Client()
        employee.force_login(make_user("saas:3", host=A, role=Membership.Role.EMPLOYEE, first_name="Eva"))
        assert api(employee, "/access/grantors") == {"grantors": [{"name": "Olga"}]}
        team = {item["key"]: item["state"] for item in api(owner, "/home/setup")["items"]}
        assert team["base.team"] == "done"
        Membership.objects.filter(user__username="saas:3").delete()
        team = {item["key"]: item["state"] for item in api(owner, "/home/setup")["items"]}
        assert team["base.team"] == "pending"

    def test_support_takes_no_place_device_nor_visit_of_the_plan(self, client, fake_saas, owner, hub_a):
        Hub.objects.filter(pk=hub_a.pk).update(state={"plan": {"max_users": 3, "max_devices": 2}})
        response = support_enters(client, fake_saas)
        usage = api(owner, "/system/plan")
        assert (usage["people"]["used"], usage["devices"]["used"]) == (1, 0)
        assert not HubVisit.objects.exists()
        assert not response.cookies.get("hub_device")
        with use_hub(hub_a):
            assert not TrustedDevice.objects.exists()

    def test_the_activity_of_support_is_not_the_business_s(self, client, fake_saas, owner, monkeypatch):
        monkeypatch.setattr(meter, "_recording", True)
        monkeypatch.setattr(meter, "_seen", {})
        support_enters(client, fake_saas)
        me(client)
        me(owner)
        today = timezone.now().date()
        assert set(meter._seen) == {(A, today, "1")}

    def test_support_s_entry_and_a_device_s_end_no_session_of_each_other(self, client, fake_saas, hub_a):
        Hub.objects.filter(pk=hub_a.pk).update(state={"plan": {"max_devices": 1}})
        till, phone = Client(), Client()
        fake_saas()
        callback(till, {"code": "c1", "next": "/"})
        support_enters(client, fake_saas)
        assert me(till)["user"] is not None
        fake_saas()
        callback(phone, {"code": "c1", "next": "/"})
        assert me(till)["user"] is None
        assert me(client)["user"] is not None

    def test_the_pickers_of_people_leave_support_out(self, client, fake_saas, owner, hub_a):
        support_enters(client, fake_saas)
        ctx = system_context(Scope("host", A))
        with use_hub(hub_a):
            HubUser.objects.create(username="saas:1", name="Olga")
            assert HubUser.objects.filter(username=SUPPORT_COPY).exists()
            assert team_roles(ctx) == {"saas:1": "hub_owner"}
            rows = list_accounts(ctx, AccountListIn()).rows
            Credential.objects.create(username="saas:1", pin_hash="x")
            Credential.objects.create(username=SUPPORT_COPY, pin_hash="y")
            on_the_pin_pad = [credential.username for credential, _ in queries.access.pin_people(A)]
        assert [row.name for row in rows] == ["Olga"]
        assert on_the_pin_pad == ["saas:1"]

    def test_a_pin_or_a_badge_of_support_opens_no_till(self, client, fake_saas, make_user, hub_a):
        support_enters(client, fake_saas)
        make_user("saas:3", host=A, role=Membership.Role.EMPLOYEE, first_name="Eva")
        cards = {"saas:3": "CARD-0003", SUPPORT_COPY: "CARD-0009"}
        with use_hub(hub_a):
            key = services.devices.badge_key()
            people = [
                Credential.objects.create(
                    username=username,
                    pin_hash=make_password("4821"),
                    badge_digest=access_rules.badge_digest(card, key=key),
                )
                for username, card in cards.items()
            ]
            by_pin = [queries.access.pin_owner(A, str(person.pk), "4821") for person in people]
            by_badge = [services.devices.badge_owner(A, card)[0] for card in cards.values()]
        assert [user and user.get_username() for user in by_pin] == ["saas:3", None]
        assert [user and user.get_username() for user in by_badge] == ["saas:3", None]


@pytest.mark.usefixtures("access_on")
class TestTurningItOff:
    def test_it_ends_the_support_sessions_and_nobody_else_s(self, client, fake_saas, owner):
        support_enters(client, fake_saas)
        employee = Client()
        fake_saas()
        callback(employee, {"code": "c1", "next": "/"})
        response = turn(owner, False)
        assert response.status_code == 200, response.content
        assert me(client)["user"] is None
        assert me(employee)["user"] is not None
        assert me(owner)["user"] is not None

    def test_turning_it_on_again_ends_nothing(self, client, fake_saas, owner):
        support_enters(client, fake_saas)
        assert turn(owner, True).status_code == 200
        assert me(client)["user"] is not None

    def test_another_business_s_switch_does_not_end_this_one_s(self, client, fake_saas, make_user, hub_b):
        support_enters(client, fake_saas)
        bea = Client()
        bea.force_login(make_user("saas:4", host=B, role=Membership.Role.OWNER, first_name="Bea"))
        assert turn(bea, False, host=B_HOST).status_code == 200
        assert me(client)["user"] is not None
