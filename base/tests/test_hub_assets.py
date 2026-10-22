"""``{% hub_assets "<entry>" %}``: the ``<link>`` and ``<script>`` tags of an entry of the Hub's Vite build.

The SPA's HTML links its own entry (``live.spa.render_spa``); a page of the Hub that is not the SPA (a hub's public
website, ``frontend/website.ts``) asks for another entry of the same build through ``live.spa.spa_assets``: the
manifest's files under ``/static/spa/``, or the dev server with DEBUG. A page whose CSP runs on a nonce carries it on
every script and modulepreload; the public website has none (``script-src 'self'``, an HTML that can be cached), so
its tags carry none either.
"""

import json

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.template import Context, RequestContext, Template
from django.test import RequestFactory

WEBSITE = "frontend/website.ts"


@pytest.fixture
def website_manifest(settings, tmp_path):
    """A Vite build manifest with the SPA's entry and the public website's, as `vite build` writes it."""
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "frontend/main.ts": {"file": "assets/main-abc123.js", "src": "frontend/main.ts", "isEntry": True},
                WEBSITE: {
                    "file": "assets/website-9f8e7d.js",
                    "src": WEBSITE,
                    "isEntry": True,
                    "css": ["assets/website-6c5b4a.css"],
                    "imports": ["_shared-321.js"],
                },
                "_shared-321.js": {"file": "assets/shared-321.js"},
            }
        )
    )
    settings.DEBUG = False
    settings.LIVE = {**settings.LIVE, "spa": {**settings.LIVE["spa"], "manifest": manifest, "dev_server": None}}
    return manifest


def render(context, entry: str = WEBSITE) -> str:
    return Template('{% load hub_assets %}{% hub_assets "' + entry + '" %}').render(context)


@pytest.mark.usefixtures("website_manifest")
def test_without_a_nonce_the_entry_links_its_build_files_with_no_nonce():
    # The public website's HTML is rendered without a request: no context processor, no nonce.
    assert render(Context({})).splitlines() == [
        '<link rel="stylesheet" href="/static/spa/assets/website-6c5b4a.css">',
        '<link rel="modulepreload" href="/static/spa/assets/shared-321.js">',
        '<script type="module" src="/static/spa/assets/website-9f8e7d.js"></script>',
    ]


@pytest.mark.usefixtures("website_manifest")
def test_with_the_response_s_nonce_every_script_and_preload_carries_it():
    request = RequestFactory().get("/")
    request._csp_nonce = "n0nce"
    # The csp context processor (TEMPLATES) puts the response's nonce in a RequestContext as ``csp_nonce``.
    assert render(RequestContext(request, {})).splitlines() == [
        '<link rel="stylesheet" href="/static/spa/assets/website-6c5b4a.css">',
        '<link rel="modulepreload" href="/static/spa/assets/shared-321.js" nonce="n0nce">',
        '<script type="module" src="/static/spa/assets/website-9f8e7d.js" nonce="n0nce"></script>',
    ]


@pytest.mark.usefixtures("website_manifest")
def test_another_entry_of_the_same_build():
    assert render(Context({}), "frontend/main.ts") == (
        '<script type="module" src="/static/spa/assets/main-abc123.js"></script>'
    )


@pytest.mark.usefixtures("website_manifest")
def test_an_entry_the_build_does_not_have_is_a_programming_error():
    with pytest.raises(ImproperlyConfigured, match="frontend/nope.ts"):
        render(Context({}), "frontend/nope.ts")


def test_with_debug_the_dev_server_serves_the_entry_and_its_css(settings):
    settings.DEBUG = True
    settings.LIVE = {**settings.LIVE, "spa": {**settings.LIVE["spa"], "dev_server": "http://localhost:5173"}}
    assert render(Context({})).splitlines() == [
        '<script type="module" src="http://localhost:5173/static/spa/@vite/client"></script>',
        '<script type="module" src="http://localhost:5173/static/spa/frontend/website.ts"></script>',
    ]
