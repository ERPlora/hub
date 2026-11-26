"""Fixtures of the website tests: contexts per role, the Vite manifest with the public entry, a hub file store in
memory, and a full content that fills every section.

The builders import the app's modules lazily, so that the tests of apps.py still collect while the rest does not
exist.

Every test with the database runs as production does: inside business A's own database (``hub_a``, entered by
``in_business_a``), its public pages and API on A's host. Business B (``hub_b``) has its own database beside it; a test
of B asks for ``hub_b`` and enters it.
"""

import json
from dataclasses import replace

import pytest
from django.core.cache import cache
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role

from apps.invoice.tests.conftest import catalog_of
from apps.sale.tests.conftest import make_user
from base.tenancy.tests.business import HOST, HUB_DB, HUB_DB_COMMITTED, A, B, in_business_a
from base.tenancy.tests.concurrency import hub_staff, plan_with_room

#: The marks, scopes and fixtures of the businesses' own databases, and what Sales' and Invoicing's tests already make
#: of them (users with a role on a host, the assistant's catalogue of a person of A), that these tests take from here.
__all__ = [
    "A", "B", "HOST", "HUB_DB", "HUB_DB_COMMITTED", "catalog_of", "hub_staff", "in_business_a", "make_user",
    "plan_with_room",
]

WEBSITE_ENTRY = "frontend/website.ts"
#: The public bundle as `vite build` names it (hashed per deploy).
WEBSITE_JS = "/static/spa/assets/website-9f8e7d.js"
WEBSITE_CSS = "/static/spa/assets/website-6c5b4a.css"


class Person:
    """A person of the team as the platform passes one (a user account), without a database row."""

    pk = None

    def __init__(self, name: str = "ana") -> None:
        self.name = name

    def get_username(self) -> str:
        return self.name

    def get_full_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name


def ctx_for(role: str | None = "hub_admin", scope: Scope = A, *, request=None, permissions=None) -> OperationContext:
    """The context a person with ``role`` on ``scope`` gets; ``role=None`` is an anonymous visitor."""
    if permissions is None:
        permissions = permissions_for_role(all_live_app_configs(), role) if role else frozenset()
    actor = Person() if role else None
    return OperationContext(scope=scope, actor=actor, permissions=permissions, language="en", request=request)


def with_language(ctx: OperationContext, language: str) -> OperationContext:
    return replace(ctx, language=language)


@pytest.fixture(autouse=True)
def clean_cache():
    """The cache is the process's memory in the tests: what one test caches never answers another."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def website_manifest(settings, tmp_path):
    """A Vite build manifest with the SPA's entry and the public website's, and no dev server."""
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "frontend/main.ts": {"file": "assets/main-abc123.js", "src": "frontend/main.ts", "isEntry": True},
                WEBSITE_ENTRY: {
                    "file": WEBSITE_JS.removeprefix("/static/spa/"),
                    "src": WEBSITE_ENTRY,
                    "isEntry": True,
                    "css": [WEBSITE_CSS.removeprefix("/static/spa/")],
                },
            }
        )
    )
    settings.DEBUG = False
    settings.LIVE = {**settings.LIVE, "spa": {**settings.LIVE["spa"], "manifest": manifest, "dev_server": None}}
    return manifest


@pytest.fixture
def hub_files(settings):
    """``storages["hub_files"]`` in memory, empty for each test."""
    from django.core.files.storage import storages

    settings.STORAGES = {**settings.STORAGES, "hub_files": {"BACKEND": "django.core.files.storage.InMemoryStorage"}}
    storages._storages.pop("hub_files", None)
    yield storages["hub_files"]
    storages._storages.pop("hub_files", None)


def full_content(**overrides) -> dict:
    """A draft that fills every section (as the editor sends it)."""
    content = {
        "topbar": {"name": "Pepe's Bistro", "logo": None},
        "hero": {"title": "Fresh food every day", "tagline": "Since 1998 in Gran Vía", "cover": None},
        "about": {"hidden": False, "title": "", "text": "We cook **everything** at home.", "image": None},
        "catalog": {"hidden": False, "title": "", "source": "service", "category_ids": [], "show_prices": True},
        "gallery": {"hidden": False, "title": "", "images": []},
        "reviews": {"hidden": False, "title": "", "place_ref": ""},
        "contact": {
            "hidden": False,
            "title": "",
            "phone": "+34 600 123 456",
            "whatsapp": "+34 600 123 456",
            "email": "hola@pepe.es",
            "socials": {"instagram": "https://instagram.com/pepe", "facebook": "", "tiktok": "", "x": ""},
            "hours": [
                {"day": "mon", "intervals": [{"opens": "09:00", "closes": "14:00"}]},
                {"day": "sun", "intervals": []},
            ],
        },
        "location": {
            "hidden": False,
            "title": "",
            "address_lines": ["Gran Vía 1", "28013 Madrid"],
            "map_url": "https://maps.google.com/?q=Gran+Via+1",
        },
        "footer": {"text": "Pepe Bistro S.L."},
    }
    for section, values in overrides.items():
        content[section] = {**content[section], **values}
    return content


#: Content whose bar names nobody and whose header has no title: the page goes by the business's own name.
NAMELESS = {"topbar": {"name": "", "logo": None}, "hero": {"title": "", "tagline": "", "cover": None}}


def page_names(html: str) -> list[str]:
    """What the page calls the business: in the browser's tab, in the top bar, as the header's title and in the
    footer."""
    import re

    tab = re.search(r"<title>([^<]*)</title>", html).group(1)
    bar = re.search(r'class="navbar-brand[^"]*" href="/">\s*<span>([^<]*)</span>', html).group(1)
    title = re.search(r"<h1[^>]*>([^<]*)</h1>", html).group(1)
    footer = re.search(r'<a class="[^"]*" href="/">([^<]*)</a>', html[html.index("<footer") :]).group(1)
    return [tab, bar, title, footer]


def catalog_snapshot() -> dict:
    """A catalog as publish leaves it in ``published_content``."""
    return {
        "source": "service",
        "show_prices": True,
        "groups": [
            {
                "name": "Hair",
                "items": [
                    {"name": "Cut", "price": 1500, "price_kind": "fixed", "minutes": 30},
                    {"name": "Colour", "price": 4000, "price_kind": "from", "minutes": 90},
                ],
            },
            {"name": "", "items": [{"name": "Consultation", "price": 0, "price_kind": "free", "minutes": 15}]},
        ],
    }


#: A business's place on Google Maps (Google's own example Place ID).
PLACE_ID = "ChIJN1t_tDeuEmsRUsoyG83frY4"
#: What the page's long review says (over the 280 characters a card shows).
LONG_REVIEW = "Me encanta este sitio. " * 20


def google_reviews(place_ref: str = PLACE_ID, **overrides) -> dict:
    """Google's rating and reviews of the place as ``apps.website.reviews`` keeps them: five reviews written 75 days
    ago, the last one long."""
    from datetime import timedelta

    from django.utils import timezone

    written = (timezone.now() - timedelta(days=75)).isoformat()
    payload = {
        "place_id": PLACE_ID,
        "place_ref": place_ref,
        "name": "Pepe's Bistro",
        "rating": 4.7,
        "count": 128,
        "maps_uri": "https://maps.google.com/?cid=7660264463346408491",
        "reviews": [
            {
                "author": f"Cliente {index}",
                "author_uri": f"https://www.google.com/maps/contrib/{index}",
                "rating": 5 - index % 2,
                "text": LONG_REVIEW.strip() if index == 4 else f"Muy bien, número {index}",
                "time": written,
                "uri": f"https://www.google.com/maps/reviews/r{index}",
            }
            for index in range(5)
        ],
        "fetched_at": timezone.now().isoformat(),
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def services_catalog(db):
    from apps.service.models import Category, Service

    hair, nails = Category.objects.create(name="Hair", sort_order=2), Category.objects.create(name="Nails", sort_order=1)
    Service.objects.create(name="Cut", price=1500, duration_minutes=30, category=hair)
    Service.objects.create(name="Manicure", price=2000, pricing_type="hourly", duration_minutes=45, category=nails)
    Service.objects.create(name="Advice", pricing_type="variable", duration_minutes=10, category=nails)
    return {"hair": hair, "nails": nails}


@pytest.fixture
def products_catalog(db):
    from apps.inventory.models import Category, Product, ProductCategory

    drinks = Category.objects.create(name="Drinks", slug="drinks", order=1)
    food = Category.objects.create(name="Food", slug="food", order=0)
    cola = Product.objects.create(name="Cola", sku="COLA", price=250)
    bocata = Product.objects.create(name="Bocata", sku="BOC", price=550)
    Product.objects.create(name="Gone", sku="GONE", price=100, is_sold_out=True)
    Product.objects.create(name="Loose", sku="LOOSE", price=0)
    ProductCategory.objects.create(product=cola, category=drinks)
    ProductCategory.objects.create(product=bocata, category=food)
    return {"drinks": drinks, "food": food}


def source_off(monkeypatch, label: str) -> None:
    """``label`` off in every hub (``base.apps_on.active_apps``), the website and the rest still on."""
    from apps.website.queries import catalog, public

    real = catalog.active_apps
    monkeypatch.setattr(catalog, "active_apps", lambda scope: real(scope) - {label})
    monkeypatch.setattr(public, "active_apps", lambda scope: real(scope) - {label})


@pytest.fixture
def no_google(monkeypatch):
    """Any attempt to ask Google fails the test."""
    from apps.website import reviews

    def refuse(*args, **kwargs):
        raise AssertionError("a read must never ask Google")

    monkeypatch.setattr(reviews, "load", refuse)
