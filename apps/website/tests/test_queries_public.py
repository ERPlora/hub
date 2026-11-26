"""The public reads: the site, the catalog and Google's reviews (no session, only when published; the reviews are
read here, never asked), and the page the public home paints."""

import base64
import datetime as dt

import pytest
from django.core.cache import cache
from django.test import RequestFactory
from live.context import Scope
from live.errors import NotFound

from apps.website.queries.public import catalog_cache_key, live_version, published_page
from apps.website import reviews
from apps.website.tests.conftest import (
    HOST,
    HUB_DB,
    PLACE_ID,
    A,
    B,
    ctx_for,
    full_content,
    google_reviews,
    source_off,
    with_language,
)
from apps.website.tests.test_queries_editor import business_in, save
from apps.website.tests.test_services import run
from base.tenancy.context import use_hub

pytestmark = HUB_DB


def visitor(**request):
    """An anonymous visitor of business A, with a request (the public routes always have one)."""
    return ctx_for(None, request=RequestFactory().get("/api/website/public/site", HTTP_HOST=HOST, **request))


def price_labels(out) -> dict[str, str]:
    return {item.name: item.price_label for group in out.groups for item in group.items}


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


def test_the_public_catalog_is_read_live_priced_for_the_visitor_and_cached_a_minute(services_catalog):
    business_in("ES")
    save()
    run("website.site.publish")
    from apps.service.models import Service

    Service.objects.create(name="Beard", price=900, duration_minutes=20, category=services_catalog["hair"])
    out = run("website.public.catalog", ctx=with_language(visitor(), "es"))
    hair = next(group for group in out.groups if group.name == "Hair")
    assert [(item.name, item.price_label) for item in hair.items] == [("Beard", "9,00\xa0€"), ("Cut", "15,00\xa0€")]
    assert cache.get(catalog_cache_key(A.key, 1, "es", "EUR")) is not None
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


def test_the_page_public_home_paints_is_the_live_publication_of_its_hub(hub_b):
    assert published_page(A) is None
    save(template="minimal")
    run("website.site.publish")
    page = published_page(A)
    assert (page["version"], page["template"]) == (1, "minimal")
    assert page["content"]["hero"]["title"] == "Fresh food every day"
    assert isinstance(page["published_at"], dt.datetime)
    assert live_version(A) == 1
    with use_hub(hub_b):
        assert (published_page(B), live_version(B)) == (None, 0)
    # A scope that is no hub has nothing to paint, never an error.
    assert (published_page(Scope("host", "nohub")), live_version(Scope("host", "nohub"))) == (None, 0)
    run("website.site.unpublish")
    assert (published_page(A), live_version(A)) == (None, 0)


def test_the_public_reviews_are_the_kept_ones_in_the_visitors_language(settings, no_google):
    settings.GOOGLE_PLACES_API_KEY = "test-key"
    save(full_content(reviews={"place_ref": PLACE_ID}))
    with pytest.raises(NotFound):
        run("website.public.reviews", ctx=visitor())
    run("website.site.publish")
    assert run("website.public.reviews", ctx=visitor()).available is False
    cache.set(reviews.reviews_key(A.key, PLACE_ID), google_reviews(), reviews.TTL)
    out = run("website.public.reviews", ctx=with_language(visitor(), "es"))
    assert (out.available, out.rating_label, out.count_label) == (True, "4,7", "128 reseñas en Google")
    assert out.stars == ["on", "on", "on", "on", "half"]
    assert [review.author for review in out.reviews] == [f"Cliente {index}" for index in range(5)]
    assert out.reviews[4].full_text and out.reviews[4].text.endswith("…")
    assert out.write_uri == f"https://search.google.com/local/writereview?placeid={PLACE_ID}"


def test_hidden_reviews_are_not_given_to_visitors(settings, no_google):
    settings.GOOGLE_PLACES_API_KEY = "test-key"
    cache.set(reviews.reviews_key(A.key, PLACE_ID), google_reviews(), reviews.TTL)
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
