"""An image a business uploads for anyone to see on its own pages (the website's images, the booking page's logo):
``base.public_images``. It comes in base64 as a JPG, PNG or WebP of 5 MB and 8000 pixels a side at most, read whole by
Pillow as the type it claims, and is kept as it came under its hub's prefix, in its app's folder, named by its
content, within the plan's space as Files counts it."""

import base64
import hashlib
import io

from pathlib import Path

import pytest
from django.utils import translation
from live.context import OperationContext, Scope
from live.errors import Conflict, InvalidPayload
from PIL import Image as PILImage
from pydantic import ValidationError

from base import public_images
from base.models import Hub
from base.schemas.public_images import ImageUploadIn
from base.storage import hub_prefix
from base.tests.po import catalogue_key, module_texts, po_entries
from base.tests.test_images import hub_files as hub_files

pytestmark = pytest.mark.django_db

A = Scope("host", "a")
BASE_PO = Path(public_images.__file__).parent / "locale" / "es" / "LC_MESSAGES" / "django.po"
FOLDER = "online_booking/logo/"


def ctx(language: str = "en") -> OperationContext:
    return OperationContext(scope=A, actor="ana", permissions=frozenset(), language=language)


def hub_a():
    return Hub.objects.get(slug="a").id


def picture(fmt: str = "PNG", size: tuple[int, int] = (40, 30)) -> bytes:
    buffer = io.BytesIO()
    PILImage.new("RGB", size, "red").save(buffer, fmt)
    return buffer.getvalue()


def upload_of(raw: bytes, content_type: str = "image/png") -> ImageUploadIn:
    return ImageUploadIn(filename="logo.png", content_type=content_type, data_base64=base64.b64encode(raw).decode())


def test_an_image_is_kept_as_it_came_under_its_hubs_prefix_in_the_folder_named_by_its_content(hub_files):
    raw = picture()
    name = f"{hashlib.sha256(raw).hexdigest()[:16]}.png"

    kept = public_images.keep(ctx(), FOLDER, upload_of(raw))

    assert kept.key == f"{hub_prefix(hub_a())}/{FOLDER}{name}"
    assert kept.name == name
    assert kept.url == f"/p/media/{hub_a().hex}/{FOLDER}{name}"
    assert (kept.sha256, kept.width, kept.height, kept.size) == (hashlib.sha256(raw).hexdigest(), 40, 30, len(raw))
    assert hub_files.open(kept.key).read() == raw


@pytest.mark.parametrize(("fmt", "content_type", "extension"), [("JPEG", "image/jpeg", "jpg"), ("WEBP", "image/webp", "webp")])
def test_each_type_keeps_its_own_extension(hub_files, fmt, content_type, extension):
    assert public_images.keep(ctx(), FOLDER, upload_of(picture(fmt), content_type)).name.endswith(f".{extension}")


def test_the_same_image_again_is_the_same_file_and_takes_no_more_space(hub_files):
    raw = picture()
    first = public_images.keep(ctx(), FOLDER, upload_of(raw))
    Hub.objects.filter(slug="a").update(state={"plan": {"max_storage_bytes": len(raw)}})

    again = public_images.keep(ctx(), FOLDER, upload_of(raw))

    assert again.key == first.key
    assert hub_files.listdir(f"{hub_prefix(hub_a())}/{FOLDER}")[1] == [first.name]


def test_an_image_past_the_plans_space_is_refused_with_files_code_and_not_kept(hub_files):
    raw = picture()
    Hub.objects.filter(slug="a").update(state={"plan": {"max_storage_bytes": len(raw) - 1}})

    with pytest.raises(Conflict) as refused:
        public_images.keep(ctx(), FOLDER, upload_of(raw))

    assert refused.value.code == "base.file_no_space"
    assert not hub_files.exists(f"{hub_prefix(hub_a())}/{FOLDER}{hashlib.sha256(raw).hexdigest()[:16]}.png")


@pytest.mark.parametrize(
    ("data_base64", "content_type"),
    [
        ("not base64!", "image/png"),
        ("", "image/png"),
        (base64.b64encode(picture("JPEG")).decode(), "image/png"),
        (base64.b64encode(b"just text").decode(), "image/webp"),
    ],
    ids=["not-base64", "empty", "another-type", "no-image"],
)
def test_a_file_that_is_no_image_of_its_type_is_refused_on_its_field_and_not_kept(hub_files, data_base64, content_type):
    data = ImageUploadIn(filename="logo.png", content_type=content_type, data_base64=data_base64)

    with pytest.raises(InvalidPayload) as refused:
        public_images.keep(ctx(), FOLDER, data)

    assert set(refused.value.fields) == {"data_base64"}
    assert not hub_files.exists(f"{hub_prefix(hub_a())}/{FOLDER}")


def test_an_image_too_heavy_or_too_large_is_refused_on_its_field(hub_files, monkeypatch):
    with pytest.raises(InvalidPayload) as too_large:
        public_images.keep(ctx(), FOLDER, upload_of(picture(size=(public_images.MAX_SIDE + 1, 1))))
    monkeypatch.setattr(public_images, "MAX_BYTES", 10)
    with pytest.raises(InvalidPayload) as too_heavy:
        public_images.keep(ctx(), FOLDER, upload_of(picture()))

    assert too_large.value.fields == {"data_base64": "The image may be 8000 pixels a side at most."}
    assert too_heavy.value.fields == {"data_base64": "The image may weigh 5 MB at most."}


def test_a_refusal_speaks_the_persons_language(hub_files):
    with translation.override("es"), pytest.raises(InvalidPayload) as refused:
        public_images.keep(ctx("es"), FOLDER, upload_of(picture("JPEG")))

    assert refused.value.fields == {"data_base64": "Este archivo no es una imagen PNG."}


def test_every_refusal_has_its_spanish_in_the_platforms_catalogue():
    with translation.override("en"):
        refusals = {catalogue_key(text) for text in module_texts(public_images)}
    entries = po_entries(BASE_PO)

    assert len(refusals) == 5
    assert {key for key in refusals if not entries.get(key, ("", False))[0] or entries[key][1]} == set()


def test_an_upload_names_one_of_the_three_types_and_a_file_of_5_mb_at_most():
    with pytest.raises(ValidationError):
        ImageUploadIn(filename="logo.gif", content_type="image/gif", data_base64="aGk=")
    with pytest.raises(ValidationError):
        ImageUploadIn(filename="logo.png", content_type="image/png", data_base64="a" * 7_000_001)
    with pytest.raises(ValidationError):
        ImageUploadIn(filename="logo.png", content_type="image/png", data_base64="aGk=", url="https://evil.example")
