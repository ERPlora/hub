"""``base.public_home``: a hub's public website answers ``/`` to a visitor without a session.

The website is a module (``apps.website``); ``base`` only knows its contract: when the module is installed and
its provider (``apps.website.public_home``) says the hub published a site, an anonymous GET or HEAD of ``/`` gets the
provider's page instead of the jump to the SaaS's login, with no cookie at all. Anything else is as before: other
paths jump to the login, a session gets the shell, and without the module (or without a published site) ``/``
jumps to the login too.
"""

import sys
import types
from urllib.parse import urlsplit

import pytest
from django.apps import apps
from django.http import HttpResponse
from django.test import RequestFactory

from base import public_home

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("spa_manifest")]

HTML = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
SAAS = "http://localhost:8001"
PAGE = "<!doctype html><title>Acme</title><a href=/auth/login>Sign in</a>"


@pytest.fixture(autouse=True)
def saas(settings):
    settings.SAAS_URL = SAAS


class FakeProvider:
    """Stands in for ``apps.website.public_home``: ``is_published(hub)`` and ``respond(request)``."""

    def __init__(self) -> None:
        self.published = True
        self.asked: list[str] = []
        self.served: list[str] = []

    def is_published(self, hub) -> bool:
        self.asked.append(hub.slug)
        return self.published

    def respond(self, request) -> HttpResponse:
        self.served.append(request.hub.slug)
        return HttpResponse(PAGE, content_type="text/html; charset=utf-8")


def installed(monkeypatch, present: bool) -> None:
    """``apps.website`` installed or not, whatever INSTALLED_APPS says; every other app as it is."""
    real = apps.is_installed
    monkeypatch.setattr(apps, "is_installed", lambda name: present if name == "apps.website" else real(name))


@pytest.fixture
def website(monkeypatch) -> FakeProvider:
    provider = FakeProvider()
    installed(monkeypatch, True)
    monkeypatch.setattr(public_home, "_provider", lambda: provider)
    return provider


def browse(client, path="/", host="a.localhost:8000", method="get", accept=HTML):
    return getattr(client, method)(path, HTTP_HOST=host, HTTP_ACCEPT=accept)


def jumps_to(response, path: str) -> bool:
    location = urlsplit(response["Location"]) if response.status_code == 302 else None
    return location is not None and f"{location.scheme}://{location.netloc}{location.path}" == f"{SAAS}{path}"


def test_without_the_module_the_home_page_jumps_to_the_saas_login(client, monkeypatch):
    installed(monkeypatch, False)

    def no_provider():
        raise AssertionError("Without apps.website installed, its provider is never imported.")

    monkeypatch.setattr(public_home, "_provider", no_provider)
    assert jumps_to(browse(client), "/hub-login/")


@pytest.mark.parametrize("method", ["get", "head"])
def test_a_published_site_is_the_home_page_of_a_visitor_without_a_session(client, website, method):
    response = browse(client, method=method)
    assert response.status_code == 200
    assert website.served == ["a"]
    if method == "get":
        assert response.content.decode() == PAGE


def test_the_public_home_page_sets_no_cookie(client, website):
    # No CSRF cookie, no session, no login state: the page may be cached and shared (round 2026-10-21).
    response = browse(client)
    assert response.status_code == 200
    assert not response.cookies
    assert "Set-Cookie" not in response.headers


def test_a_call_that_does_not_ask_for_a_page_gets_the_published_site_too(client, website):
    # A crawler or curl (Accept */*) is a visitor of the website, not someone on the way to the shell.
    response = browse(client, accept="*/*")
    assert (response.status_code, response.content.decode()) == (200, PAGE)


def test_an_unpublished_site_leaves_the_home_page_jumping_to_the_login(client, website):
    website.published = False
    assert jumps_to(browse(client), "/hub-login/")
    assert (website.asked, website.served) == (["a"], [])


def test_a_signed_in_person_gets_the_shell_even_with_a_published_site(client, website, make_user):
    client.force_login(make_user("ana", host="a", role="hub_employee"))
    response = browse(client)
    assert response.status_code == 200
    assert '<div id="app"></div>' in response.content.decode()
    assert website.served == []


@pytest.mark.parametrize("path", ["/demo/items", "/website"])
def test_other_paths_still_jump_to_the_login(client, website, path):
    assert jumps_to(browse(client, path), "/hub-login/")
    assert website.served == []


def test_a_path_that_names_a_file_is_not_the_website_either(client, website):
    # /index.html names a file, no route of the SPA (base.spa.NOT_A_FILE): a plain 404 with no cookie, not the site.
    response = browse(client, "/index.html")
    assert (response.status_code, dict(response.cookies)) == (404, {})
    assert website.served == []


def test_only_the_home_page_is_the_website_for_a_call_that_does_not_ask_for_a_page(client, website):
    response = browse(client, "/demo/items", accept="*/*")
    assert response.status_code == 200
    assert '<div id="app"></div>' in response.content.decode()
    assert website.served == []


def test_a_post_to_the_home_page_is_still_not_allowed(client, website):
    assert browse(client, method="post").status_code == 405
    assert website.served == []


def test_a_demo_with_a_published_site_shows_it_and_one_without_jumps_to_its_door(client, website):
    import datetime as dt

    from django.utils import timezone

    from base.models import Hub

    expires = timezone.now() + dt.timedelta(minutes=5)
    Hub.objects.create(slug="demo-0000beef", status="ready", is_demo=True, expires_at=expires)
    response = browse(client, host="demo-0000beef.localhost:8000")
    assert (response.status_code, website.served) == (200, ["demo-0000beef"])
    website.published = False
    assert jumps_to(browse(client, host="demo-0000beef.localhost:8000"), "/demo/enter/")


def test_each_hub_asks_about_its_own_site(client, website):
    assert browse(client, host="b.localhost:8000").status_code == 200
    assert website.asked == ["b"]


def test_the_answer_is_asked_once_per_request(client, website):
    # The login gate and the view both need it: the provider is asked once, and again on the next request.
    browse(client)
    browse(client)
    assert website.asked == ["a", "a"]


def test_a_request_without_a_hub_has_no_website(website):
    request = RequestFactory().get("/", HTTP_HOST="a.localhost:8000")
    assert public_home.website_enabled(request) is False
    assert website.asked == []


def test_the_provider_is_the_website_module(monkeypatch):
    provider = types.ModuleType("apps.website.public_home")
    monkeypatch.setitem(sys.modules, "apps.website.public_home", provider)
    assert public_home._provider() is provider
