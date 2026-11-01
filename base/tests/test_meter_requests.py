"""Where the meter hears a business during the day (BASE-F40; PLAN-HUB §66): every request that reaches a hub counts, and
every person with a session there has activity. Static files, health probes, ``/internal``, the platform's host and the
demos are not measured; a visitor of the public web and an API key are no people; and nothing of it adds a statement to
the request, sync or async.
"""

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.test.client import FakePayload
from django.test.utils import CaptureQueriesContext

from base import meter
from base.models import Membership
from base.operations import HubContextBuilder
from base.tenancy import connections as tenancy_connections
from base.tenancy import limits
from base.tenancy.tests import hubs
from base.tests.test_api_keys import CARTS, bearer, create, get, host
from base.tests.test_internal import signed
from control.models import Hub

HUB_DB = pytest.mark.django_db(databases=hubs.HUB_DATABASES)
HUB_DB_COMMITTED = pytest.mark.django_db(databases=hubs.HUB_DATABASES, transaction=True)
ITEMS = "/api/demo/items"


pytestmark = pytest.mark.usefixtures("no_test_fallback")


@pytest.fixture(autouse=True)
def counting(monkeypatch):
    """This process counts, from nothing, with no limiter or identity left by another test."""
    monkeypatch.setattr(meter, "_recording", True)
    monkeypatch.setattr(meter, "_activity", {})
    monkeypatch.setattr(meter, "_seen", {})
    monkeypatch.setattr(limits, "_limiters", {})


def member(slug: str, saas_id: str = "olga", role: str = "hub_admin"):
    user, _ = get_user_model().objects.get_or_create(username=f"saas:{saas_id}")
    Membership.objects.get_or_create(user=user, host=slug, defaults={"role": role})
    return user


def on(hub) -> meter.Unflushed:
    return meter.unflushed(hub.pk, hub.slug)


# ── Requests ──────────────────────────────────────────────────────────────────────────────────────────────────────────


@HUB_DB
def test_a_request_counts_for_its_hub_and_no_other(client, hub_a, hub_b):
    client.force_login(member(hub_a.slug))

    assert client.get(ITEMS, HTTP_HOST=host(hub_a)).status_code == 200
    assert client.get(ITEMS, HTTP_HOST=host(hub_a)).status_code == 200

    assert on(hub_a).requests == 2
    assert on(hub_b).requests == 0


@HUB_DB
def test_a_visitor_of_the_public_web_counts_as_a_request_and_as_nobody(client, hub_a):
    client.get("/robots.txt", HTTP_HOST=host(hub_a))

    assert on(hub_a).requests == 1
    assert on(hub_a).people == frozenset()


@HUB_DB
@pytest.mark.parametrize("path", ["/healthz", "/readyz", "/static/nothing.js", "/csp-report/"])
def test_what_is_no_business_s_request_does_not_count(client, hub_a, path):
    client.get(path, HTTP_HOST=host(hub_a))

    assert on(hub_a).requests == 0


@HUB_DB
def test_the_saas_s_door_does_not_count(client, hub_a):
    response = signed(client, "get", "/internal/usage?day=2026-03-10", b"", with_v2=True, host=host(hub_a))

    assert response.status_code != 404
    assert on(hub_a).requests == 0


@HUB_DB
def test_the_platform_s_host_does_not_count_even_with_a_business_chosen(client, hub_a):
    client.force_login(get_user_model().objects.create_superuser("root", "root@example.com", "pw"))
    client.get(f"/admin/hub/{hub_a.slug}/", HTTP_HOST="hubs.localhost")
    client.get("/admin/demo/item/", HTTP_HOST="hubs.localhost")

    assert on(hub_a).requests == 0
    assert meter._seen == {}


@HUB_DB
def test_a_demo_is_not_measured(client, hub_a, monkeypatch):
    Hub.objects.filter(pk=hub_a.pk).update(is_demo=True)
    client.force_login(member(hub_a.slug))
    # What the fixture did on its alias, as the hub it was then: a real demo is one from its first transaction.
    monkeypatch.setattr(limits, "_limiters", {})
    meter._activity.clear()

    response = client.get(ITEMS, HTTP_HOST=host(hub_a))

    assert response.status_code == 200
    assert meter._activity == {}
    assert meter._seen == {}


@HUB_DB_COMMITTED
async def test_a_request_daphne_serves_counts_too(async_client, hub_a):
    from asgiref.sync import sync_to_async

    user = await sync_to_async(member)(hub_a.slug)
    await async_client.aforce_login(user)

    response = await async_client.request(
        method="GET",
        path=ITEMS,
        query_string="",
        headers=[(b"host", host(hub_a).encode())],
        _body_file=FakePayload(b""),
    )
    await sync_to_async(connections.close_all)()

    assert response.status_code == 200
    assert meter.unflushed(hub_a.pk, hub_a.slug).requests == 1
    assert meter.unflushed(hub_a.pk, hub_a.slug).people == frozenset({"olga"})
    assert meter.unflushed(hub_a.pk, hub_a.slug).peak >= 1


# ── Room ──────────────────────────────────────────────────────────────────────────────────────────────────────────────


@HUB_DB_COMMITTED
def test_a_request_with_no_room_is_counted_as_that(client, hub_a, hub_b, monkeypatch):
    """Answered 503 ``base.hub_busy``, as anyone sees it, whichever transaction hit it, and only for its own hub."""
    monkeypatch.setattr(limits, "SLOT_WAIT_SECONDS", 0.05)
    client.force_login(member(hub_a.slug))
    assert client.get(ITEMS, HTTP_HOST=host(hub_a)).status_code == 200
    assert on(hub_a).busy == 0

    limiter = limits.limiter_for(tenancy_connections.hub_alias(hub_a))
    taken = [limiter.take(wait=0) for _ in range(limiter.limits.max_transactions)]
    try:
        busy = client.get(ITEMS, HTTP_HOST=host(hub_a))
    finally:
        for slot in taken:
            slot.release()

    assert (busy.status_code, busy.json()["error"]["code"]) == (503, "base.hub_busy")
    assert on(hub_a).busy >= 1
    assert on(hub_b).busy == 0
    assert client.get(ITEMS, HTTP_HOST=host(hub_a)).status_code == 200


@HUB_DB_COMMITTED
def test_the_peak_comes_from_the_real_transactions(client, hub_a):
    client.force_login(member(hub_a.slug))

    assert client.get(ITEMS, HTTP_HOST=host(hub_a)).status_code == 200

    assert on(hub_a).peak == 1


# ── People ────────────────────────────────────────────────────────────────────────────────────────────────────────────


@HUB_DB
def test_a_person_with_a_session_has_activity_under_their_account(client, hub_a):
    client.force_login(member(hub_a.slug, saas_id="ana"))

    client.get(ITEMS, HTTP_HOST=host(hub_a))

    assert on(hub_a).people == frozenset({"ana"})


@HUB_DB
def test_someone_without_a_session_is_nobody(client, hub_a):
    assert client.get(ITEMS, HTTP_HOST=host(hub_a)).status_code in (401, 403)

    assert on(hub_a).people == frozenset()
    assert on(hub_a).requests == 1


@HUB_DB
def test_an_api_key_is_no_person(client, hub_a):
    client.force_login(member(hub_a.slug))
    token = create(client, hub_a, mode="read")["token"]
    client.logout()
    monkeypatched_seen = dict(meter._seen)
    meter._seen.clear()

    answered = get(client, host(hub_a), CARTS, **bearer(token))

    assert answered.status_code == 200
    assert monkeypatched_seen  # the admin who made it, seen
    assert meter._seen == {}


@HUB_DB
def test_a_session_opened_on_another_hub_is_nobody_here(client, hub_a, hub_b):
    from base.middleware import SESSION_HOST_KEY

    client.force_login(member(hub_a.slug))
    session = client.session
    session[SESSION_HOST_KEY] = hub_b.slug
    session.save()

    client.get(ITEMS, HTTP_HOST=host(hub_a))

    assert on(hub_a).people == frozenset()


@HUB_DB
def test_the_context_builder_of_a_request_with_no_hub_notes_nobody(hub_a, rf):
    request = rf.get(ITEMS, HTTP_HOST=host(hub_a))
    request.user = member(hub_a.slug)

    HubContextBuilder().from_request(request)

    assert meter._seen == {}


# ── Nothing added to the request ──────────────────────────────────────────────────────────────────────────────────────


@HUB_DB
def test_counting_adds_no_statement_to_a_request(client, hub_a, monkeypatch):
    client.force_login(member(hub_a.slug))
    alias = tenancy_connections.hub_alias(hub_a)
    client.get(ITEMS, HTTP_HOST=host(hub_a))  # the first one checks the database's identity

    def statements_of_a_request() -> int:
        with CaptureQueriesContext(connections["default"]) as control, CaptureQueriesContext(connections[alias]) as own:
            assert client.get(ITEMS, HTTP_HOST=host(hub_a)).status_code == 200
        return len(control) + len(own)

    counted = statements_of_a_request()
    monkeypatch.setattr(meter, "_recording", False)
    uncounted = statements_of_a_request()

    assert counted == uncounted


# ── The serving process starts it ─────────────────────────────────────────────────────────────────────────────────────


def test_the_process_daphne_runs_starts_the_meter_and_the_worker_does_not(monkeypatch):
    import runpy
    from pathlib import Path

    import config.asgi

    started = []
    monkeypatch.setattr(meter, "start", lambda: started.append(True))

    runpy.run_path(str(Path(config.asgi.__file__)))

    assert started == [True]
    assert "meter" not in Path("base/worker.py").read_text(encoding="utf-8")
