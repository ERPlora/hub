"""The public website on a business's own domain (HUBS-F17, PLAN-SAAS §37 point 2), end to end through the middleware.

The same page as on its own address, with what that domain changes: «Log in» goes to the business's own address, the
page asks nothing of ``/api`` (which is not there), so its catalog is read when it is painted and it is kept a minute
instead of an hour, and it never names a report's address that is not there. A session never turns it into the app. The
door itself (the unknown host, what is closed, the probe, the images) is in ``base/tests/test_custom_domains.py``.
"""

import pytest
from django.core.cache import cache

from apps.website import public_home, queries
from apps.website.models import Site
from apps.website.queries import CATALOG_TTL, PAGE_TTL, page_cache_key
from apps.website.render import local_day
from apps.website.tests.conftest import A, B, ctx_for, full_content
from apps.website.tests.test_public_home import publish, run
from base import custom_domains
from base.models import Hub
from base.tenancy.connections import hub_alias
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_custom_domains import DOMAIN, HTML, OTHER_DOMAIN, statements  # noqa: F401
from live.context import Scope

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("website_manifest")]

SLUG_HOST = "a.localhost:8000"
LOGIN_ON_ITS_ADDRESS = 'href="https://a.localhost/auth/login"'


def connect(slug: str, domain: str) -> None:
    """``slug``'s last photo named ``domain``."""
    Hub.objects.filter(slug=slug).update(custom_domain=domain)
    custom_domains.forget()


@pytest.fixture
def connected():
    connect("a", DOMAIN)


def visit(client, host=DOMAIN, method="get", language="en", **headers):
    return getattr(client, method)("/", HTTP_HOST=host, HTTP_ACCEPT=HTML, HTTP_ACCEPT_LANGUAGE=language, **headers)


# The page


def test_a_published_site_opens_on_its_domain_as_a_page_with_no_cookie(client, connected):
    publish()
    response = visit(client)
    assert response.status_code == 200
    assert response["Content-Type"] == "text/html; charset=utf-8"
    assert "Fresh food every day" in response.content.decode()
    assert not response.cookies and "Set-Cookie" not in response.headers
    assert response["Cache-Control"] == "public, max-age=60"
    assert {value.strip() for value in response["Vary"].split(",")} >= {"Accept-Language", "Cookie"}
    csp = response["Content-Security-Policy"]
    assert "script-src 'self';" in csp and "frame-ancestors 'none'" in csp and "nonce" not in csp


def test_head_answers_too(client, connected):
    publish()
    assert visit(client, method="head").status_code == 200


def test_it_speaks_the_visitors_language(client, connected):
    publish()
    assert "Entrar" in visit(client, language="es-ES,es;q=0.9").content.decode()
    assert "Log in" in visit(client, language="en-GB").content.decode()


def test_a_session_of_the_business_gets_the_website_never_the_shell(client, connected, make_user):
    publish()
    client.force_login(make_user("ana"))
    page = visit(client).content.decode()
    assert "Fresh food every day" in page
    assert 'id="spa-config"' not in page and "session-me" not in page


def test_on_its_own_address_a_session_still_gets_the_shell(client, connected, make_user):
    publish()
    client.force_login(make_user("ana"))
    assert "session-me" in visit(client, host=SLUG_HOST).content.decode()


@pytest.mark.parametrize("state", ["never_published", "offline", "app_off"])
def test_without_a_website_to_show_the_domain_serves_nothing(client, connected, state, monkeypatch):
    if state == "offline":
        publish()
        run("website.site.unpublish")
    elif state == "app_off":
        publish()
        monkeypatch.setattr(queries.relay, "active_apps", lambda scope: frozenset())
    response = visit(client)
    assert response.status_code == 404
    assert "auth/login" not in response.content.decode()


def test_a_site_that_went_offline_between_the_check_and_the_page_is_not_found(client, connected, monkeypatch):
    publish()
    monkeypatch.setattr(queries, "published_page", lambda scope: None)
    assert visit(client).status_code == 404
    # On its own address it still sends to the team's sign-in.
    assert visit(client, host=SLUG_HOST)["Location"] == public_home.OFFLINE_FALLBACK


# Two businesses


def test_each_domain_shows_the_site_of_its_own_business(client, connected):
    publish(hero={"title": "Ours, of A"})
    publish(ctx=ctx_for(scope=B), hero={"title": "Theirs, of B"})
    connect("b", OTHER_DOMAIN)
    of_a, of_b = visit(client).content.decode(), visit(client, host=OTHER_DOMAIN).content.decode()
    assert "Ours, of A" in of_a and "Theirs, of B" not in of_a
    assert "Theirs, of B" in of_b and "Ours, of A" not in of_b


def test_a_domain_that_moved_to_another_business_never_shows_the_one_it_left(client, connected):
    publish(hero={"title": "Ours, of A"})
    publish(ctx=ctx_for(scope=B), hero={"title": "Theirs, of B"})
    assert "Ours, of A" in visit(client).content.decode()
    # Both photos applied, on another process: this one's map still says it is A's.
    Hub.objects.filter(slug="a").update(custom_domain="")
    Hub.objects.filter(slug="b").update(custom_domain=DOMAIN)
    assert visit(client).status_code == 404
    custom_domains.forget()
    page = visit(client).content.decode()
    assert "Theirs, of B" in page and "Ours, of A" not in page


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_each_domain_reads_the_database_of_its_own_business(client, hub_a, hub_b, statements):  # noqa: F811
    # Two businesses of today, each with its own database, not the suite's shared fallback.
    a, b = Scope("host", hub_a.slug), Scope("host", hub_b.slug)
    with use_hub(hub_a):
        publish(ctx=ctx_for(scope=a), hero={"title": "In the database of A"})
    with use_hub(hub_b):
        publish(ctx=ctx_for(scope=b), hero={"title": "In the database of B"})
    connect(hub_a.slug, DOMAIN)
    connect(hub_b.slug, OTHER_DOMAIN)
    statements.clear()
    page = visit(client).content.decode()
    assert "In the database of A" in page and "In the database of B" not in page
    assert {alias for alias, _sql in statements} <= {"default", hub_alias(hub_a)}
    assert hub_alias(hub_a) in {alias for alias, _sql in statements}
    statements.clear()
    page = visit(client, host=OTHER_DOMAIN).content.decode()
    assert "In the database of B" in page and "In the database of A" not in page
    assert {alias for alias, _sql in statements} <= {"default", hub_alias(hub_b)}


# What it reads


def test_the_domain_adds_no_read_to_the_page(client, connected, statements):  # noqa: F811
    publish()
    visit(client)
    visit(client, host=SLUG_HOST)
    statements.clear()
    assert visit(client, host=SLUG_HOST).status_code == 200
    on_its_address = list(statements)
    assert on_its_address, "the control must see the page's own reads"
    statements.clear()
    assert visit(client).status_code == 200
    # The row by its id here, by its slug there: the same reads, on the same databases.
    assert [alias for alias, _sql in statements] == [alias for alias, _sql in on_its_address]


# «Log in»


@pytest.mark.parametrize("template", ["classic", "modern", "bold", "minimal"])
def test_log_in_leaves_the_domain_for_the_businesss_own_address(client, connected, template):
    publish(template=template)
    page = visit(client).content.decode()
    assert page.count(LOGIN_ON_ITS_ADDRESS) == 2
    assert 'href="/auth/login"' not in page


def test_on_its_own_address_log_in_is_where_it_was(client, connected):
    publish()
    page = visit(client, host=SLUG_HOST).content.decode()
    assert 'href="/auth/login"' in page and "https://a.localhost" not in page


# What it asks of the Hub


def test_the_page_says_it_asks_nothing_of_the_api_there(client, connected):
    publish()
    assert "data-ep-static" in visit(client).content.decode().split("<head>")[0]
    assert "data-ep-static" not in visit(client, host=SLUG_HOST).content.decode().split("<head>")[0]


def test_its_policy_names_no_report_address_that_is_not_there(client, connected):
    publish()
    assert "report-uri" not in visit(client)["Content-Security-Policy"]
    assert "report-uri /csp-report/" in visit(client, host=SLUG_HOST)["Content-Security-Policy"]


def test_each_address_keeps_its_own_page(client, connected):
    publish()
    today = local_day("")
    visit(client)
    assert cache.get(page_cache_key("a", 1, "en", today, "EUR", own_domain=True)) is not None
    assert cache.get(page_cache_key("a", 1, "en", today, "EUR")) is None
    visit(client, host=SLUG_HOST)
    assert LOGIN_ON_ITS_ADDRESS in cache.get(page_cache_key("a", 1, "en", today, "EUR", own_domain=True))
    assert LOGIN_ON_ITS_ADDRESS not in cache.get(page_cache_key("a", 1, "en", today, "EUR"))


def kept_for(monkeypatch) -> dict:
    """What each key is kept for, as the page writes it."""
    kept: dict[str, int] = {}
    original = cache.set

    def spied(key, value, timeout=None, **kwargs):
        kept[key] = timeout
        return original(key, value, timeout, **kwargs)

    monkeypatch.setattr(cache, "set", spied)
    return kept


def test_on_the_domain_the_page_is_kept_a_minute_and_on_its_address_an_hour(client, connected, monkeypatch):
    publish()
    today = local_day("")
    kept = kept_for(monkeypatch)
    visit(client)
    visit(client, host=SLUG_HOST)
    assert kept[page_cache_key("a", 1, "en", today, "EUR", own_domain=True)] == CATALOG_TTL
    assert kept[page_cache_key("a", 1, "en", today, "EUR")] == PAGE_TTL


def test_a_new_publication_shows_at_once(client, connected):
    publish(hero={"title": "First title"})
    assert "First title" in visit(client).content.decode()
    # Its commit is the test's: nothing forgets what is kept, the new version is another key.
    publish(hero={"title": "Second title"})
    page = visit(client).content.decode()
    assert "Second title" in page and "First title" not in page


def test_a_publication_forgets_the_page_of_the_domain_too(client, connected):
    publish()
    today = local_day("")
    visit(client)
    key = page_cache_key("a", 1, "en", today, "EUR", own_domain=True)
    assert cache.get(key) is not None
    queries.forget_cached("a", 1, "EUR")
    assert cache.get(key) is None


# The catalog: there is no refresh, so it is read when the page is painted


def test_the_catalog_is_the_live_one_and_not_the_snapshot_of_the_publication(client, connected):
    from apps.service.models import Service

    publish(catalog={"source": "service", "show_prices": True})
    assert Site.objects.get().published_content["catalog"]["groups"] == []
    # Offered after the publication: only a read of the source itself can know it.
    Service.objects.create(name="Live haircut", price=1250, duration_minutes=30)
    page = visit(client).content.decode()
    assert "Live haircut" in page and "€12.50" in page
    # On its address the page paints the snapshot, and its script refreshes it.
    assert "Live haircut" not in visit(client, host=SLUG_HOST).content.decode()


def test_a_hidden_catalog_is_not_even_read(db):
    from apps.service.models import Service

    Service.objects.create(name="Live haircut", price=1250, duration_minutes=30)
    assert queries.live_catalog(A, full_content(catalog={"source": "service", "hidden": False}))["groups"]
    assert queries.live_catalog(A, full_content(catalog={"source": "service", "hidden": True}))["groups"] == []
