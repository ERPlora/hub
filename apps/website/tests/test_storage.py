"""Where the website keeps its images in the hub file store: under the hub's prefix, named by their content."""

import uuid

import pytest

from apps.website.storage import EXTENSIONS, image_key, image_url

HUB = uuid.UUID("0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b")
SHA = "0123456789abcdef" + "f" * 48


def test_an_image_is_keyed_by_its_hub_and_the_first_16_hex_of_its_sha256():
    assert image_key(HUB, SHA, "image/png") == f"hub-{HUB.hex}/website/img/0123456789abcdef.png"
    assert image_key(HUB, SHA, "image/jpeg").endswith("/0123456789abcdef.jpg")
    assert image_key(HUB, SHA, "image/webp").endswith("/0123456789abcdef.webp")
    assert EXTENSIONS == {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def test_its_url_is_the_hub_media_view_of_the_key_under_the_prefix():
    key = image_key(HUB, SHA, "image/png")
    assert image_url(HUB, key) == f"/p/media/{HUB.hex}/website/img/0123456789abcdef.png"


def test_a_key_of_another_hub_has_no_url_here():
    other = image_key(uuid.uuid4(), SHA, "image/png")
    with pytest.raises(ValueError):
        image_url(HUB, other)


def test_a_type_the_website_does_not_take_has_no_key():
    with pytest.raises(KeyError):
        image_key(HUB, SHA, "image/gif")
