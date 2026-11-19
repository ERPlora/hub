"""Where the website keeps its images in the hub file store: under the hub's prefix, in its own folder."""

import uuid

import pytest
from django.apps import apps

from apps.website.storage import FOLDER, image_url

HUB = uuid.UUID("0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b")
KEY = f"hub-{HUB.hex}/website/img/0123456789abcdef.png"


def test_its_images_go_to_the_folder_it_serves_to_anyone():
    assert FOLDER == "website/img/"
    assert apps.get_app_config("website").public_media == [FOLDER]


def test_its_url_is_the_hub_media_view_of_the_key_under_the_prefix():
    assert image_url(HUB, KEY) == f"/p/media/{HUB.hex}/website/img/0123456789abcdef.png"


def test_a_key_of_another_hub_has_no_url_here():
    with pytest.raises(ValueError):
        image_url(HUB, KEY.replace(HUB.hex, uuid.uuid4().hex))
