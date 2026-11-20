"""The website's tables: the business's one site (the draft and what is published) and the images uploaded for it."""

import pytest
from django.db import IntegrityError
from live.operations import atomic

from apps.website.models import Image, Site
from apps.website.tests.conftest import HUB_DB

pytestmark = HUB_DB


def test_a_new_site_starts_classic_never_published_and_offline():
    site = Site.objects.create()
    assert site.id.version == 7
    assert (site.template, site.theme, site.content, site.published_content) == ("classic", {}, {}, {})
    assert (site.published_version, site.published_at, site.is_live) == (0, None, False)
    assert site.updated_by == ""
    # Google's reviews of its place: none read yet.
    assert site.reviews_snapshot == {}


def test_the_business_database_holds_one_site_at_most():
    Site.objects.create()
    with pytest.raises(IntegrityError), atomic():
        Site.objects.create()
    assert Site.objects.count() == 1
    assert Site._meta.get_field("singleton").editable is False


def test_the_site_and_its_images_name_no_business():
    # The database is the business's: no row says whose it is.
    assert "hub_id" not in {field.name for field in Site._meta.get_fields()}
    assert "hub_id" not in {field.name for field in Image._meta.get_fields()}


def test_the_template_is_one_of_the_four():
    assert [value for value, _label in Site.Template.choices] == ["classic", "modern", "minimal", "bold"]
    with pytest.raises(IntegrityError), atomic():
        Site.objects.create(template="fancy")


def test_an_image_keeps_its_key_hash_and_size_and_a_key_is_stored_once():
    image = Image.objects.create(
        key="hub-0123/website/img/abcdef0123456789.png",
        sha256="a" * 64,
        content_type="image/png",
        width=10,
        height=20,
        size=1234,
    )
    assert image.id.version == 7
    assert image.created_at is not None
    with pytest.raises(IntegrityError), atomic():
        Image.objects.create(key=image.key, sha256="a" * 64, content_type="image/png", width=1, height=1, size=1)
