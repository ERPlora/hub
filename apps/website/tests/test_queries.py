"""The website's reads: the editor's site and preview, the QR, and the public site and catalog (no session, only
when published). The catalog is read from Inventory or Services by their operations' names."""

import base64
import datetime as dt

import pytest
from django.core.cache import cache
from django.test import RequestFactory
from live.context import Scope
from live.errors import NotFound, PermissionDenied
from live.operations import get

from apps.website.queries import catalog_cache_key, live_version, published_page, read_catalog
from apps.website.schemas import CatalogSection
from apps.website import reviews
from apps.website.tests.conftest import PLACE_ID, A, B, ctx_for, full_content, google_reviews, with_language
from base.models import Hub

pytestmark = pytest.mark.django_db


def run(name: str, data: dict | None = None, ctx=None):
    op = get(name)
    return op(ctx or ctx_for(), op.input(**(data or {})))


def save(content=None, template="classic"):
    return run("website.site.save", {"template": template, "theme": {}, "content": content or full_content()})


def visitor(**request):
    """An anonymous visitor of hub ``a``, with a request (the public routes always have one)."""
    return ctx_for(None, request=RequestFactory().get("/api/website/public/site", HTTP_HOST="a.localhost", **request))


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


# The editor


def test_the_site_of_a_hub_that_never_saved_one_is_the_empty_classic_draft(settings):
    out = run("website.site.get", ctx=ctx_for("hub_manager"))
    assert (out.template, out.published_version, out.is_live, out.has_changes) == ("classic", 0, False, False)
    assert out.content.hero.title == "" and (out.theme.palette, out.theme.mode) == ("ocean", "auto")
    assert out.public_url == f"https://a.{settings.HUB_BASE_DOMAIN}/"


def test_the_site_says_what_is_published_and_whether_the_draft_moved_on():
    save()
    run("website.site.publish")
    out = run("website.site.get")
    assert (out.published_version, out.is_live, out.has_changes) == (1, True, False)
    save(full_content(hero={"title": "New"}))
    assert run("website.site.get").has_changes is True


def test_an_employee_does_not_see_the_website():
    with pytest.raises(PermissionDenied):
        run("website.site.get", ctx=ctx_for("hub_employee"))


@pytest.mark.usefixtures("website_manifest")
def test_the_preview_is_the_draft_rendered_with_a_fresh_catalog(services_catalog):
    save(template="bold")
    html = run("website.site.preview").html
    assert '<body class="ws-bold text-break"' in html and "data-ep-preview" in html
    assert "Fresh food every day" in html and "Manicure" in html
    # In the editor's language.
    assert "Entrar" in run("website.site.preview", ctx=with_language(ctx_for(), "es")).html


def test_only_who_manages_the_website_previews_it():
    with pytest.raises(PermissionDenied):
        run("website.site.preview", ctx=ctx_for("hub_manager"))


def test_the_qr_is_the_hubs_address_as_png_or_svg():
    request = RequestFactory().get("/api/website/qr", HTTP_HOST="a.localhost:8000")
    png = run("website.qr.get", {"format": "png"}, ctx_for("hub_manager", request=request))
    assert (png.url, png.content_type, png.filename) == ("http://a.localhost:8000/", "image/png", "website-qr-a.png")
    assert base64.b64decode(png.content_base64).startswith(b"\x89PNG")
    svg = run("website.qr.get", {"format": "svg"}, ctx_for(request=request))
    assert (svg.content_type, svg.filename) == ("image/svg+xml", "website-qr-a.svg")
    assert base64.b64decode(svg.content_base64).startswith(b"<svg")


# The catalog, by the other apps' operations


def test_the_services_catalog_is_grouped_by_category_in_their_order(services_catalog):
    snapshot = read_catalog(ctx_for(None), CatalogSection(source="service"))
    assert snapshot == {
        "source": "service",
        "show_prices": True,
        "groups": [
            {
                "name": "Nails",
                "items": [
                    {"name": "Advice", "price": 0, "price_kind": "none", "minutes": 10},
                    {"name": "Manicure", "price": 2000, "price_kind": "hourly", "minutes": 45},
                ],
            },
            {"name": "Hair", "items": [{"name": "Cut", "price": 1500, "price_kind": "fixed", "minutes": 30}]},
        ],
    }


def test_the_products_catalog_lists_what_is_on_sale_by_category(products_catalog):
    snapshot = read_catalog(ctx_for(None), CatalogSection(source="inventory", show_prices=False))
    assert snapshot == {
        "source": "inventory",
        "show_prices": False,
        "groups": [
            {"name": "Food", "items": [{"name": "Bocata", "price": 550, "price_kind": "fixed", "minutes": None}]},
            {"name": "Drinks", "items": [{"name": "Cola", "price": 250, "price_kind": "fixed", "minutes": None}]},
            {"name": "", "items": [{"name": "Loose", "price": 0, "price_kind": "none", "minutes": None}]},
        ],
    }


def test_a_category_filter_keeps_only_those_categories(products_catalog):
    section = CatalogSection(source="inventory", category_ids=[products_catalog["drinks"].id])
    assert [group["name"] for group in read_catalog(ctx_for(None), section)["groups"]] == ["Drinks"]


def source_off(monkeypatch, label: str) -> None:
    """``label`` off in every hub (``base.relay.active_apps``: in phase 1 every installed app is on; in phase 2 the
    hub's activation), the website and the rest still on."""
    from base import relay

    real = relay.active_apps
    monkeypatch.setattr(relay, "active_apps", lambda scope: real(scope) - {label})


def test_a_source_whose_app_is_off_in_the_hub_is_an_empty_catalog_not_an_error(monkeypatch, products_catalog):
    # flow: WEBSITE-F05 — Inventory has products on sale, but it is not on in this hub: nothing is read from it.
    source_off(monkeypatch, "inventory")
    assert read_catalog(ctx_for(None), CatalogSection(source="inventory"))["groups"] == []


def test_no_source_is_no_catalog():
    assert read_catalog(ctx_for(None), CatalogSection()) == {"source": None, "show_prices": True, "groups": []}


def test_the_editor_lists_the_categories_of_a_source_to_choose_from(services_catalog, products_catalog):
    services = run("website.catalog.categories", {"source": "service"}).categories
    assert [category.name for category in services] == ["Nails", "Hair"]
    products = run("website.catalog.categories", {"source": "inventory"}).categories
    assert [(category.id, category.name) for category in products] == [
        (products_catalog["food"].id, "Food"),
        (products_catalog["drinks"].id, "Drinks"),
    ]
    with pytest.raises(PermissionDenied):
        run("website.catalog.categories", {"source": "service"}, ctx_for("hub_manager"))


def test_the_categories_of_a_source_whose_app_is_off_in_the_hub_are_none(monkeypatch, services_catalog):
    source_off(monkeypatch, "service")
    assert run("website.catalog.categories", {"source": "service"}).categories == []


# The public reads


def test_the_public_site_is_not_found_until_published_and_after_it_goes_offline():
    save()
    with pytest.raises(NotFound) as missing:
        run("website.public.site", ctx=visitor())
    assert missing.value.code == "website.not_published"
    run("website.site.publish")
    assert run("website.public.site", ctx=visitor()).version == 1
    run("website.site.unpublish")
    with pytest.raises(NotFound):
        run("website.public.site", ctx=visitor())


def test_the_public_site_is_what_was_published_without_the_hidden_sections():
    save(full_content(about={"hidden": True, "text": "secret plans"}))
    run("website.site.publish")
    save(full_content(hero={"title": "Draft only"}))
    out = run("website.public.site", ctx=visitor())
    assert (out.version, out.template) == (1, "classic")
    assert out.content.hero.title == "Fresh food every day"
    assert out.content.about.hidden is True and out.content.about.text == ""


def test_a_hidden_gallery_leaves_no_photo_in_the_public_site(hub_files):
    import io

    from PIL import Image as PILImage

    buffer = io.BytesIO()
    PILImage.new("RGB", (4, 3), (9, 9, 9)).save(buffer, format="PNG")
    photo = run(
        "website.image.upload",
        {"filename": "a.png", "content_type": "image/png", "data_base64": base64.b64encode(buffer.getvalue()).decode()},
    )
    save(full_content(gallery={"hidden": True, "title": "Our work", "images": [{"id": str(photo.id), "url": ""}]}))
    run("website.site.publish")
    gallery = run("website.public.site", ctx=visitor()).content.gallery
    assert gallery.model_dump() == {"hidden": True, "title": "", "images": []}


def business_in(country: str, slug: str = "a") -> None:
    """``slug``'s business as erplora.com registered it in ``country``: its currency is its country's (BASE-F50)."""
    Hub.objects.filter(slug=slug).update(country=country)


def price_labels(out) -> dict[str, str]:
    return {item.name: item.price_label for group in out.groups for item in group.items}


def test_the_public_catalog_is_read_live_priced_for_the_visitor_and_cached_a_minute(services_catalog):
    business_in("ES")
    save()
    run("website.site.publish")
    from apps.service.models import Service

    Service.objects.create(name="Beard", price=900, duration_minutes=20, category=services_catalog["hair"])
    out = run("website.public.catalog", ctx=with_language(visitor(), "es"))
    hair = next(group for group in out.groups if group.name == "Hair")
    assert [(item.name, item.price_label) for item in hair.items] == [("Beard", "9,00\xa0€"), ("Cut", "15,00\xa0€")]
    assert cache.get(catalog_cache_key("a", 1, "es", "EUR")) is not None
    Service.objects.filter(name="Beard").update(is_active=False)
    cached = run("website.public.catalog", ctx=with_language(visitor(), "es"))
    assert "Beard" in [item.name for group in cached.groups for item in group.items]


@pytest.mark.parametrize(
    ("country", "cut", "manicure"),
    [
        ("PL", "15,00\xa0PLN", "20,00\xa0PLN"),
        # The yen has no minor unit: a price of 1500 is ¥1,500, never ¥15.
        ("JP", "1.500\xa0JPY", "2.000\xa0JPY"),
    ],
)
def test_the_public_catalog_is_priced_in_the_business_s_currency(services_catalog, country, cut, manicure):
    # flow: website-business-currency — the currency of the business's country, with its decimals, never the euro.
    business_in(country)
    save()
    run("website.site.publish")
    labels = price_labels(run("website.public.catalog", ctx=with_language(visitor(), "es")))
    assert labels["Cut"] == cut
    assert labels["Manicure"].startswith(manicure)
    assert labels["Advice"] == ""
    assert not any("€" in label for label in labels.values())


@pytest.mark.usefixtures("website_manifest")
def test_the_editors_preview_prices_in_the_business_s_currency(services_catalog):
    # flow: website-business-currency — the preview paints the page the visitors will see, in the same currency.
    business_in("PL")
    save()
    html = run("website.site.preview").html
    assert "PLN\xa015.00" in html
    assert "€" not in html


def test_the_public_catalog_follows_a_change_of_the_business_s_country_at_once(services_catalog):
    # The catalog is kept a minute: a business whose country (hence its currency) changes on erplora.com is never
    # priced in the old one meanwhile.
    business_in("ES")
    save()
    run("website.site.publish")
    assert price_labels(run("website.public.catalog", ctx=with_language(visitor(), "es")))["Cut"] == "15,00\xa0€"
    business_in("PL")
    assert price_labels(run("website.public.catalog", ctx=with_language(visitor(), "es")))["Cut"] == "15,00\xa0PLN"


def test_the_public_catalog_of_an_unpublished_site_is_not_found():
    save()
    with pytest.raises(NotFound):
        run("website.public.catalog", ctx=visitor())


def test_the_public_catalog_of_a_hidden_catalog_is_empty(services_catalog):
    save(full_content(catalog={"hidden": True}))
    run("website.site.publish")
    assert run("website.public.catalog", ctx=visitor()).groups == []


def test_the_public_catalog_of_a_source_turned_off_after_publishing_is_empty_not_an_error(monkeypatch, services_catalog):
    # flow: WEBSITE-F05 — the page refreshes its catalog on every visit: Services off in the hub, nothing is read.
    save(full_content(catalog={"source": "service"}))
    run("website.site.publish")
    assert [group.name for group in run("website.public.catalog", ctx=visitor()).groups] == ["Nails", "Hair"]
    cache.clear()
    source_off(monkeypatch, "service")
    catalog = run("website.public.catalog", ctx=visitor())
    assert (catalog.source, catalog.groups) == ("service", [])


def test_the_page_public_home_paints_is_the_live_publication_of_its_hub():
    assert published_page(A) is None
    save(template="minimal")
    run("website.site.publish")
    page = published_page(A)
    assert (page["version"], page["template"]) == (1, "minimal")
    assert page["content"]["hero"]["title"] == "Fresh food every day"
    assert isinstance(page["published_at"], dt.datetime)
    assert (published_page(B), live_version(A), live_version(B)) == (None, 1, 0)
    # A scope that is no hub has nothing to paint, never an error.
    assert (published_page(Scope("host", "nohub")), live_version(Scope("host", "nohub"))) == (None, 0)
    run("website.site.unpublish")
    assert (published_page(A), live_version(A)) == (None, 0)


# Google's reviews (read here, never asked: services and the public home ask Google)


@pytest.fixture
def no_google(monkeypatch):
    """Any attempt to ask Google fails the test."""

    def refuse(*args, **kwargs):
        raise AssertionError("a read must never ask Google")

    monkeypatch.setattr(reviews, "load", refuse)


def test_the_editor_sees_whether_googles_reviews_are_there(settings, no_google):
    settings.GOOGLE_PLACES_API_KEY = ""
    assert run("website.site.get").reviews.state == "empty"
    save(full_content(reviews={"place_ref": PLACE_ID}))
    assert run("website.site.get").reviews.state == "unavailable"
    settings.GOOGLE_PLACES_API_KEY = "test-key"
    assert run("website.site.get").reviews.state == "waiting"
    cache.set(reviews.reviews_key("a", PLACE_ID), reviews.FAILED, reviews.FAILURE_TTL)
    assert run("website.site.get").reviews.state == "failed"
    payload = google_reviews()
    cache.set(reviews.reviews_key("a", PLACE_ID), payload, reviews.TTL)
    status = run("website.site.get").reviews
    assert (status.state, status.rating, status.count) == ("ready", 4.7, 128)
    assert status.fetched_at.isoformat() == payload["fetched_at"]


@pytest.mark.usefixtures("website_manifest")
def test_the_preview_paints_the_reviews_kept_or_says_where_they_will_be(settings, no_google):
    settings.GOOGLE_PLACES_API_KEY = "test-key"
    save(full_content(reviews={"place_ref": PLACE_ID}))
    assert "data-ep-reviews-hint" in run("website.site.preview").html
    cache.set(reviews.reviews_key("a", PLACE_ID), google_reviews(), reviews.TTL)
    html = run("website.site.preview").html
    assert "128 reviews on Google" in html and "data-ep-reviews-hint" not in html


@pytest.mark.usefixtures("website_manifest")
def test_the_sites_last_good_reviews_stand_in_when_nothing_is_kept(settings, no_google):
    from apps.website.models import Site

    settings.GOOGLE_PLACES_API_KEY = "test-key"
    save(full_content(reviews={"place_ref": PLACE_ID}))
    Site.objects.update(reviews_snapshot=google_reviews(count=9))
    assert run("website.site.get").reviews.count == 9
    assert "9 reviews on Google" in run("website.site.preview").html


def test_the_public_reviews_are_the_kept_ones_in_the_visitors_language(settings, no_google):
    settings.GOOGLE_PLACES_API_KEY = "test-key"
    save(full_content(reviews={"place_ref": PLACE_ID}))
    with pytest.raises(NotFound):
        run("website.public.reviews", ctx=visitor())
    run("website.site.publish")
    assert run("website.public.reviews", ctx=visitor()).available is False
    cache.set(reviews.reviews_key("a", PLACE_ID), google_reviews(), reviews.TTL)
    out = run("website.public.reviews", ctx=with_language(visitor(), "es"))
    assert (out.available, out.rating_label, out.count_label) == (True, "4,7", "128 reseñas en Google")
    assert out.stars == ["on", "on", "on", "on", "half"]
    assert [review.author for review in out.reviews] == [f"Cliente {index}" for index in range(5)]
    assert out.reviews[4].full_text and out.reviews[4].text.endswith("…")
    assert out.write_uri == f"https://search.google.com/local/writereview?placeid={PLACE_ID}"


def test_hidden_reviews_are_not_given_to_visitors(settings, no_google):
    settings.GOOGLE_PLACES_API_KEY = "test-key"
    cache.set(reviews.reviews_key("a", PLACE_ID), google_reviews(), reviews.TTL)
    save(full_content(reviews={"place_ref": PLACE_ID, "hidden": True}))
    run("website.site.publish")
    assert run("website.public.reviews", ctx=visitor()).available is False
    # Nor the place behind them: the public site leaves a hidden section empty.
    assert run("website.public.site", ctx=visitor()).content.reviews.place_ref == ""



def test_the_public_reviews_come_from_the_sites_last_good_answer_when_the_cache_is_cold(settings, no_google):
    # flow: WEBSITE-F12 — after a deploy or a cache restart the page's visitors still get the kept reviews.
    from apps.website.models import Site

    settings.GOOGLE_PLACES_API_KEY = "test-key"
    save(full_content(reviews={"place_ref": PLACE_ID}))
    run("website.site.publish")
    Site.objects.update(reviews_snapshot=google_reviews(count=9))
    cache.clear()
    out = run("website.public.reviews", ctx=visitor())
    assert (out.available, out.count_label) == (True, "9 reviews on Google")
