"""What of Website travels in an export of the business (BASE-F35): the page as it is being edited (its design, its
colours and what each section says) with its own images inside the file and the categories of its catalog by name, so
that loading the file in a new business brings the page back as a draft to publish. What visitors see (the published
version) and what Google said of the reviews never travel: the page arrives unpublished and Google is asked again.

A business that never saved its page has none of its own: nothing travels and nothing counts, so a new business is still
offered a template. A page the business saved is its own: a file never overwrites it.

Every test runs against the real apps, in business A's own database, as production does.
"""

import base64
import io
import uuid

from django.apps import apps
from PIL import Image as PILImage

from apps.website.models import Image, Site
from apps.website.tests.conftest import HUB_DB, PLACE_ID, full_content, google_reviews, in_business_a
from apps.website.tests.test_services import png_bytes, upload
from base import blueprint
from base.blueprint.calls import STAYS_HOOK
from base.blueprint.export import counts
from base.tests.blueprint_round_trip import app_report, call, ctx, data_of, exported, loaded_back

__all__ = ["ctx", "in_business_a"]
pytestmark = HUB_DB

IMAGE_FIELDS = (("topbar", "logo"), ("hero", "cover"), ("about", "image"))
THEME = {"palette": "forest", "custom": {"primary": "#aa0000", "accent": "#112233"}, "mode": "dark"}


def our_catalog(ctx) -> uuid.UUID:
    """Two categories of Services; the id of «Hair», the one the page's catalog shows."""
    hair = call(ctx, "service.category.create", name="Hair")
    call(ctx, "service.category.create", name="Nails")
    return hair.id


def our_page(ctx, hair: uuid.UUID) -> dict[str, uuid.UUID]:
    """A page saved with a logo, a cover, a photo beside «About us» that the gallery shows too, and a catalog of «Hair»;
    the ids of its images, by the name of their file."""
    logo = upload(png_bytes(40, 20, colour=(10, 20, 30)), filename="logo.png")
    cover = upload(png_bytes(64, 48, colour=(40, 50, 60), fmt="JPEG"), content_type="image/jpeg", filename="cover.jpg")
    terrace = upload(png_bytes(30, 30, colour=(70, 80, 90)), filename="terrace.png")
    room = upload(png_bytes(24, 36, colour=(100, 110, 120)), filename="dining-room.png")
    content = full_content(
        topbar={"logo": {"id": str(logo.id)}},
        hero={"cover": {"id": str(cover.id)}},
        about={"image": {"id": str(terrace.id)}},
        catalog={"source": "service", "category_ids": [str(hair)]},
        gallery={"images": [{"id": str(room.id)}, {"id": str(terrace.id)}]},
        reviews={"place_ref": PLACE_ID},
    )
    call(ctx, "website.site.save", template="modern", theme=THEME, content=content)
    return {"logo.png": logo.id, "cover.jpg": cover.id, "terrace.png": terrace.id, "dining-room.png": room.id}


def _named(ref: dict | None) -> str | None:
    return ref["name"] if ref else None


def the_page(ctx) -> dict:
    """The page as the business reads it: its design, its colours and its content, each image by the name of its file
    and each category of its catalog by its name, without ids or addresses."""
    site = call(ctx, "website.site.get")
    content = site.content.model_dump(mode="json")
    for section, field in IMAGE_FIELDS:
        content[section][field] = _named(content[section][field])
    content["gallery"]["images"] = [_named(ref) for ref in content["gallery"]["images"]]
    categories = {str(row.id): row.name for row in call(ctx, "website.catalog.categories", source="service").categories}
    content["catalog"]["category_ids"] = [categories.get(pk, pk) for pk in content["catalog"]["category_ids"]]
    return {"template": site.template, "theme": site.theme.model_dump(mode="json"), "content": content}


def born_again(ctx) -> None:
    """The business as a new one is born: no page saved, no image of it and no category of Services."""
    Site.objects.all().delete()
    Image.objects.all().delete()
    for row in call(ctx, "service.category.list", limit=100).rows:
        call(ctx, "service.category.delete", id=row.id)


def site_part(report: dict) -> dict:
    return next(part for part in app_report(report, "website")["datasets"] if part["key"] == "website.site")


def kind_and_size(raw: bytes) -> tuple[str, tuple[int, int]]:
    with PILImage.open(io.BytesIO(raw)) as image:
        return image.format, image.size


def without_media(file: str, name: str) -> str:
    """``file`` with the image ``name`` taken out of it, as a file changed by hand would be."""
    bundle = blueprint.archive.read_base64(file)
    del bundle.media[name]
    return base64.b64encode(blueprint.archive.write_zip(bundle)).decode("ascii")


def test_the_page_travels_in_one_part_that_carries_the_site_and_its_images():
    parts = blueprint.datasets.datasets_of("website")

    assert [(part.key, part.models, part.personal) for part in parts] == [("website.site", ("Site", "Image"), False)]
    assert "pending" not in dict(getattr(apps.get_app_config("website"), STAYS_HOOK, {})).values()


def test_export_lists_the_page_among_what_travels(ctx):
    listed = {app.id: app for app in call(ctx, "base.dataset.list").apps}

    assert [part.key for part in listed["website"].datasets] == ["website.site"]


def test_a_backup_brings_the_page_back_to_a_new_business_as_a_draft_with_its_images_and_its_catalog(ctx, hub_files):
    our_page(ctx, our_catalog(ctx))
    call(ctx, "website.site.publish")
    Site.objects.update(reviews_snapshot=google_reviews())
    before = the_page(ctx)
    file = exported(ctx, ["website", "service"])
    born_again(ctx)

    report = loaded_back(ctx, file)

    assert the_page(ctx) == before
    site = Site.objects.get()
    assert (site.published_version, site.is_live, site.published_content, site.reviews_snapshot) == (0, False, {}, {})
    assert sorted((image.filename, image.content_type) for image in Image.objects.all()) == [
        ("cover.jpg", "image/webp"), ("dining-room.png", "image/webp"), ("logo.png", "image/webp"),
        ("terrace.png", "image/webp"),
    ]  # fmt: skip
    assert (site_part(report)["created"], site_part(report)["already"], site_part(report)["problems"]) == (1, 0, [])


def test_the_file_carries_each_image_inside_as_a_webp_and_each_category_by_its_name(ctx, hub_files):
    ids = our_page(ctx, our_catalog(ctx))

    bundle = blueprint.archive.read_base64(exported(ctx, ["website"]))

    [row] = bundle.data["website.site"]
    content = row["content"]
    assert (row["template"], row["theme"]) == ("modern", THEME)
    assert content["topbar"]["logo"] == {"file": f"website/img/{ids['logo.png'].hex}.webp", "name": "logo.png"}
    assert [ref["name"] for ref in content["gallery"]["images"]] == ["dining-room.png", "terrace.png"]
    assert (content["catalog"]["categories"], "category_ids" in content["catalog"]) == (["Hair"], False)
    assert sorted(bundle.media) == sorted(f"website/img/{pk.hex}.webp" for pk in ids.values())
    assert kind_and_size(bundle.media[f"website/img/{ids['dining-room.png'].hex}.webp"]) == ("WEBP", (24, 36))


def test_a_business_that_never_saved_its_page_has_nothing_of_it_to_carry_or_count(ctx):
    assert counts(ctx)["website.site"] == 0
    assert "website.site" not in data_of(ctx, ["website"])


def test_a_page_the_business_saved_counts_as_its_own(ctx):
    call(ctx, "website.site.save", template="classic", theme={}, content=full_content())

    assert counts(ctx)["website.site"] == 1


def test_loading_the_file_again_keeps_the_page_the_business_saved(ctx, hub_files):
    our_page(ctx, our_catalog(ctx))
    file = exported(ctx, ["website"])
    call(ctx, "website.site.save", template="bold", theme={}, content=full_content(hero={"title": "Our own page"}))
    before = the_page(ctx)

    report = loaded_back(ctx, file)

    assert the_page(ctx) == before
    assert (site_part(report)["created"], site_part(report)["already"]) == (0, 1)


def test_a_category_the_loading_business_does_not_have_is_left_out_and_told(ctx, hub_files):
    our_page(ctx, our_catalog(ctx))
    file = exported(ctx, ["website"])
    born_again(ctx)
    call(ctx, "service.category.create", name="Nails")

    report = loaded_back(ctx, file)

    assert the_page(ctx)["content"]["catalog"]["category_ids"] == []
    assert site_part(report)["created"] == 1
    assert [problem for problem in site_part(report)["problems"] if "«Hair»" in problem] == site_part(report)["problems"]
    assert len(site_part(report)["problems"]) == 1


def test_an_image_the_file_does_not_carry_is_left_out_and_told(ctx, hub_files):
    ids = our_page(ctx, our_catalog(ctx))
    file = without_media(exported(ctx, ["website", "service"]), f"website/img/{ids['terrace.png'].hex}.webp")
    born_again(ctx)

    report = loaded_back(ctx, file)

    page = the_page(ctx)["content"]
    assert (page["about"]["image"], page["gallery"]["images"]) == (None, ["dining-room.png"])
    assert page["topbar"]["logo"] == "logo.png"
    assert site_part(report)["created"] == 1
    assert len(site_part(report)["problems"]) == 1 and "terrace.png" in site_part(report)["problems"][0]


def test_an_image_whose_file_the_store_lost_stays_out_of_the_file_and_its_load_says_so(ctx, hub_files):
    ids = our_page(ctx, our_catalog(ctx))
    hub_files.delete(Image.objects.get(id=ids["terrace.png"]).key)

    file = exported(ctx, ["website", "service"])

    kept = sorted(f"website/img/{pk.hex}.webp" for name, pk in ids.items() if name != "terrace.png")
    assert sorted(blueprint.archive.read_base64(file).media) == kept
    born_again(ctx)
    report = loaded_back(ctx, file)
    assert the_page(ctx)["content"]["gallery"]["images"] == ["dining-room.png"]
    assert len(site_part(report)["problems"]) == 1 and "terrace.png" in site_part(report)["problems"][0]


def test_a_page_the_business_would_not_save_is_refused_and_told_by_its_name(ctx, hub_files):
    our_page(ctx, our_catalog(ctx))
    bundle = blueprint.archive.read_base64(exported(ctx, ["website", "service"]))
    bundle.data["website.site"][0]["template"] = "no-such-template"
    born_again(ctx)

    report = loaded_back(ctx, base64.b64encode(blueprint.archive.write_zip(bundle)).decode("ascii"))

    assert counts(ctx)["website.site"] == 0
    assert site_part(report)["created"] == 0
    assert len(site_part(report)["problems"]) == 1 and "Design, texts and images" in site_part(report)["problems"][0]


def test_a_load_leaves_the_rows_it_is_given_as_they_were(ctx, hub_files):
    """A template's rows are read once per process and loaded into every business that picks it: loading the same rows
    again brings the page back again, with its images."""
    our_page(ctx, our_catalog(ctx))
    before = the_page(ctx)
    bundle = blueprint.archive.read_base64(exported(ctx, ["website", "service"]))

    for _ in range(2):
        born_again(ctx)
        blueprint.loading.apply(ctx, bundle, apps=None)
        assert the_page(ctx) == before
