"""The website's writes: save the draft, publish it (with the catalog's snapshot and a new version), take it offline
and upload an image to the hub file store."""

import base64
import hashlib
import io
import threading
import uuid

import pytest
from django.core.cache import cache
from django.db import connection, transaction
from live.errors import InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent
from live.operations import get
from PIL import Image as PILImage

from apps.website.models import Image, Site
from apps.website.queries import page_cache_key
from apps.website.tests.conftest import A, B, ctx_for, full_content
from base.models import Hub

pytestmark = pytest.mark.django_db


def run(name: str, data: dict | None = None, ctx=None):
    op = get(name)
    return op(ctx or ctx_for(), op.input(**(data or {})))


def save(content=None, template="classic", theme=None, ctx=None):
    return run(
        "website.site.save",
        {"template": template, "theme": theme or {}, "content": full_content() if content is None else content},
        ctx,
    )


def events(name: str) -> list[OutboxEvent]:
    return list(OutboxEvent.objects.filter(name=name).order_by("created_at"))


def png_bytes(width=4, height=3, colour=(200, 30, 30), fmt="PNG") -> bytes:
    buffer = io.BytesIO()
    PILImage.new("RGB", (width, height), colour).save(buffer, format=fmt)
    return buffer.getvalue()


def upload(raw: bytes, content_type="image/png", filename="logo.png", ctx=None):
    return run(
        "website.image.upload",
        {"filename": filename, "content_type": content_type, "data_base64": base64.b64encode(raw).decode()},
        ctx,
    )


@pytest.fixture
def services_catalog(db):
    """Two offered services in «Hair» and one without a category, as Services keeps them."""
    from apps.service.models import Category, Service

    hair = Category.objects.create(name="Hair", sort_order=1)
    Service.objects.create(name="Cut", price=1500, duration_minutes=30, category=hair)
    Service.objects.create(name="Colour", price=4000, pricing_type="from", duration_minutes=90, category=hair)
    Service.objects.create(name="Consultation", price=0, pricing_type="free", duration_minutes=15)
    Service.objects.create(name="Retired", price=1000, is_active=False)
    return hair


# Save


def test_save_keeps_the_draft_and_tells_the_editor():
    out = save(template="modern", theme={"palette": "forest", "custom": {"primary": "#AA0000", "accent": "#112233"}})

    site = Site.objects.get()
    assert (site.template, site.theme["custom"]["primary"], site.content["hero"]["title"]) == ("modern", "#aa0000", "Fresh food every day")
    assert site.updated_by == "ana"
    assert (out.template, out.published_version, out.is_live, out.has_changes) == ("modern", 0, False, True)
    assert [event.payload for event in events("website.site.updated")] == [{"id": str(site.id)}]


def test_saving_the_same_draft_again_changes_nothing():
    save()
    save()
    assert len(events("website.site.updated")) == 1


def test_changing_the_template_keeps_every_text():
    save(template="classic")
    out = save(template="bold")
    assert out.template == "bold"
    assert out.content.hero.title == "Fresh food every day"
    assert out.content.about.text == "We cook **everything** at home."


def test_only_who_manages_the_website_saves_it():
    with pytest.raises(PermissionDenied):
        save(ctx=ctx_for("hub_manager"))
    assert not Site.objects.exists()


def test_an_image_of_the_draft_is_an_upload_of_this_hub_and_its_url_is_the_servers(hub_files):
    image = upload(png_bytes())
    content = full_content(hero={"cover": {"id": str(image.id), "url": "https://evil.example/x.png"}})
    out = save(content)
    assert out.content.hero.cover.url == image.url
    assert Site.objects.get().content["hero"]["cover"] == {"id": str(image.id), "url": image.url}


def test_an_image_that_is_no_upload_of_this_hub_is_refused(hub_files):
    with pytest.raises(InvalidPayload) as refused:
        save(full_content(about={"image": {"id": str(uuid.uuid4()), "url": ""}}))
    assert set(refused.value.fields) == {"content.about.image"}
    other_hub = upload(png_bytes(), ctx=ctx_for(scope=B))
    with pytest.raises(InvalidPayload) as refused:
        save(full_content(topbar={"logo": {"id": str(other_hub.id), "url": other_hub.url}}))
    assert set(refused.value.fields) == {"content.topbar.logo"}


# Publish


def test_publish_copies_the_draft_with_a_catalog_snapshot_bumps_the_version_and_clears_the_cache(
    services_catalog, django_capture_on_commit_callbacks
):
    save(template="modern", theme={"palette": "forest", "mode": "dark"})
    cache.set(page_cache_key("a", 0, "en"), b"stale")
    with django_capture_on_commit_callbacks(execute=True):
        out = run("website.site.publish")
    site = Site.objects.get()
    assert (out.published_version, out.is_live) == (1, True)
    assert out.published_at is not None and site.published_at == out.published_at
    published = site.published_content
    assert (published["template"], published["theme"]["palette"], published["theme"]["mode"]) == ("modern", "forest", "dark")
    assert published["content"] == site.content
    assert published["catalog"] == {
        "source": "service",
        "show_prices": True,
        "groups": [
            {
                "name": "Hair",
                "items": [
                    {"name": "Colour", "price": 4000, "price_kind": "from", "minutes": 90},
                    {"name": "Cut", "price": 1500, "price_kind": "fixed", "minutes": 30},
                ],
            },
            {"name": "", "items": [{"name": "Consultation", "price": 0, "price_kind": "free", "minutes": 15}]},
        ],
    }
    assert [event.payload for event in events("website.site.published")] == [{"id": str(site.id), "version": 1}]
    assert cache.get(page_cache_key("a", 0, "en")) is None
    # A change of the draft stays out of the page until it is published again.
    save(template="bold")
    assert Site.objects.get().published_content["template"] == "modern"
    cache.set(page_cache_key("a", 1, "es"), b"old")
    with django_capture_on_commit_callbacks(execute=True):
        assert run("website.site.publish").published_version == 2
    assert Site.objects.get().published_content["template"] == "bold"
    assert cache.get(page_cache_key("a", 1, "es")) is None


def test_publish_snapshots_only_the_chosen_categories(services_catalog):
    save(full_content(catalog={"category_ids": [str(services_catalog.id)]}))
    run("website.site.publish")
    groups = Site.objects.get().published_content["catalog"]["groups"]
    assert [group["name"] for group in groups] == ["Hair"]


def test_publish_without_the_catalogs_app_leaves_an_empty_catalog_not_an_error(monkeypatch):
    from django.apps import apps

    real = apps.is_installed
    monkeypatch.setattr(apps, "is_installed", lambda name: False if name == "apps.service" else real(name))
    save()
    run("website.site.publish")
    assert Site.objects.get().published_content["catalog"] == {"source": "service", "show_prices": True, "groups": []}


def test_publishing_a_site_never_saved_publishes_the_empty_page():
    out = run("website.site.publish")
    assert (out.published_version, out.is_live) == (1, True)
    assert Site.objects.get().published_content["content"]["hero"]["title"] == ""


def test_only_who_manages_the_website_publishes_it():
    save()
    with pytest.raises(PermissionDenied):
        run("website.site.publish", ctx=ctx_for("hub_manager"))
    assert Site.objects.get().published_version == 0


# One site per hub (phase 1: the tables are shared, the row names its hub)


def hub_site(slug: str) -> Site:
    return Site.objects.get(hub_id=Hub.objects.get(slug=slug).id)


def test_each_hub_saves_and_publishes_its_own_site():
    save(template="modern", ctx=ctx_for(scope=A))
    run("website.site.publish", ctx=ctx_for(scope=A))
    save(full_content(hero={"title": "Bea's barber shop"}), template="bold", ctx=ctx_for(scope=B))
    assert run("website.site.publish", ctx=ctx_for(scope=B)).published_version == 1
    a, b = hub_site("a"), hub_site("b")
    assert (a.published_content["template"], a.published_content["content"]["hero"]["title"]) == (
        "modern",
        "Fresh food every day",
    )
    assert (b.published_content["template"], b.published_content["content"]["hero"]["title"]) == (
        "bold",
        "Bea's barber shop",
    )
    assert (a.published_version, b.published_version) == (1, 1)
    run("website.site.unpublish", ctx=ctx_for(scope=B))
    assert (hub_site("a").is_live, hub_site("b").is_live) == (True, False)


def test_the_team_of_another_hub_never_reads_nor_changes_this_hubs_site():
    save(template="modern", ctx=ctx_for(scope=A))
    run("website.site.publish", ctx=ctx_for(scope=A))
    save(full_content(hero={"title": "Draft only"}), template="modern", ctx=ctx_for(scope=A))
    b_admin = ctx_for(scope=B)
    seen = run("website.site.get", ctx=b_admin)
    assert (seen.template, seen.content.hero.title, seen.published_version, seen.is_live) == ("classic", "", 0, False)
    assert "Draft only" not in run("website.site.preview", ctx=b_admin).html
    save(full_content(hero={"title": "Overwritten"}), template="bold", ctx=b_admin)
    run("website.site.unpublish", ctx=b_admin)
    a = hub_site("a")
    assert (a.template, a.content["hero"]["title"], a.published_version, a.is_live) == ("modern", "Draft only", 1, True)
    assert run("website.site.get", ctx=ctx_for(scope=A)).content.hero.title == "Draft only"


def test_taking_offline_a_site_never_saved_keeps_it_unsaved():
    out = run("website.site.unpublish")
    assert (out.published_version, out.is_live) == (0, False)
    assert not Site.objects.exists()


# Take offline


def test_taking_the_site_offline_keeps_its_version_and_publishing_again_goes_on(django_capture_on_commit_callbacks):
    save()
    run("website.site.publish")
    cache.set(page_cache_key("a", 1, "en"), b"page")
    with django_capture_on_commit_callbacks(execute=True):
        out = run("website.site.unpublish")
    assert (out.published_version, out.is_live) == (1, False)
    assert cache.get(page_cache_key("a", 1, "en")) is None
    assert len(events("website.site.unpublished")) == 1
    # Already offline: nothing to do, nothing recorded.
    run("website.site.unpublish")
    assert len(events("website.site.unpublished")) == 1
    assert run("website.site.publish").published_version == 2


def test_only_who_manages_the_website_takes_it_offline():
    run("website.site.publish")
    with pytest.raises(PermissionDenied):
        run("website.site.unpublish", ctx=ctx_for("hub_manager"))


# Images


def test_image_upload_stores_a_content_hashed_key_in_hub_files(hub_files):
    raw = png_bytes(4, 3)
    image = upload(raw)
    hub = Hub.objects.get(slug="a")
    sha = hashlib.sha256(raw).hexdigest()
    key = f"hub-{hub.id.hex}/website/img/{sha[:16]}.png"
    assert hub_files.exists(key)
    with hub_files.open(key) as stored:
        assert stored.read() == raw
    assert image.url == f"/p/media/{hub.id.hex}/website/img/{sha[:16]}.png"
    assert (image.width, image.height, image.size, image.content_type) == (4, 3, len(raw), "image/png")
    row = Image.objects.get(id=image.id)
    assert (row.key, row.sha256) == (key, sha)
    assert [event.payload for event in events("website.image.uploaded")] == [{"id": str(image.id)}]


def test_an_upload_belongs_to_its_hub(hub_files):
    raw = png_bytes()
    a_image, b_image = upload(raw, ctx=ctx_for(scope=A)), upload(raw, ctx=ctx_for(scope=B))
    assert a_image.id != b_image.id
    assert Image.objects.get(id=a_image.id).hub_id == Hub.objects.get(slug="a").id
    assert Image.objects.get(id=b_image.id).hub_id == Hub.objects.get(slug="b").id
    # The same file on each hub: each saves it with its own upload, never the other's.
    save(full_content(hero={"cover": {"id": str(b_image.id), "url": ""}}), ctx=ctx_for(scope=B))
    with pytest.raises(InvalidPayload) as refused:
        save(full_content(hero={"cover": {"id": str(b_image.id), "url": ""}}), ctx=ctx_for(scope=A))
    assert set(refused.value.fields) == {"content.hero.cover"}


def test_the_same_image_twice_is_one_file_and_one_row(hub_files):
    raw = png_bytes()
    assert upload(raw).id == upload(raw).id
    assert Image.objects.count() == 1


@pytest.mark.parametrize(
    "raw,content_type",
    [
        (b"not an image at all", "image/png"),
        (png_bytes(fmt="JPEG"), "image/png"),
        (png_bytes(fmt="GIF"), "image/webp"),
        (b"", "image/png"),
    ],
)
def test_an_upload_that_is_not_an_image_of_its_type_is_refused(hub_files, raw, content_type):
    with pytest.raises(InvalidPayload) as refused:
        upload(raw, content_type=content_type)
    assert set(refused.value.fields) == {"data_base64"}
    assert not Image.objects.exists()


def test_an_upload_that_is_not_base64_is_refused(hub_files):
    with pytest.raises(InvalidPayload):
        run("website.image.upload", {"filename": "x.png", "content_type": "image/png", "data_base64": "@@@"})


def test_an_upload_over_5_mb_is_refused(hub_files):
    # A valid PNG followed by padding: 5 MB and one byte, still under the input's base64 bound.
    raw = png_bytes()
    raw += b"\0" * (5 * 1024 * 1024 + 1 - len(raw))
    with pytest.raises(InvalidPayload) as refused:
        upload(raw)
    assert "5 MB" in refused.value.fields["data_base64"]


def test_an_image_too_large_in_pixels_is_refused(hub_files):
    with pytest.raises(InvalidPayload):
        upload(png_bytes(8001, 1))


def test_only_who_manages_the_website_uploads(hub_files):
    with pytest.raises(PermissionDenied):
        upload(png_bytes(), ctx=ctx_for("hub_manager"))


def test_a_scope_that_is_no_hub_has_nowhere_to_keep_images(hub_files):
    from live.context import Scope

    with pytest.raises(NotFound):
        upload(png_bytes(), ctx=ctx_for(scope=Scope("host", "nohub")))


# Two first saves at once (threads, real transactions)


def _in_thread(target):
    outcome = {}

    def body():
        try:
            outcome["result"] = target()
        except Exception as error:  # the outcome is asserted by the test
            outcome["error"] = error
        finally:
            connection.close()

    thread = threading.Thread(target=body)
    thread.start()
    return thread, outcome


@pytest.mark.django_db(transaction=True)
def test_two_first_saves_at_once_leave_one_site_and_neither_fails(transactional_db):
    # The first save of a hub creates its row: another one at the same moment waits for it and saves after it,
    # never a duplicate key (a 500).
    first_saved, release = threading.Event(), threading.Event()

    def first():
        with transaction.atomic():
            out = save(template="modern")
            first_saved.set()
            release.wait(5)
        return out

    holder, held = _in_thread(first)
    assert first_saved.wait(5)
    waiter, second = _in_thread(lambda: save(template="bold"))
    waiter.join(0.3)
    waited = waiter.is_alive()
    release.set()
    holder.join(5)
    waiter.join(5)
    assert "result" in held, held
    assert "result" in second, second
    assert waited, "the second save did not wait for the first one's row"
    assert Site.objects.count() == 1
    assert hub_site("a").template == "bold"
