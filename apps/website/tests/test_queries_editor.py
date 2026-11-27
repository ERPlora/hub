"""The editor's reads: the site and its preview, the QR, the categories its catalog may show, and Google's reviews
as the editor sees them (read here, never asked: services and the public home ask Google)."""

import base64

import pytest
from django.core.cache import cache
from django.test import RequestFactory
from live.errors import PermissionDenied

from apps.website import reviews
from apps.website.tests.conftest import (
    HOST,
    HUB_DB,
    NAMELESS,
    PLACE_ID,
    A,
    ctx_for,
    full_content,
    google_reviews,
    page_names,
    source_off,
    with_language,
)
from apps.website.tests.test_services import run
from base.models import Hub
from base.tests.test_qr import expected_dark, png_dark, svg_dark

pytestmark = HUB_DB


def save(content=None, template="classic"):
    return run("website.site.save", {"template": template, "theme": {}, "content": content or full_content()})


def business_in(country: str, slug: str = A.key) -> None:
    """``slug``'s business as erplora.com registered it in ``country``: its currency is its country's (BASE-F50)."""
    Hub.objects.filter(slug=slug).update(country=country)


def test_the_site_of_a_hub_that_never_saved_one_is_the_empty_classic_draft(settings):
    out = run("website.site.get", ctx=ctx_for("hub_manager"))
    assert (out.template, out.published_version, out.is_live, out.has_changes) == ("classic", 0, False, False)
    assert out.content.hero.title == "" and (out.theme.palette, out.theme.mode) == ("ocean", "auto")
    assert out.public_url == f"https://{A.key}.{settings.HUB_BASE_DOMAIN}/"


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


@pytest.mark.usefixtures("website_manifest")
def test_the_preview_of_a_page_that_names_nobody_goes_by_the_business_s_name():
    # flow: WEBSITE-F06 — the editor sees the name its visitors will see: the business's as erplora.com registered it
    # (Settings › Business), never the slug of its address (hub#2084); a business without one (a demo), its address.
    Hub.objects.filter(slug=A.key).update(name="Salón Aurora")
    save(full_content(**NAMELESS))
    assert page_names(run("website.site.preview").html) == ["Salón Aurora"] * 4
    Hub.objects.filter(slug=A.key).update(name="")
    assert page_names(run("website.site.preview").html) == [A.key] * 4


def test_only_who_manages_the_website_previews_it():
    with pytest.raises(PermissionDenied):
        run("website.site.preview", ctx=ctx_for("hub_manager"))


def test_the_qr_is_the_hubs_address_as_png_or_svg():
    request = RequestFactory().get("/api/website/qr", HTTP_HOST=f"{HOST}:8000")
    png = run("website.qr.get", {"format": "png"}, ctx_for("hub_manager", request=request))
    assert (png.url, png.content_type, png.filename) == (f"http://{HOST}:8000/", "image/png", f"website-qr-{A.key}.png")
    assert base64.b64decode(png.content_base64).startswith(b"\x89PNG")
    svg = run("website.qr.get", {"format": "svg"}, ctx_for(request=request))
    assert (svg.content_type, svg.filename) == ("image/svg+xml", f"website-qr-{A.key}.svg")
    assert base64.b64decode(svg.content_base64).startswith(b"<svg")


def test_the_catalogs_qr_opens_the_page_right_at_its_catalog():
    request = RequestFactory().get("/api/website/qr", HTTP_HOST=f"{HOST}:8000")
    catalog = f"http://{HOST}:8000/#catalog"
    png = run("website.qr.get", {"format": "png", "target": "catalog"}, ctx_for("hub_manager", request=request))
    assert (png.url, png.filename) == (catalog, f"website-catalog-qr-{A.key}.png")
    assert png_dark(base64.b64decode(png.content_base64)) == expected_dark(catalog)
    svg = run("website.qr.get", {"format": "svg", "target": "catalog"}, ctx_for(request=request))
    assert (svg.url, svg.filename) == (catalog, f"website-catalog-qr-{A.key}.svg")
    assert svg_dark(base64.b64decode(svg.content_base64)) == expected_dark(catalog)


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


@pytest.mark.usefixtures("website_manifest")
def test_the_editors_preview_prices_in_the_business_s_currency(services_catalog):
    # flow: website-business-currency — the preview paints the page the visitors will see, in the same currency.
    business_in("PL")
    save()
    html = run("website.site.preview").html
    assert "PLN\xa015.00" in html
    assert "€" not in html


def test_the_editor_sees_whether_googles_reviews_are_there(settings, no_google):
    settings.GOOGLE_PLACES_API_KEY = ""
    assert run("website.site.get").reviews.state == "empty"
    save(full_content(reviews={"place_ref": PLACE_ID}))
    assert run("website.site.get").reviews.state == "unavailable"
    settings.GOOGLE_PLACES_API_KEY = "test-key"
    assert run("website.site.get").reviews.state == "waiting"
    cache.set(reviews.reviews_key(A.key, PLACE_ID), reviews.FAILED, reviews.FAILURE_TTL)
    assert run("website.site.get").reviews.state == "failed"
    payload = google_reviews()
    cache.set(reviews.reviews_key(A.key, PLACE_ID), payload, reviews.TTL)
    status = run("website.site.get").reviews
    assert (status.state, status.rating, status.count) == ("ready", 4.7, 128)
    assert status.fetched_at.isoformat() == payload["fetched_at"]


@pytest.mark.usefixtures("website_manifest")
def test_the_preview_paints_the_reviews_kept_or_says_where_they_will_be(settings, no_google):
    settings.GOOGLE_PLACES_API_KEY = "test-key"
    save(full_content(reviews={"place_ref": PLACE_ID}))
    assert "data-ep-reviews-hint" in run("website.site.preview").html
    cache.set(reviews.reviews_key(A.key, PLACE_ID), google_reviews(), reviews.TTL)
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
