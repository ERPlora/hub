"""The business's API keys (``erpk_live``), in Employees › API keys.

Who runs the business creates a key with a name, a pace (requests a minute) and what it may do — read, create, update
and delete, on every app or app by app, never more than its maker may do — and sees its token once; the hub keeps only
its digest. The key reaches only
the operations its apps publish (``expose_api``), of the apps this business has, with the same checks as anyone; it is
rotated (a new token, the old one stops at once) and revoked (at once, for good). A key lives in its hub's own
database: a key of one business never opens another. A business without its own database is not served at all, so
no token gets in there.
"""

import hashlib
import json
import time
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone
from live.models import OutboxEvent
from live.operations import registry

from apps.customer.models import Consent, Customer
from apps.inventory.models import Category
from apps.tax.models import TaxCategory
from base import api_keys, permissions
from base.api_actions import ACTIONS, CREATE, DELETE, READ, UPDATE, action_of
from base.models.api_keys import ApiKey
from base.models import Membership
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.routes import bound_routes, spa_routes

HUB_DB = pytest.mark.django_db(databases=hubs.HUB_DATABASES)


@pytest.fixture(autouse=True)
def pace_clock(monkeypatch):
    """A key's pace counts per minute of the clock, so a test's requests could fall in two minutes, depending on the
    second the suite runs. Its clock stands still at a minute's last instant, the worst case: every request of the test
    counts in that minute until the test moves ``pace_clock.now``. Only the pace's clock: the rest keeps the real one."""
    clock = SimpleNamespace(now=time.time() // 60 * 60 + 59.9)
    monkeypatch.setattr(api_keys, "time", SimpleNamespace(time=lambda: clock.now))
    return clock


def member(slug: str, role: str = "hub_admin", username: str = "saas:1"):
    user, _ = get_user_model().objects.get_or_create(username=username, defaults={"first_name": "Olga"})
    Membership.objects.get_or_create(user=user, host=slug, defaults={"role": role})
    return user


def host(hub) -> str:
    return f"{hub.slug}.localhost:8000"


def post(client, hub_host, path, body=None, **headers):
    return client.post(f"/api{path}", json.dumps(body or {}), content_type="application/json", HTTP_HOST=hub_host, **headers)


def get(client, hub_host, path, **headers):
    return client.get(f"/api{path}", HTTP_HOST=hub_host, **headers)


def bearer(token: str) -> dict:
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def code(response) -> str:
    return response.json()["error"]["code"]


def create(client, hub, **fields) -> dict:
    body = {"name": "Gestoría — facturas", "rate_per_minute": 60, "scopes": {"*": list(ACTIONS)}, **fields}
    response = post(client, host(hub), "/keys", body)
    assert response.status_code == 200, response.content
    return response.json()


@pytest.fixture
def admin_on_a(client, hub_a):
    client.force_login(member(hub_a.slug))
    return client


CARTS = "/cart_checkout/carts"
TAX_CATEGORIES = "/tax/categories"
CATEGORIES = "/inventory/categories"
#: What each action's call of Inventory's categories answers when it opens.
OPENED = {READ: 200, CREATE: 201, UPDATE: 200, DELETE: 200}


def call(client, hub, action: str, key: dict):
    """The call of ``action`` on a category of Inventory, with ``key``; the category is made by whoever runs the
    business, so a key that does not create still has one to change or delete."""
    if action == READ:
        return get(client, host(hub), CATEGORIES, **key)
    if action == CREATE:
        return post(client, host(hub), CATEGORIES, {"name": "Bebidas"}, **key)
    with use_hub(hub):
        category = Category.objects.create(name=f"C {Category.objects.count()}", slug=f"c-{Category.objects.count()}")
    if action == UPDATE:
        return post(client, host(hub), f"{CATEGORIES}/update", {"id": str(category.id), "name": "Otra"}, **key)
    return post(client, host(hub), f"{CATEGORIES}/delete", {"id": str(category.id)}, **key)


class TestWithoutItsOwnDatabase:
    """A business without its own database is not served at all: its door answers 503 before any key is read, made or
    accepted."""

    @pytest.mark.django_db
    def test_the_screen_and_a_new_key_answer_503_and_nothing_is_created(self, client):
        client.force_login(member("a"))
        listed = get(client, "a.localhost:8000", "/keys")
        refused = post(client, "a.localhost:8000", "/keys", {"name": "X", "rate_per_minute": 60, "scopes": {"*": ["read"]}})
        assert [(answer.status_code, code(answer)) for answer in (listed, refused)] == [(503, "base.hub_maintenance")] * 2

    @pytest.mark.django_db
    def test_no_token_gets_in(self, client):
        response = get(client, "a.localhost:8000", CARTS, **bearer("erpk_live_" + "x" * 43))
        assert (response.status_code, code(response)) == (503, "base.hub_maintenance")


@HUB_DB
class TestCreate:
    """The token once; the hub keeps its digest and its beginning."""

    def test_the_token_is_shown_once_and_kept_as_its_digest(self, admin_on_a, hub_a):
        answer = create(admin_on_a, hub_a)
        token = answer["token"]
        assert token.startswith("erpk_live_") and len(token) >= 50
        assert answer["key"]["prefix"] == token[: api_keys.PREFIX_LENGTH]
        assert answer["key"]["name"] == "Gestoría — facturas"
        with use_hub(hub_a):
            kept = ApiKey.objects.get()
        assert kept.token_digest == hashlib.sha256(token.encode()).hexdigest()
        assert token not in json.dumps([getattr(kept, field.attname) for field in ApiKey._meta.fields], default=str)
        listed = get(admin_on_a, host(hub_a), "/keys").json()
        assert set(listed) == {"keys", "apps", "grantable"}
        assert "token" not in listed["keys"][0] and token not in json.dumps(listed)
        assert listed["keys"][0]["created_by"] == "Olga"

    def test_its_event_carries_no_token(self, admin_on_a, hub_a):
        token = create(admin_on_a, hub_a)["token"]
        with use_hub(hub_a):
            event = OutboxEvent.objects.get(name="base.api_key.created")
        assert token not in json.dumps(event.payload)

    @pytest.mark.parametrize(
        ("fields", "field"),
        [
            ({"name": "  "}, "name"),
            ({"rate_per_minute": 0}, "rate_per_minute"),
            ({"rate_per_minute": 10_001}, "rate_per_minute"),
            ({"scopes": {}}, "scopes"),
            ({"scopes": {"cart_checkout": []}}, "scopes"),
            ({"scopes": {"nope": ["read"]}}, "scopes"),
            # Customers publishes only what it reads: no key creates a customer.
            ({"scopes": {"customer": ["create"]}}, "scopes"),
            ({"scopes": {"cart_checkout": ["write"]}}, "scopes"),
        ],
    )
    def test_what_is_wrong_is_said_on_its_field(self, admin_on_a, hub_a, fields, field):
        body = {"name": "Gestoría", "rate_per_minute": 60, "scopes": {"*": ["read"]}, **fields}
        response = post(admin_on_a, host(hub_a), "/keys", body)
        assert response.status_code == 422, response.content
        # Said on its field: the field itself, or a path inside it (``scopes.cart_checkout.0``).
        assert any(key.split(".")[0] == field for key in response.json()["error"]["fields"])

    @pytest.mark.parametrize(
        ("fields", "field"),
        [
            ({"name": "  "}, "name"),
            ({"scopes": {}}, "scopes"),
            ({"scopes": {"nope": ["read"]}}, "scopes"),
            ({"scopes": {"customer": ["create"]}}, "scopes"),
        ],
    )
    def test_a_field_is_refused_in_words_a_person_can_read(self, admin_on_a, hub_a, fields, field):
        # A form says on top what no field shows (FormModal, hub#833): a code or an app's id would reach the person.
        body = {"name": "Gestoría", "rate_per_minute": 60, "scopes": {"*": ["read"]}, **fields}
        error = post(admin_on_a, host(hub_a), "/keys", body).json()["error"]
        assert error["fields"] == {field: error["message"]}

    def test_only_who_runs_the_business(self, client, hub_a):
        client.force_login(member(hub_a.slug, role="hub_manager", username="saas:4"))
        response = post(client, host(hub_a), "/keys", {"name": "X", "rate_per_minute": 60, "scopes": {"*": ["read"]}})
        assert code(response) == "permission_denied"
        assert code(get(client, host(hub_a), "/keys")) == "permission_denied"


@HUB_DB
class TestUse:
    """A key reaches what its apps publish, read or write as it says, and nothing else."""

    def test_a_read_key_reads_and_does_not_write(self, admin_on_a, client, hub_a):
        token = create(admin_on_a, hub_a, scopes={"*": [READ]})["token"]
        client.logout()
        assert get(client, host(hub_a), CARTS, **bearer(token)).status_code == 200
        refused = post(client, host(hub_a), CARTS, {"session_token": "sess_api001"}, **bearer(token))
        assert (refused.status_code, code(refused)) == (403, "base.api_key_scope")

    def test_a_key_that_creates_updates_and_deletes_writes_and_does_not_read(self, admin_on_a, client, hub_a):
        token = create(admin_on_a, hub_a, scopes={"*": [CREATE, UPDATE, DELETE]})["token"]
        client.logout()
        created = post(client, host(hub_a), CARTS, {"session_token": "sess_api002"}, **bearer(token))
        assert created.status_code == 201, created.content
        assert code(get(client, host(hub_a), CARTS, **bearer(token))) == "base.api_key_scope"

    def test_a_key_per_app_reaches_its_apps_only(self, admin_on_a, client, hub_a):
        token = create(admin_on_a, hub_a, scopes={"cart_checkout": [READ]})["token"]
        client.logout()
        assert get(client, host(hub_a), CARTS, **bearer(token)).status_code == 200
        assert code(get(client, host(hub_a), TAX_CATEGORIES, **bearer(token))) == "base.api_key_scope"

    def test_a_full_key_does_both(self, admin_on_a, client, hub_a):
        token = create(admin_on_a, hub_a)["token"]
        client.logout()
        assert get(client, host(hub_a), TAX_CATEGORIES, **bearer(token)).status_code == 200
        assert post(client, host(hub_a), CARTS, {"session_token": "sess_api003"}, **bearer(token)).status_code == 201

    @pytest.mark.parametrize("action", ACTIONS)
    def test_each_action_opens_its_own_calls_only(self, admin_on_a, client, hub_a, action):
        token = create(admin_on_a, hub_a, scopes={"inventory": [action]})["token"]
        client.logout()
        answers = {each: call(client, hub_a, each, bearer(token)) for each in ACTIONS}
        assert {each: answer.status_code for each, answer in answers.items() if answer.status_code < 400} == {
            action: OPENED[action]
        }
        assert {code(answer) for each, answer in answers.items() if each != action} == {"base.api_key_scope"}

    def test_a_key_that_reads_and_creates_in_one_app_does_just_that(self, admin_on_a, client, hub_a):
        token = create(admin_on_a, hub_a, scopes={"inventory": [READ, CREATE]})["token"]
        client.logout()
        key = bearer(token)
        made = post(client, host(hub_a), CATEGORIES, {"name": "Postres"}, **key)
        assert made.status_code == 201, made.content
        assert [row["name"] for row in get(client, host(hub_a), CATEGORIES, **key).json()["rows"]] == ["Postres"]
        changed = post(client, host(hub_a), f"{CATEGORIES}/update", {"id": made.json()["id"], "name": "Dulces"}, **key)
        gone = post(client, host(hub_a), f"{CATEGORIES}/delete", {"id": made.json()["id"]}, **key)
        elsewhere = get(client, host(hub_a), CARTS, **key)
        assert {code(changed), code(gone), code(elsewhere)} == {"base.api_key_scope"}

    def test_what_no_app_publishes_never_opens_to_a_key(self, admin_on_a, client, hub_a):
        token = create(admin_on_a, hub_a)["token"]
        client.logout()
        response = post(client, host(hub_a), "/customer/customers", {"name": "Ana"}, **bearer(token))
        assert response.status_code == 401
        assert get(client, host(hub_a), "/keys", **bearer(token)).status_code == 401

    def test_a_key_sees_and_writes_the_costs_as_whoever_makes_it(self, admin_on_a, client, hub_a):
        """Only the owner and an administrator make a key, and they see every data of the business: so does their key.
        An integration that keeps a product's cost reads it and sends it, as before the costs had a permission."""
        token = create(admin_on_a, hub_a)["token"]
        client.logout()
        with use_hub(hub_a):
            TaxCategory.objects.get_or_create(key="test.general", defaults={"name": "General"})
        tea = {"name": "Tea", "sku": "TEA", "price": 150, "cost": 90, "tax_category_key": "test.general"}
        made = post(client, host(hub_a), "/inventory/products", tea, **bearer(token))
        assert made.status_code == 201, made.content
        rows = get(client, host(hub_a), "/inventory/products", **bearer(token)).json()["rows"]
        assert [(row["sku"], row["cost"]) for row in rows] == [("TEA", 90)]

    def test_a_key_reads_the_address_a_customer_s_consent_was_given_for_as_whoever_makes_it(self, admin_on_a, client, hub_a):
        """An integration that writes to the customers reads where each one agreed to be written to."""
        token = create(admin_on_a, hub_a)["token"]
        client.logout()
        with use_hub(hub_a):
            marta = Customer.objects.create(name="Marta Ruiz", email="marta@example.com")
            Consent.objects.create(customer=marta, channel="email", state="granted", contact_point="marta@example.com",
                                   source="counter", occurred_at=timezone.now(), created_at=timezone.now())
        state = get(client, host(hub_a), f"/customer/consents/state?customer_id={marta.id}", **bearer(token))
        assert [row["contact_point"] for row in state.json()["rows"]] == ["marta@example.com"]

    def test_its_last_use_is_kept(self, admin_on_a, client, hub_a):
        token = create(admin_on_a, hub_a)["token"]
        assert get(admin_on_a, host(hub_a), "/keys").json()["keys"][0]["last_used_at"] is None
        get(client, host(hub_a), CARTS, **bearer(token))
        client.force_login(member(hub_a.slug))
        assert get(client, host(hub_a), "/keys").json()["keys"][0]["last_used_at"] is not None

    def test_a_token_nobody_issued_is_401_and_too_many_from_one_address_wait(self, client, hub_a):
        for _ in range(api_keys.KEY_ADDRESS_LIMIT.attempts):
            assert get(client, host(hub_a), CARTS, **bearer("erpk_live_" + "n" * 43)).status_code == 401
        waiting = get(client, host(hub_a), CARTS, **bearer("erpk_live_" + "n" * 43))
        assert (waiting.status_code, code(waiting)) == (429, "base.too_many_api_key_tries")

    def test_its_pace_is_its_requests_a_minute(self, admin_on_a, client, hub_a, pace_clock):
        """The pace's clock stands still at the minute's last instant (``pace_clock``): on the wall clock the third
        request now and then fell in the next minute and went through (the CI of hub#377)."""
        token = create(admin_on_a, hub_a, rate_per_minute=2)["token"]
        client.logout()
        assert [get(client, host(hub_a), CARTS, **bearer(token)).status_code for _ in range(2)] == [200, 200]
        third = get(client, host(hub_a), CARTS, **bearer(token))
        assert (third.status_code, code(third)) == (429, "base.api_key_rate_limited")
        pace_clock.now += 0.2  # the next minute counts again
        assert get(client, host(hub_a), CARTS, **bearer(token)).status_code == 200

    def test_a_key_of_one_business_never_opens_another(self, admin_on_a, client, hub_a, hub_b):
        """The frontier is the database: the key of A does not exist in B's."""
        token = create(admin_on_a, hub_a)["token"]
        client.logout()
        assert get(client, host(hub_a), CARTS, **bearer(token)).status_code == 200
        assert get(client, host(hub_b), CARTS, **bearer(token)).status_code == 401
        with use_hub(hub_b):
            assert ApiKey.objects.count() == 0


@HUB_DB
class TestRotateAndRevoke:
    """A new token and the old one stops at once; a revoked key stops for good."""

    def test_rotating_gives_a_new_token_and_the_old_one_stops(self, admin_on_a, hub_a):
        client = Client()
        made = create(admin_on_a, hub_a)
        rotated = post(admin_on_a, host(hub_a), "/keys/rotate", {"id": made["key"]["id"]})
        assert rotated.status_code == 200, rotated.content
        new = rotated.json()["token"]
        assert new != made["token"] and rotated.json()["key"]["prefix"] == new[: api_keys.PREFIX_LENGTH]
        assert get(client, host(hub_a), CARTS, **bearer(made["token"])).status_code == 401
        assert get(client, host(hub_a), CARTS, **bearer(new)).status_code == 200
        with use_hub(hub_a):
            assert OutboxEvent.objects.filter(name="base.api_key.rotated").count() == 1

    def test_revoking_stops_it_at_once_and_for_good(self, admin_on_a, hub_a):
        client = Client()
        made = create(admin_on_a, hub_a)
        revoked = post(admin_on_a, host(hub_a), "/keys/revoke", {"id": made["key"]["id"]})
        assert revoked.status_code == 200, revoked.content
        assert revoked.json()["key"]["revoked_at"] is not None
        assert get(client, host(hub_a), CARTS, **bearer(made["token"])).status_code == 401
        again = post(admin_on_a, host(hub_a), "/keys/revoke", {"id": made["key"]["id"]})
        assert (again.status_code, code(again)) == (409, "base.api_key_revoked")
        rotate = post(admin_on_a, host(hub_a), "/keys/rotate", {"id": made["key"]["id"]})
        assert (rotate.status_code, code(rotate)) == (409, "base.api_key_revoked")

    def test_a_key_that_is_not_there(self, admin_on_a, hub_a):
        response = post(admin_on_a, host(hub_a), "/keys/revoke", {"id": "0199aaaa-0000-7000-8000-000000000009"})
        assert (response.status_code, code(response)) == (404, "base.api_key_not_found")


@HUB_DB
class TestTheList:
    """Each key, what it may do, its pace, its last use; the apps a key can reach, with what each publishes; and the
    most who asks may give a key."""

    def test_each_key_and_what_it_may_do(self, admin_on_a, hub_a):
        create(admin_on_a, hub_a, name="Read", scopes={"*": [READ]}, rate_per_minute=30)
        create(admin_on_a, hub_a, name="Carts", scopes={"cart_checkout": [DELETE, READ, DELETE]})
        keys = {key["name"]: key for key in get(admin_on_a, host(hub_a), "/keys").json()["keys"]}
        assert (keys["Read"]["scopes"], keys["Read"]["rate_per_minute"]) == ({"*": [READ]}, 30)
        assert keys["Carts"]["scopes"] == {"cart_checkout": [READ, DELETE]}
        assert keys["Carts"]["revoked_at"] is None and "mode" not in keys["Carts"]

    def test_a_key_left_in_the_old_shape_lists_only_its_actions(self, admin_on_a, hub_a):
        """While a deploy migrates, the code of before still writes a key per app with «write»: the list shows what it
        can do now (its reading) instead of failing."""
        made = create(admin_on_a, hub_a, scopes={"tax": [READ]})["key"]
        with use_hub(hub_a):
            ApiKey.objects.filter(pk=made["id"]).update(scopes={"tax": ["read", "write"], "sale": ["write"]})
        [listed] = get(admin_on_a, host(hub_a), "/keys").json()["keys"]
        assert listed["scopes"] == {"tax": [READ]}

    def test_the_apps_that_publish_their_api_with_what_each_publishes(self, admin_on_a, hub_a):
        apps = {app["id"]: app for app in get(admin_on_a, host(hub_a), "/keys").json()["apps"]}
        assert apps["cart_checkout"]["actions"] == list(ACTIONS)
        assert apps["tax"]["actions"] == [READ, UPDATE]
        assert apps["customer"]["actions"] == [READ]
        assert "base" not in apps and all(app["name"] for app in apps.values())

    def test_who_runs_the_business_may_give_a_key_all_it_publishes(self, admin_on_a, hub_a):
        listed = get(admin_on_a, host(hub_a), "/keys").json()
        assert listed["grantable"] == {"*": list(ACTIONS), **{app["id"]: app["actions"] for app in listed["apps"]}}


@pytest.fixture
def cannot_delete_in_inventory(monkeypatch):
    """Whoever runs the business holds, today, nothing that deletes in Inventory (as a role made by the business could
    leave out)."""
    deleting = {op.permission for op in registry.values() if op.app_label == "inventory" and action_of(op) == DELETE}
    assert deleting, "Inventory publishes no deletion any more: pick another app"
    role_permissions = permissions.permissions_of_role
    monkeypatch.setattr(permissions, "permissions_of_role", lambda role: role_permissions(role) - deleting)


@HUB_DB
@pytest.mark.usefixtures("cannot_delete_in_inventory")
class TestNeverMoreThanItsMaker:
    """A key is given only what whoever makes it may do on each app: asked for more, nothing is made."""

    @pytest.mark.parametrize("scopes", [{"inventory": [READ, DELETE]}, {"*": [READ, DELETE]}])
    def test_more_than_its_maker_may_do_is_refused_on_its_field(self, admin_on_a, hub_a, scopes):
        response = post(admin_on_a, host(hub_a), "/keys", {"name": "Tienda", "rate_per_minute": 60, "scopes": scopes})
        assert (response.status_code, code(response)) == (403, "base.api_key_beyond_maker")
        error = response.json()["error"]
        assert error["fields"] == {"scopes": error["message"]}
        with use_hub(hub_a):
            assert ApiKey.objects.count() == 0

    @pytest.mark.parametrize("scopes", [{"inventory": [READ, CREATE, UPDATE]}, {"*": [READ, CREATE, UPDATE]}])
    def test_what_its_maker_may_do_is_given(self, admin_on_a, hub_a, scopes):
        assert create(admin_on_a, hub_a, scopes=scopes)["key"]["scopes"] == scopes

    def test_the_most_it_may_give_leaves_out_what_its_maker_may_not_do(self, admin_on_a, hub_a):
        listed = get(admin_on_a, host(hub_a), "/keys").json()
        apps = {app["id"]: app for app in listed["apps"]}
        assert apps["inventory"]["actions"] == list(ACTIONS)
        assert listed["grantable"]["inventory"] == [READ, CREATE, UPDATE]
        assert listed["grantable"]["*"] == [READ, CREATE, UPDATE]
        assert listed["grantable"]["cart_checkout"] == list(ACTIONS)


KEY_ROUTES = {
    ("GET", "/keys", "base.api_key.list"),
    ("POST", "/keys", "base.api_key.create"),
    ("POST", "/keys/rotate", "base.api_key.rotate"),
    ("POST", "/keys/revoke", "base.api_key.revoke"),
}


def test_the_spas_route_map_names_every_route_of_the_keys():
    from base.api.people import router

    assert KEY_ROUTES <= bound_routes(router)
    mine = {op for _, _, op in KEY_ROUTES}
    assert {route for route in spa_routes("base.") if route[2] in mine} == KEY_ROUTES
