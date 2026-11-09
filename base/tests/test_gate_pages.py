"""The Hub's gate pages (a hub being prepared, gone or suspended, and the sign-in to retry) wear ERPlora's look from
one stylesheet of ``base``, served as a static file with the logo: they are rendered without the request, so with no
nonce, and the strict CSP lets in only what comes from 'self' (no ``<style>`` nor ``style=``)."""

import re
from pathlib import Path

import pytest
from django.apps import apps
from django.contrib.staticfiles import finders
from django.core.management import call_command
from django.template.loader import get_template, render_to_string
from django.template.loader_tags import ExtendsNode

from base.models import Hub

STYLESHEET = "base/gate.css"
LOGO = "base/img/logo.png"
SAAS = "http://localhost:8001"
HTML = "text/html,application/xhtml+xml"

#: Each page with the context its view renders it with (base.middleware, base.auth_views).
PAGES = {
    "preparing": ("base/hub_preparing.html", {}),
    "maintenance": ("base/hub_maintenance.html", {}),
    "gone": ("base/hub_gone.html", {"is_demo": False, "back_url": f"{SAAS}/launch"}),
    "gone-demo": ("base/hub_gone.html", {"is_demo": True, "back_url": f"{SAAS}/demo/ended"}),
    "suspended": ("base/hub_suspended.html", {"back_url": f"{SAAS}/launch"}),
    "login-retry": ("base/login_retry.html", {"retry_url": "/auth/login?next=%2F"}),
    "too-many-attempts": ("base/too_many_attempts.html", {"minutes": 15}),
    "jump": ("base/jump.html", {"target": "/auth/login?next=", "csp_nonce": "n0nce"}),
    "database-cut": ("base/database_cut.html", {"message": "ERPlora will be back in a moment."}),
}
#: The one layout every gate page wears: its head, its stylesheet and ERPlora's mark are written once.
LAYOUT = "base/gate.html"


def csp_directives(response) -> dict[str, list[str]]:
    parts = (part.strip().split() for part in response["Content-Security-Policy"].split(";"))
    return {name: values for name, *values in parts if name}


@pytest.mark.parametrize("page", PAGES)
def test_every_gate_page_links_the_gate_stylesheet_and_shows_the_logo_with_no_inline_style(page, settings):
    template, context = PAGES[page]
    html = render_to_string(template, context)
    assert html.count(f'<link rel="stylesheet" href="{settings.STATIC_URL}{STYLESHEET}">') == 1
    assert f'src="{settings.STATIC_URL}{LOGO}"' in html
    assert not re.search(r"<style\b|\sstyle\s*=", html, re.IGNORECASE)


@pytest.mark.parametrize("page", PAGES)
def test_every_gate_page_wears_the_one_gate_layout(page):
    """A gate page says only what is its own: a new one that copies the head and the mark again is the duplicate this
    stops (dup-guard, hub#831)."""
    template = get_template(PAGES[page][0]).template
    first = template.nodelist[0]
    assert isinstance(first, ExtendsNode), f"{template.origin.template_name} does not extend {LAYOUT}"
    assert first.parent_name.var == LAYOUT


def test_every_gate_page_is_listed_here():
    """Each template that wears the gate's look is checked above: none is left out."""
    folder = Path(apps.get_app_config("base").path) / "templates" / "base"
    wearing = {path.name for path in folder.glob("*.html") if "ep-gate__" in path.read_text() or "{% extends" in path.read_text()}
    listed = {Path(template).name for template, _context in PAGES.values()}
    assert wearing - {Path(LAYOUT).name, "_gate_brand.html"} == listed


@pytest.mark.parametrize("path", [STYLESHEET, LOGO])
def test_the_static_files_finders_find_the_stylesheet_and_the_logo(path):
    assert finders.find(path)


def test_collectstatic_copies_them_where_whitenoise_serves_production_from(settings, tmp_path):
    # The image's build runs collectstatic (Dockerfile); WhiteNoise serves STATIC_ROOT without DEBUG.
    settings.STATIC_ROOT = tmp_path
    call_command("collectstatic", interactive=False, verbosity=0)
    assert (tmp_path / STYLESHEET).is_file()
    assert (tmp_path / LOGO).is_file()


@pytest.mark.django_db
class TestOnTheHostOfAHubThatDoesNotOpen:
    @pytest.mark.parametrize(
        ("fields", "status"),
        [({"status": "requested"}, 503), ({"status": "cancelled"}, 410), ({"state": {"status": "suspended"}}, 402)],
        ids=["preparing", "gone", "suspended"],
    )
    def test_its_page_links_the_stylesheet_that_its_csp_lets_in(self, client, settings, fields, status):
        Hub.objects.create(slug="acme", **{"status": "ready", **fields})
        response = client.get("/", HTTP_HOST="acme.localhost:8000", HTTP_ACCEPT=HTML)
        assert response.status_code == status
        assert f'href="{settings.STATIC_URL}{STYLESHEET}"' in response.content.decode()
        directives = csp_directives(response)
        assert "'self'" in directives["style-src"]
        assert "'self'" in directives["img-src"]

    @pytest.mark.parametrize(("path", "content_type"), [(STYLESHEET, "text/css"), (LOGO, "image/png")])
    def test_the_stylesheet_and_the_logo_are_still_served(self, client, settings, path, content_type):
        # Static files answer before the host's gate (WhiteNoise; from the finders here, STATIC_ROOT once collected).
        settings.WHITENOISE_USE_FINDERS = True
        Hub.objects.create(slug="acme", status="ready", state={"status": "suspended"})
        response = client.get(f"{settings.STATIC_URL}{path}", HTTP_HOST="acme.localhost:8000", HTTP_ACCEPT=HTML)
        assert response.status_code == 200
        assert response["Content-Type"].startswith(content_type)
