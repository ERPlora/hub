"""The website's provider of ``base.public_home``: ``/`` of a hub with a published site, for a visitor without a
session, end to end through the Hub's middleware.

The page is rendered once per publication, language and deploy and kept (``website:home:…``); it carries no cookie,
no nonce and a CSP of its own; the browser may keep it a minute. Without a live publication ``/`` jumps to the SaaS's
login as before, and a session always gets the shell.
"""

import re
from datetime import UTC, datetime
from urllib.parse import urlsplit

import pytest
from django.core.cache import cache
from django.test import RequestFactory
from live.operations import get

from apps.website import public_home
from apps.website.models import Site
from apps.website.queries import page_cache_key
from apps.website.render import local_day
from apps.website.tests.conftest import B, WEBSITE_JS, ctx_for, full_content
from base.models import Hub

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("website_manifest")]

HTML = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
SAAS = "http://localhost:8001"


@pytest.fixture(autouse=True)
def saas(settings):
    settings.SAAS_URL = SAAS


def run(name: str, data: dict | None = None, ctx=None):
    op = get(name)
    return op(ctx or ctx_for(), op.input(**(data or {})))


def publish(template="classic", ctx=None, **overrides):
    content = full_content(**overrides)
    run("website.site.save", {"template": template, "theme": {"palette": "forest"}, "content": content}, ctx)
    return run("website.site.publish", ctx=ctx)


def visit(client, method="get", language="en", host="a.localhost:8000", **headers):
    return getattr(client, method)("/", HTTP_HOST=host, HTTP_ACCEPT=HTML, HTTP_ACCEPT_LANGUAGE=language, **headers)


def jumps_to_the_login(response) -> bool:
    location = urlsplit(response["Location"]) if response.status_code == 302 else None
    return location is not None and f"{location.scheme}://{location.netloc}{location.path}" == f"{SAAS}/hub-login/"


def test_an_anonymous_visitor_gets_the_published_site_on_the_root_with_a_nonce_free_csp_and_no_cookie(client):
    publish(about={"hidden": True})
    response = visit(client)
    assert response.status_code == 200
    assert response["Content-Type"] == "text/html; charset=utf-8"
    page = response.content.decode()
    assert "Fresh food every day" in page and 'href="/auth/login"' in page and "Log in" in page
    assert "We cook" not in page
    assert f'src="{WEBSITE_JS}"' in page
    csp = response["Content-Security-Policy"]
    assert "script-src 'self';" in csp and "frame-ancestors 'none'" in csp
    assert "nonce" not in csp and "strict-dynamic" not in csp and "trusted-types" not in csp
    assert "nonce" not in page
    assert not response.cookies and "Set-Cookie" not in response.headers
    assert response["Cache-Control"] == "public, max-age=60"
    assert "Accept-Language" in response["Vary"]


def test_the_page_varies_on_the_cookie_so_a_browser_never_shows_it_to_whoever_just_signed_in(client):
    # «Sign in» comes back to ``/`` with a session: the minute the browser may keep the visitor's page must not
    # answer that request (the shell must).
    publish()
    response = visit(client)
    assert {value.strip() for value in response["Vary"].split(",")} >= {"Accept-Language", "Cookie"}
    assert response["Cache-Control"] == "public, max-age=60"
    # The page says so itself, whether or not a middleware read the session on the way.
    request = RequestFactory().get("/", HTTP_HOST="a.localhost:8000", HTTP_ACCEPT_LANGUAGE="en")
    request.hub = Hub.objects.get(slug="a")
    own = public_home.respond(request)
    assert {value.strip() for value in own["Vary"].split(",")} == {"Accept-Language", "Cookie"}


def test_head_answers_the_same_page(client):
    publish()
    assert visit(client, method="head").status_code == 200


def test_the_page_speaks_the_visitors_language_and_each_language_is_kept_apart(client):
    publish()
    assert "Entrar" in visit(client, language="es-ES,es;q=0.9").content.decode()
    assert "Log in" in visit(client, language="en-GB").content.decode()
    # A language the Hub does not speak gets the source.
    assert "Log in" in visit(client, language="de").content.decode()
    assert cache.get(page_cache_key("a", 1, "es", local_day(""))) is not None
    assert cache.get(page_cache_key("a", 1, "en", local_day(""))) is not None


def test_the_page_is_rendered_once_per_publication_and_a_new_one_shows_at_once(client, django_capture_on_commit_callbacks):
    publish()
    assert "Fresh food every day" in visit(client).content.decode()
    # Nobody but a publication changes what is kept: a row edited by hand waits for the next one.
    Site.objects.update(published_content={**Site.objects.get().published_content, "template": "bold"})
    assert "ws-classic" in visit(client).content.decode()
    with django_capture_on_commit_callbacks(execute=True):
        publish(template="minimal", hero={"title": "New season"})
    page = visit(client).content.decode()
    assert "ws-minimal" in page and "New season" in page


def test_a_new_publication_shows_even_where_the_old_page_was_not_dropped(client):
    # Another process's cache (the process's memory locally) never hears this one's COMMIT: the version in the key
    # alone keeps it from serving the old page. Here no on_commit runs, so nothing drops the first page.
    publish()
    assert "ws-classic" in visit(client).content.decode()
    publish(template="bold", hero={"title": "New season"})
    page = visit(client).content.decode()
    assert "ws-bold" in page and "New season" in page


def test_a_new_deploy_renders_the_page_again_for_its_bundle(client, settings):
    publish()
    settings.APP_VERSION = "abc"
    visit(client)
    assert cache.get(page_cache_key("a", 1, "en", local_day(""))) is not None
    settings.APP_VERSION = "def"
    assert cache.get(page_cache_key("a", 1, "en", local_day(""))) is None


def today_row(page: str) -> str:
    return re.search(r'<li\b[^>]*aria-current="date"[^>]*>(.*?)</li>', page, re.S).group(1)


def test_the_page_marks_today_in_the_hubs_time_zone_and_keeps_each_day_apart(client, monkeypatch):
    Hub.objects.filter(slug="a").update(timezone="America/New_York")
    publish()
    # 2026-10-19 02:30 UTC is still Sunday in New York: the kept page is Sunday's; at 14:00 UTC it is Monday's.
    monkeypatch.setattr("django.utils.timezone.now", lambda: datetime(2026, 10, 19, 2, 30, tzinfo=UTC))
    assert "Sunday" in today_row(visit(client).content.decode())
    monkeypatch.setattr("django.utils.timezone.now", lambda: datetime(2026, 10, 19, 14, 0, tzinfo=UTC))
    assert "Monday" in today_row(visit(client).content.decode())
    assert cache.get(page_cache_key("a", 1, "en", "sun")) is not None
    assert cache.get(page_cache_key("a", 1, "en", "mon")) is not None


def test_without_a_publication_the_root_jumps_to_the_login(client):
    run("website.site.save", {"template": "classic", "theme": {}, "content": full_content()})
    assert jumps_to_the_login(visit(client))


def test_a_site_taken_offline_jumps_to_the_login_again(client):
    publish()
    run("website.site.unpublish")
    assert jumps_to_the_login(visit(client))


def test_a_signed_in_person_gets_the_shell(client, make_user):
    publish()
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    response = visit(client)
    assert response.status_code == 200
    assert "Fresh food every day" not in response.content.decode()


def test_other_paths_still_jump_to_the_login(client):
    publish()
    response = client.get("/website", HTTP_HOST="a.localhost:8000", HTTP_ACCEPT=HTML)
    assert jumps_to_the_login(response)


def test_a_site_published_by_one_hub_is_not_the_home_page_of_another(client):
    publish()
    assert jumps_to_the_login(visit(client, host="b.localhost:8000"))
    assert public_home.is_published(Hub.objects.get(slug="b")) is False


def test_each_hub_shows_its_own_site_on_its_root(client):
    publish()
    publish(template="bold", ctx=ctx_for(scope=B), hero={"title": "Bea's barber shop"})
    a_page, b_page = visit(client).content.decode(), visit(client, host="b.localhost:8000").content.decode()
    assert "Fresh food every day" in a_page and "ws-classic" in a_page and "Bea" not in a_page
    assert "Bea&#x27;s barber shop" in b_page and "ws-bold" in b_page and "Fresh food every day" not in b_page


def test_with_the_module_off_in_the_hub_neither_the_root_nor_the_public_api_show_its_site(client, monkeypatch):
    # The same guard on every public path: the module on in this hub (phase 1: every installed app,
    # ``base.relay.active_apps``; phase 2: its activation) and a live publication of its own.
    publish()
    from base import relay

    on = relay.active_apps
    monkeypatch.setattr(relay, "active_apps", lambda scope: on(scope) - {"website"})
    assert jumps_to_the_login(visit(client))
    assert public_home.is_published(Hub.objects.get(slug="a")) is False
    for path in ("/api/website/public/site", "/api/website/public/catalog"):
        response = client.get(path, HTTP_HOST="a.localhost:8000")
        assert (response.status_code, response.json()["error"]["code"]) == (404, "app_inactive"), path


def test_is_published_says_whether_a_publication_is_live():
    hub = Hub.objects.get(slug="a")
    assert public_home.is_published(hub) is False
    publish()
    assert public_home.is_published(hub) is True
    run("website.site.unpublish")
    assert public_home.is_published(hub) is False

