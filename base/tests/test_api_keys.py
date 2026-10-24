"""BASE-G146…G149, G03, G05, G25 and G37: the business's API keys (``erpk_live``), in Employees › API keys.

Who runs the business creates a key with a name, a pace (requests a minute) and what it may do — everything, read only,
write only, or per app, read and write — and sees its token once; the hub keeps only its digest. The key reaches only
the operations its apps publish (``expose_api``), of the apps this business has, with the same checks as anyone; it is
rotated (a new token, the old one stops at once) and revoked (at once, for good). A key lives in its hub's own
database: a key of one business never opens another (PLAN-HUB §3, «API keys»). While a business still shares phase 1's
database with others that frontier cannot be kept, so there its keys are «not available yet» and no token gets in.
"""

import hashlib
import json

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client
from live.models import OutboxEvent

from base import api_keys
from base.models import ApiKey, Membership
from base.tenancy import context
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs

HUB_DB = pytest.mark.django_db(databases=hubs.HUB_DATABASES)


@pytest.fixture(autouse=True)
def as_in_production(monkeypatch):
    """Every request opens its own database context, as in production (``base/tenancy/tests/conftest.py``)."""
    monkeypatch.setattr(context, "_test_fallback", None)
    cache.clear()
    yield
    cache.clear()


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
    body = {"name": "Gestoría — facturas", "rate_per_minute": 60, "mode": "full", "scopes": {}, **fields}
    response = post(client, host(hub), "/keys", body)
    assert response.status_code == 200, response.content
    return response.json()


@pytest.fixture
def admin_on_a(client, hub_a):
    client.force_login(member(hub_a.slug))
    return client


CARTS = "/cart_checkout/carts"
TAX_CATEGORIES = "/tax/categories"


class TestNotYetAvailable:
    """A business on phase 1's shared database: its keys would open its neighbours', so none is made nor accepted."""

    @pytest.mark.django_db
    def test_the_screen_says_not_yet_and_nothing_is_created(self, client):
        client.force_login(member("a"))
        listed = get(client, "a.localhost:8000", "/keys")
        assert listed.status_code == 200, listed.content
        assert (listed.json()["available"], listed.json()["keys"]) == (False, [])
        refused = post(client, "a.localhost:8000", "/keys", {"name": "X", "rate_per_minute": 60, "mode": "full", "scopes": {}})
        assert (refused.status_code, code(refused)) == (409, "base.api_keys_unavailable")
        assert "not available yet" in refused.json()["error"]["message"]

    @pytest.mark.django_db
    def test_no_token_gets_in(self, client):
        response = get(client, "a.localhost:8000", CARTS, **bearer("erpk_live_" + "x" * 43))
        assert response.status_code == 401

    @pytest.mark.django_db
    def test_not_even_one_that_is_in_the_shared_tables(self, client):
        """A key row in phase 1's shared tables (left by hand, or by a business before it moved) would be anybody's."""
        token = api_keys.new_token()
        with context.use_shared_database():
            ApiKey.objects.create(name="Planted", prefix=token[: api_keys.PREFIX_LENGTH], token_digest=api_keys.digest(token), mode="full")
        for slug in ("a", "b"):
            assert get(client, f"{slug}.localhost:8000", CARTS, **bearer(token)).status_code == 401


@HUB_DB
class TestCreate:
    """BASE-G146: the token once; the hub keeps its digest and its beginning."""

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
        assert listed["available"] is True
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
            ({"mode": "per_app", "scopes": {}}, "scopes"),
            ({"mode": "per_app", "scopes": {"nope": ["read"]}}, "scopes"),
            ({"mode": "per_app", "scopes": {"cart_checkout": ["delete"]}}, "scopes"),
        ],
    )
    def test_what_is_wrong_is_said_on_its_field(self, admin_on_a, hub_a, fields, field):
        body = {"name": "Gestoría", "rate_per_minute": 60, "mode": "full", "scopes": {}, **fields}
        response = post(admin_on_a, host(hub_a), "/keys", body)
        assert response.status_code == 422, response.content
        # Said on its field: the field itself, or a path inside it (``scopes.cart_checkout.0``).
        assert any(key.split(".")[0] == field for key in response.json()["error"]["fields"])

    def test_only_who_runs_the_business(self, client, hub_a):
        client.force_login(member(hub_a.slug, role="hub_manager", username="saas:4"))
        response = post(client, host(hub_a), "/keys", {"name": "X", "rate_per_minute": 60, "mode": "full", "scopes": {}})
        assert code(response) == "permission_denied"
        assert code(get(client, host(hub_a), "/keys")) == "permission_denied"


@HUB_DB
class TestUse:
    """BASE-G25, G37: a key reaches what its apps publish, read or write as it says, and nothing else."""

    def test_a_read_key_reads_and_does_not_write(self, admin_on_a, client, hub_a):
        token = create(admin_on_a, hub_a, mode="read")["token"]
        client.logout()
        assert get(client, host(hub_a), CARTS, **bearer(token)).status_code == 200
        refused = post(client, host(hub_a), CARTS, {"session_token": "sess_api001"}, **bearer(token))
        assert (refused.status_code, code(refused)) == (403, "base.api_key_scope")

    def test_a_write_key_writes_and_does_not_read(self, admin_on_a, client, hub_a):
        token = create(admin_on_a, hub_a, mode="write")["token"]
        client.logout()
        created = post(client, host(hub_a), CARTS, {"session_token": "sess_api002"}, **bearer(token))
        assert created.status_code == 201, created.content
        assert code(get(client, host(hub_a), CARTS, **bearer(token))) == "base.api_key_scope"

    def test_a_key_per_app_reaches_its_apps_only(self, admin_on_a, client, hub_a):
        token = create(admin_on_a, hub_a, mode="per_app", scopes={"cart_checkout": ["read"]})["token"]
        client.logout()
        assert get(client, host(hub_a), CARTS, **bearer(token)).status_code == 200
        assert code(get(client, host(hub_a), TAX_CATEGORIES, **bearer(token))) == "base.api_key_scope"

    def test_a_full_key_does_both(self, admin_on_a, client, hub_a):
        token = create(admin_on_a, hub_a)["token"]
        client.logout()
        assert get(client, host(hub_a), TAX_CATEGORIES, **bearer(token)).status_code == 200
        assert post(client, host(hub_a), CARTS, {"session_token": "sess_api003"}, **bearer(token)).status_code == 201

    def test_what_no_app_publishes_never_opens_to_a_key(self, admin_on_a, client, hub_a):
        token = create(admin_on_a, hub_a)["token"]
        client.logout()
        response = post(client, host(hub_a), "/customer/customers", {"name": "Ana"}, **bearer(token))
        assert response.status_code == 401
        assert get(client, host(hub_a), "/keys", **bearer(token)).status_code == 401

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

    def test_its_pace_is_its_requests_a_minute(self, admin_on_a, client, hub_a):
        token = create(admin_on_a, hub_a, rate_per_minute=2)["token"]
        client.logout()
        assert [get(client, host(hub_a), CARTS, **bearer(token)).status_code for _ in range(2)] == [200, 200]
        third = get(client, host(hub_a), CARTS, **bearer(token))
        assert (third.status_code, code(third)) == (429, "base.api_key_rate_limited")

    def test_a_key_of_one_business_never_opens_another(self, admin_on_a, client, hub_a, hub_b):
        """The frontier is the database: the key of A does not exist in B's (PLAN-HUB §3)."""
        token = create(admin_on_a, hub_a)["token"]
        client.logout()
        assert get(client, host(hub_a), CARTS, **bearer(token)).status_code == 200
        assert get(client, host(hub_b), CARTS, **bearer(token)).status_code == 401
        with use_hub(hub_b):
            assert ApiKey.objects.count() == 0


@HUB_DB
class TestRotateAndRevoke:
    """BASE-G147, G148: a new token and the old one stops at once; a revoked key stops for good."""

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
    """BASE-G149: each key, what it may do, its pace, its last use; and the apps a key per app can reach."""

    def test_each_key_and_what_it_may_do(self, admin_on_a, hub_a):
        create(admin_on_a, hub_a, name="Read", mode="read", rate_per_minute=30)
        create(admin_on_a, hub_a, name="Carts", mode="per_app", scopes={"cart_checkout": ["read", "write"]})
        keys = {key["name"]: key for key in get(admin_on_a, host(hub_a), "/keys").json()["keys"]}
        assert (keys["Read"]["mode"], keys["Read"]["rate_per_minute"], keys["Read"]["scopes"]) == ("read", 30, {})
        assert keys["Carts"]["scopes"] == {"cart_checkout": ["read", "write"]}
        assert keys["Carts"]["revoked_at"] is None

    def test_the_apps_that_publish_their_api_with_what_each_offers(self, admin_on_a, hub_a):
        apps = {app["id"]: app for app in get(admin_on_a, host(hub_a), "/keys").json()["apps"]}
        assert apps["cart_checkout"]["read"] is True and apps["cart_checkout"]["write"] is True
        assert apps["tax"]["read"] is True
        assert "base" not in apps and all(app["name"] for app in apps.values())


KEY_ROUTES = {
    ("GET", "/keys", "base.api_key.list"),
    ("POST", "/keys", "base.api_key.create"),
    ("POST", "/keys/rotate", "base.api_key.rotate"),
    ("POST", "/keys/revoke", "base.api_key.revoke"),
}


def test_the_spas_route_map_names_every_route_of_the_keys(settings):
    from base.tests.test_access_routes import bound_routes

    assert KEY_ROUTES <= bound_routes()
    spa = json.loads((settings.BASE_DIR / "frontend" / "generated" / "operations.json").read_text())
    mine = {op for _, _, op in KEY_ROUTES}
    named = {(route["method"].upper(), route["path"].removeprefix("/api"), op) for op, route in spa.items() if op in mine}
    assert named == KEY_ROUTES
