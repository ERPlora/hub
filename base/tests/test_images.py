"""The image of a row an app sells (round 2026-10-30): ``base.images``, what Inventory, Services and Combos share.

A product, a service or a set menu keeps one reference: ``catalog:<folder>/<name>`` (an image of the shared library,
``base.image_catalog``), ``file:<app>/<folder>/<uuid7 hex>.webp`` (a photo of its own, under its hub's prefix of the
hub file store, served by ``/p/media/`` to the hub's sessions) or nothing. A photo of its own comes in as a JPG, PNG or
WebP of 2 MB at most and is kept as a WebP of 512 × 512 (the middle of it, cropped to a square, quality 85), counted
against the plan's space; a WebP that already is one is kept as it came. A reference is never a URL: the URL is made
when the row is read.
"""

import base64
import io
import re
import uuid

import pytest
from django.core.files.storage import storages
from live.context import OperationContext, Scope
from live.errors import Conflict, InvalidPayload, OperationError
from PIL import Image as PILImage

from base import files, images
from base.models import Hub
from base.storage import hub_prefix
from base.tests.test_image_catalog import image_library, webp  # noqa: F401 - the library fixture

pytestmark = pytest.mark.django_db

A = Scope("host", "a")
FOLDER = "inventory/products/"


@pytest.fixture
def hub_files(settings):
    """``storages["hub_files"]`` in memory, empty for each test."""
    settings.STORAGES = {**settings.STORAGES, "hub_files": {"BACKEND": "django.core.files.storage.InMemoryStorage"}}
    storages._storages.pop("hub_files", None)
    yield storages["hub_files"]
    storages._storages.pop("hub_files", None)


def ctx(language: str = "en") -> OperationContext:
    return OperationContext(scope=A, actor="ana", permissions=frozenset(), language=language)


def picture(fmt: str = "PNG", size: tuple[int, int] = (800, 600), mode: str = "RGB", **save) -> bytes:
    """A picture whose left third is red, middle third green and right third blue."""
    image = PILImage.new(mode, size, "green")
    third = size[0] // 3
    image.paste("red", (0, 0, third, size[1]))
    image.paste("blue", (size[0] - third, 0, size[0], size[1]))
    buffer = io.BytesIO()
    image.save(buffer, fmt, **save)
    return buffer.getvalue()


def opened(raw: bytes) -> PILImage.Image:
    image = PILImage.open(io.BytesIO(raw))
    image.load()
    return image


def hub_a() -> uuid.UUID:
    return Hub.objects.get(slug="a").id


# ── References ──────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("reference", "kind"),
    [
        ("", images.NONE),
        ("catalog:hospitality/cafe_solo", images.CATALOG),
        (f"file:{FOLDER}0193a1b2c3d47e8f9a0b1c2d3e4f5a6b.webp", images.FILE),
        ("file:inventory/products/x.webp", None),
        ("file:../hub-b/inventory/products/0193a1b2c3d47e8f9a0b1c2d3e4f5a6b.webp", None),
        ("https://cdn.example.com/x.webp", None),
        ("/p/catalog/hospitality/cafe_solo.webp", None),
    ],
)
def test_a_reference_is_an_image_of_the_library_a_photo_of_its_own_or_nothing(reference, kind):
    assert images.kind_of(reference) == kind


def test_the_url_of_an_image_of_the_library_is_the_hubs_route_to_it():
    assert images.Urls(A)("catalog:hospitality/cafe_solo") == "/p/catalog/hospitality/cafe_solo.webp"


def test_the_url_of_a_photo_of_its_own_is_its_hubs_media_route():
    name = f"{FOLDER}0193a1b2c3d47e8f9a0b1c2d3e4f5a6b.webp"

    assert images.Urls(A)(f"file:{name}") == f"/p/media/{hub_a().hex}/{name}"


def test_no_image_has_no_url_and_neither_has_a_reference_that_is_none():
    urls = images.Urls(A)

    assert (urls(""), urls("https://cdn.example.com/x.webp")) == ("", "")


def test_the_hub_is_read_once_and_only_for_a_photo_of_its_own(monkeypatch):
    reads = []
    real = images.hub_id
    monkeypatch.setattr(images, "hub_id", lambda scope: reads.append(scope) or real(scope))
    urls = images.Urls(A)

    urls("catalog:hospitality/cafe_solo")
    assert reads == []
    urls(f"file:{FOLDER}0193a1b2c3d47e8f9a0b1c2d3e4f5a6b.webp")
    urls(f"file:{FOLDER}0193a1b2c3d47e8f9a0b1c2d3e4f5a6c.webp")
    assert reads == [A]


# ── What a row may point at ─────────────────────────────────────────────────────────────────────────────────────


def test_an_image_the_library_has_may_be_set(image_library):  # noqa: F811
    images.check(ctx(), "catalog:hospitality/cafe_solo")


def test_nothing_may_be_set(image_library):  # noqa: F811
    images.check(ctx(), "")


def test_an_image_the_library_does_not_have_is_refused(image_library):  # noqa: F811
    with pytest.raises(InvalidPayload) as refused:
        images.check(ctx("es"), "catalog:hospitality/churros")

    assert (refused.value.code, refused.value.fields) == (
        "base.image_unknown",
        {"image": "Esa imagen ya no está en la librería. Elige otra."},
    )


@pytest.mark.parametrize(
    "reference",
    [
        # A photo of its own is written only by its upload: by hand, no row points at another's file.
        f"file:{FOLDER}0193a1b2c3d47e8f9a0b1c2d3e4f5a6b.webp",
        "https://cdn.example.com/x.webp",
        "/p/catalog/hospitality/cafe_solo.webp",
        "cafe_solo",
    ],
)
def test_what_is_no_image_of_the_library_is_refused(image_library, reference):  # noqa: F811
    with pytest.raises(InvalidPayload) as refused:
        images.check(ctx(), reference, field="photo")

    assert (refused.value.code, refused.value.fields) == (
        "base.image_unknown",
        {"photo": "Choose an image of the library or upload a photo."},
    )


# ── A photo of its own: what comes in ───────────────────────────────────────────────────────────────────────────


def test_a_photo_is_sent_in_base64():
    assert images.decode(base64.b64encode(b"bytes").decode()) == b"bytes"


@pytest.mark.parametrize("sent", ["", "not base64!", "QUJD="])
def test_what_is_no_base64_is_refused(sent):
    with pytest.raises(InvalidPayload) as refused:
        images.decode(sent)

    assert (refused.value.code, set(refused.value.fields)) == ("base.photo_invalid", {"data_base64"})


def test_a_photo_past_2_mb_is_refused_and_one_of_2_mb_is_taken():
    assert len(images.decode(base64.b64encode(b"\0" * images.MAX_UPLOAD_BYTES).decode())) == images.MAX_UPLOAD_BYTES

    with pytest.raises(InvalidPayload) as refused:
        images.decode(base64.b64encode(b"\0" * (images.MAX_UPLOAD_BYTES + 1)).decode())

    assert refused.value.code == "base.photo_too_big"
    assert refused.value.message == "The photo weighs more than 2 MB. Choose a lighter one."


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_a_photo_becomes_a_webp_of_512_by_512_cut_from_its_middle(fmt):
    kept = opened(images.to_webp(picture(fmt, (900, 300))))

    assert (kept.format, kept.size) == ("WEBP", (images.SIDE, images.SIDE))
    # A 900 × 300 picture keeps its middle 300 × 300: the green third, none of the red or the blue.
    red, green, blue = kept.convert("RGB").getpixel((256, 256))
    assert green > 100 and red < 60 and blue < 60
    assert kept.convert("RGB").getpixel((5, 256))[1] > 100


def test_a_tall_photo_keeps_its_middle_too():
    kept = opened(images.to_webp(picture("PNG", (300, 900))))

    assert kept.size == (images.SIDE, images.SIDE)


def test_a_phone_photo_is_turned_upright():
    # 400 × 300, its left half red: the camera held sideways (EXIF orientation 6, turn it 90° clockwise to see it).
    image = PILImage.new("RGB", (400, 300), "green")
    image.paste("red", (0, 0, 200, 300))
    exif = PILImage.Exif()
    exif[0x0112] = 6
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", exif=exif)

    kept = opened(images.to_webp(buffer.getvalue())).convert("RGB")

    # Upright it is 300 × 400 with its red half on top: red top right, green bottom left (sideways, the opposite).
    assert kept.getpixel((450, 5))[0] > 150 and kept.getpixel((450, 5))[1] < 80
    assert kept.getpixel((5, 450))[1] > 100 and kept.getpixel((5, 450))[0] < 60


def test_a_webp_of_512_by_512_without_metadata_is_kept_as_it_came():
    raw = picture("WEBP", (512, 512), quality=60)

    assert images.to_webp(raw) == raw


def test_what_a_photo_says_of_where_it_was_taken_is_dropped():
    exif = PILImage.Exif()
    exif[0x010F] = "The camera's maker"
    raw = picture("WEBP", (512, 512), exif=exif)

    kept = opened(images.to_webp(raw))

    assert "exif" not in kept.info


def test_a_transparent_png_stays_transparent():
    raw = picture("PNG", (600, 600), mode="RGBA")
    image = PILImage.open(io.BytesIO(raw)).convert("RGBA")
    image.putpixel((0, 0), (0, 0, 0, 0))
    buffer = io.BytesIO()
    image.save(buffer, "PNG")

    assert opened(images.to_webp(buffer.getvalue())).mode == "RGBA"


@pytest.mark.parametrize("raw", [b"not an image at all", b"GIF89a" + b"\0" * 20, b"\x89PNG\r\n\x1a\n" + b"\0" * 50])
def test_what_is_no_jpg_png_or_webp_is_refused(raw):
    with pytest.raises(InvalidPayload) as refused:
        images.to_webp(raw)

    assert (refused.value.code, set(refused.value.fields)) == ("base.photo_invalid", {"data_base64"})


def test_a_gif_is_refused_even_when_pillow_reads_it():
    with pytest.raises(InvalidPayload):
        images.to_webp(picture("GIF", (100, 100)))


def test_a_photo_with_too_many_pixels_is_refused_before_it_is_decoded():
    raw = picture("PNG", (images.MAX_SIDE + 1, 10))

    with pytest.raises(InvalidPayload) as refused:
        images.to_webp(raw)

    assert refused.value.code == "base.photo_invalid"


def test_the_refusals_are_said_in_the_persons_language():
    with pytest.raises(InvalidPayload) as english:
        images.to_webp(b"text", language="en")
    with pytest.raises(InvalidPayload) as spanish:
        images.to_webp(b"text", language="es")

    assert english.value.message == "That file is not a photo. Upload a JPG, PNG or WebP image."
    assert spanish.value.message == "Ese archivo no es una foto. Sube una imagen JPG, PNG o WebP."


# ── A photo of its own: where it is kept ────────────────────────────────────────────────────────────────────────


def test_a_photo_is_kept_under_its_hubs_prefix_in_the_apps_folder_by_a_new_uuid7(hub_files):
    reference = images.keep_photo(ctx(), FOLDER, webp())

    match = re.fullmatch(rf"file:{FOLDER}([0-9a-f]{{32}})\.webp", reference)
    assert match and uuid.UUID(match.group(1)).version == 7
    assert hub_files.open(f"{hub_prefix(hub_a())}/{reference.removeprefix('file:')}").read() == webp()


def test_the_same_photo_twice_is_two_files(hub_files):
    assert images.keep_photo(ctx(), FOLDER, webp()) != images.keep_photo(ctx(), FOLDER, webp())


def test_a_photo_past_the_plans_space_is_refused_and_not_kept(hub_files):
    Hub.objects.filter(slug="a").update(state={"plan": {"max_storage_bytes": len(webp()) - 1}})

    with pytest.raises(Conflict) as refused:
        images.keep_photo(ctx(), FOLDER, webp())

    assert refused.value.code == "base.file_no_space"
    assert files.used_bytes(hub_files, hub_a()) == 0


def test_a_store_that_does_not_answer_says_the_photo_could_not_be_saved(hub_files, monkeypatch):
    def broken(name, content, max_length=None):
        raise OSError("the bucket did not answer")

    monkeypatch.setattr(hub_files, "save", broken)

    with pytest.raises(OperationError) as refused:
        images.keep_photo(ctx("es"), FOLDER, webp())

    assert (refused.value.status, refused.value.code) == (503, "base.photo_not_saved")
    assert refused.value.message == "No se pudo guardar la foto. Inténtalo de nuevo."


def test_a_photo_let_go_is_deleted_once_the_change_is_saved(hub_files, django_capture_on_commit_callbacks):
    reference = images.keep_photo(ctx(), FOLDER, webp())
    key = f"{hub_prefix(hub_a())}/{reference.removeprefix('file:')}"

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        images.let_go(ctx(), reference)
        assert hub_files.exists(key)

    assert len(callbacks) == 1
    assert not hub_files.exists(key)


def test_letting_go_an_image_of_the_library_or_nothing_deletes_nothing(django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks() as callbacks:
        images.let_go(ctx(), "catalog:hospitality/cafe_solo")
        images.let_go(ctx(), "")

    assert callbacks == []


def test_a_photo_of_its_own_is_read_back_for_a_blueprint(hub_files):
    reference = images.keep_photo(ctx(), FOLDER, webp("blue"))

    assert images.read_photo(A, reference) == webp("blue")
    assert images.read_photo(A, f"file:{FOLDER}{uuid.uuid7().hex}.webp") is None
