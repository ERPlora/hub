"""How a file carries the images of a business's own pages (its website's), which their app keeps as they were uploaded
(a JPG, PNG or WebP of up to 5 MB): as a WebP of at most 2560 pixels a side (WordPress's ceiling for an image of a
page), upright and without the camera's metadata, so that a page with a dozen photos still fits in a file a business
can load again. And how a part whose app keeps its images itself gives them to the file."""

import io

from PIL import Image as PILImage

from base import images
from base.blueprint import photos
from base.blueprint.calls import Dataset

ORIENTATION = 0x0112
#: The camera held sideways: the picture is to be turned 90° clockwise to be seen upright.
SIDEWAYS = 6


def picture(size: tuple[int, int], *, fmt: str = "PNG", mode: str = "RGB", exif: bytes | None = None) -> bytes:
    colour = (200, 30, 30, 120) if mode == "RGBA" else (200, 30, 30)
    buffer = io.BytesIO()
    PILImage.new(mode, size, colour).save(buffer, format=fmt, **({"exif": exif} if exif else {}))
    return buffer.getvalue()


def sideways() -> bytes:
    exif = PILImage.Exif()
    exif[ORIENTATION] = SIDEWAYS
    return exif.tobytes()


def opened(raw: bytes) -> tuple[str, tuple[int, int], str, bool]:
    with PILImage.open(io.BytesIO(raw)) as image:
        return image.format, image.size, image.mode, bool(image.getexif())


def test_a_photo_larger_than_a_file_carries_travels_as_a_webp_of_2560_a_side_with_its_shape():
    assert opened(images.carried(picture((3000, 1500), fmt="JPEG")))[:2] == ("WEBP", (2560, 1280))


def test_a_png_travels_as_a_webp_of_its_own_size():
    assert opened(images.carried(picture((300, 200))))[:2] == ("WEBP", (300, 200))


def test_a_logo_with_transparency_keeps_it():
    assert opened(images.carried(picture((120, 60), mode="RGBA")))[2] == "RGBA"


def test_a_photo_taken_sideways_travels_upright_and_without_the_cameras_metadata():
    assert opened(images.carried(picture((40, 30), fmt="JPEG", exif=sideways()))) == ("WEBP", (30, 40), "RGB", False)


def test_a_webp_a_file_can_carry_travels_as_it_is():
    raw = picture((800, 600), fmt="WEBP")

    assert images.carried(raw) == raw


def test_a_webp_larger_than_a_file_carries_is_made_smaller():
    assert opened(images.carried(picture((3000, 2000), fmt="WEBP")))[:2] == ("WEBP", (2560, 1707))


def test_what_is_no_image_is_not_carried():
    assert images.carried(b"no image") is None


def test_an_image_heavier_than_a_file_takes_even_as_a_webp_is_not_carried(monkeypatch):
    monkeypatch.setattr(images, "MAX_UPLOAD_BYTES", 100)

    assert images.carried(picture((400, 300), fmt="JPEG")) is None


def a_part(key: str, *, media=None, images=None) -> Dataset:
    return Dataset(key=key, label=key, rows=list, count=len, load=print, models=("Row",), media=media, images=images)


def test_a_part_whose_app_keeps_its_images_gives_the_file_those_its_rows_name():
    seen = []

    def own_media(ctx, rows):
        seen.append(rows)
        return {"pages/img/" + row["file"]: b"RIFF" for row in rows}

    parts = [a_part("pages.site", media=own_media), a_part("pages.other", media=own_media)]

    media = photos.export_media(None, {"pages.site": [{"file": "a.webp"}]}, parts)

    assert (media, seen) == ({"pages/img/a.webp": b"RIFF"}, [[{"file": "a.webp"}]])
