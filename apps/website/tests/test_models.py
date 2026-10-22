"""The website's tables: one site per hub (the draft and what is published) and the images uploaded for it."""

import uuid

import pytest
from django.db import IntegrityError, transaction

from apps.website.models import Image, Site

pytestmark = pytest.mark.django_db


def test_a_new_site_starts_classic_never_published_and_offline():
    site = Site.objects.create(hub_id=uuid.uuid7())
    assert site.id.version == 7
    assert (site.template, site.theme, site.content, site.published_content) == ("classic", {}, {}, {})
    assert (site.published_version, site.published_at, site.is_live) == (0, None, False)
    assert site.updated_by == ""
    # Google's reviews of its place: none read yet.
    assert site.reviews_snapshot == {}


def test_each_hub_has_one_site_at_most():
    # Phase 1: the tables are shared by every hub until phase 2 moves them to each hub's database (WORKBOOK): the
    # row names its hub, and a hub has one row.
    a, b = uuid.uuid7(), uuid.uuid7()
    Site.objects.create(hub_id=a)
    Site.objects.create(hub_id=b)
    with pytest.raises(IntegrityError), transaction.atomic():
        Site.objects.create(hub_id=a)
    assert Site.objects.count() == 2


def test_a_site_always_names_its_hub_and_it_never_changes_by_hand():
    with pytest.raises(IntegrityError), transaction.atomic():
        Site.objects.create()
    assert Site._meta.get_field("hub_id").editable is False


def test_the_template_is_one_of_the_four():
    assert [value for value, _label in Site.Template.choices] == ["classic", "modern", "minimal", "bold"]
    with pytest.raises(IntegrityError), transaction.atomic():
        Site.objects.create(hub_id=uuid.uuid7(), template="fancy")


def test_an_image_keeps_its_hub_key_hash_and_size_and_a_key_is_stored_once():
    hub = uuid.uuid7()
    image = Image.objects.create(
        hub_id=hub,
        key="hub-0123/website/img/abcdef0123456789.png",
        sha256="a" * 64,
        content_type="image/png",
        width=10,
        height=20,
        size=1234,
    )
    assert image.id.version == 7
    assert image.created_at is not None
    assert Image.objects.get(id=image.id).hub_id == hub
    # The uploads of a hub are looked up by its id.
    assert Image._meta.get_field("hub_id").db_index and Image._meta.get_field("hub_id").editable is False
    with pytest.raises(IntegrityError), transaction.atomic():
        Image.objects.create(
            hub_id=hub, key=image.key, sha256="a" * 64, content_type="image/png", width=1, height=1, size=1
        )
