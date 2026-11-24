"""ERPlora's own hub on its address (``erp.erplora.com``): it opens as any business, for whoever is given access to it.

Its name is the one reserved name the host gate serves; any other, and the one its row had before, is no hub's. In the
Hub admin, its link opens it too.
"""

from urllib.parse import parse_qs, urlsplit

import pytest

from base.admin import ADMIN_HUB_SESSION_KEY
from base.models import Hub, Membership
from base.tenancy.context import use_hub
from base.tenancy.tests.business import A, HUB_DB
from base.tests.test_middleware import browse, jump_target, through_the_jump
from live.context import Scope, system_context
from live.operations import get as get_operation

pytestmark = [HUB_DB, pytest.mark.usefixtures("spa_manifest", "erplora_com")]

ERP = "erp.erplora.com"
A_HOST = f"{A.key}.erplora.com"
PLATFORM = "hubs.erplora.com"
CUSTOMERS = "/api/customer/customers"


@pytest.fixture
def erplora_com(settings):
    settings.ALLOWED_HOSTS = [".erplora.com"]
    settings.HUB_BASE_DOMAIN = "erplora.com"
    settings.SAAS_URL = "http://localhost:8001"
    settings.LIVE = {**settings.LIVE, "hub_slug_min_length": 3}


def named(hub: Hub, slug: str, *, is_platform: bool) -> Hub:
    Hub.objects.filter(pk=hub.pk).update(slug=slug, is_platform=is_platform)
    return Hub.objects.get(pk=hub.pk)


@pytest.fixture
def erp(hub_b):
    """ERPlora's own hub on its own database (``hub_b``'s), as ``create_platform_hub`` leaves it."""
    return named(hub_b, "erp", is_platform=True)


def customer_in(hub: Hub, name: str) -> None:
    create = get_operation("customer.customer.create")
    with use_hub(hub):
        create(system_context(Scope("host", hub.slug)), create.input(name=name))


def closed(client, host: str) -> None:
    """``host`` is no hub's: nothing of it answers, a page, a jump or the API, with a key or without one."""
    for path in ("/", "/system", "/auth/login", "/auth/callback"):
        assert browse(client, path, host).status_code == 404, path
    for path in ("/api/me", "/api/system/plan", "/api/live", CUSTOMERS):
        for headers in ({}, {"HTTP_AUTHORIZATION": "Bearer erpk_live_any"}):
            api = client.get(path, HTTP_HOST=host, **headers)
            assert (api.status_code, api.json()["error"]["code"]) == (404, "not_found"), path


# ── Its address ───────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.usefixtures("erp")
def test_its_address_opens_its_entrance(client):
    page = browse(client, "/system", ERP)

    assert jump_target(page) == "/auth/login?next=%2Fsystem"
    sign_in = through_the_jump(client, page, ERP)
    assert sign_in.status_code == 302
    asked = urlsplit(sign_in["Location"])
    assert (f"{asked.scheme}://{asked.netloc}{asked.path}", parse_qs(asked.query)["hub"]) == (
        "http://localhost:8001/hub-login/",
        ["erp"],
    )


@pytest.mark.usefixtures("erp")
def test_its_api_asks_a_visitor_to_sign_in(client):
    assert client.get(CUSTOMERS, HTTP_HOST=ERP).status_code == 401


@pytest.mark.usefixtures("erp")
def test_nobody_holds_anything_there_without_being_given_access(client, hub_a, make_user, superuser):
    for user in (make_user("ana", host=A.key, role="hub_owner"), superuser):
        client.force_login(user)
        refused = client.get(CUSTOMERS, HTTP_HOST=ERP)
        assert refused.status_code == 403, user


def test_without_its_row_its_address_is_not_found(client):
    closed(client, ERP)


@pytest.mark.parametrize("slug", ["erplora", "test", "hub", "www"])
def test_any_other_reserved_name_is_not_found_even_with_a_row(client, superuser, hub_b, slug):
    named(hub_b, slug, is_platform=slug == "erplora")
    host = f"{slug}.erplora.com"

    closed(client, host)
    client.force_login(superuser)
    closed(client, host)


def test_until_its_row_is_renamed_neither_of_its_names_opens(client, hub_b):
    named(hub_b, "erplora", is_platform=True)

    closed(client, ERP)
    closed(client, "erplora.erplora.com")


def test_a_row_under_its_name_that_is_not_its_own_is_never_served(client, hub_b):
    named(hub_b, "erp", is_platform=False)

    closed(client, ERP)


# ── The other businesses ──────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.usefixtures("erp")
def test_a_business_opens_on_its_own_address_as_before(client, hub_a, make_user):
    sign_in = through_the_jump(client, browse(client, "/", A_HOST), A_HOST)
    assert parse_qs(urlsplit(sign_in["Location"]).query)["hub"] == [A.key]
    assert client.get(CUSTOMERS, HTTP_HOST=A_HOST).status_code == 401

    client.force_login(make_user("ana", host=A.key, role="hub_owner"))
    assert client.get(CUSTOMERS, HTTP_HOST=A_HOST).status_code == 200


def test_the_platform_s_hub_and_a_business_never_cross(client, erp, hub_a, make_user):
    customer_in(erp, "Customer of ERPlora")
    customer_in(hub_a, "Customer of A")
    ana = make_user("ana", host=A.key, role="hub_owner")
    Membership.objects.create(user=ana, host="erp", role=Membership.Role.OWNER)
    client.force_login(ana)

    def names(host):
        return [row["name"] for row in client.get(CUSTOMERS, HTTP_HOST=host).json()["rows"]]

    assert names(ERP) == ["Customer of ERPlora"]
    assert names(A_HOST) == ["Customer of A"]
    created = client.post(CUSTOMERS, {"name": "New there"}, content_type="application/json", HTTP_HOST=ERP)
    assert created.status_code == 201
    assert "New there" in names(ERP)
    assert names(A_HOST) == ["Customer of A"]


# ── The Hub admin ─────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.usefixtures("erp")
def test_its_link_opens_it_in_the_hub_admin(client, superuser):
    client.force_login(superuser)

    opened = client.get("/admin/hub/erp/", HTTP_HOST=PLATFORM)

    assert (opened.status_code, opened["Location"]) == (302, "/admin/")
    assert client.session[ADMIN_HUB_SESSION_KEY] == "erp"
    assert "Hub: erp" in client.get("/admin/", HTTP_HOST=PLATFORM).content.decode()


@pytest.mark.parametrize("slug", ["erplora", "test", "hubs"])
def test_the_link_of_any_other_reserved_name_is_not_found(client, superuser, slug):
    client.force_login(superuser)

    assert client.get(f"/admin/hub/{slug}/", HTTP_HOST=PLATFORM).status_code == 404
    assert ADMIN_HUB_SESSION_KEY not in client.session


@pytest.mark.parametrize(
    ("slug", "audience"), [("erp", ["hub-admin"]), ("erplora", None), ("test", None)]
)
def test_the_staff_s_jump_to_the_hub_admin_is_for_its_name_alone(client, slug, audience):
    jump = client.get("/auth/login", {"hub": slug}, HTTP_HOST=PLATFORM)

    asked = parse_qs(urlsplit(jump["Location"]).query)
    assert jump.status_code == 302
    assert asked.get("audience") == audience
    assert asked.get("hub") == ([slug] if audience else None)
