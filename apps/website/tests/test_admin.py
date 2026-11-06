"""Django admin of the website app, read-mostly (round 12, PLAN §17): the staff on hubs.erplora.com see the site and
its images and can only take a site offline (``is_live``); its content goes through the editor's operations, which
validate it and write its images' URLs."""

import uuid

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.website.admin import ImageAdmin, SiteAdmin
from apps.website.models import Image, Site

MODELS = {Site: SiteAdmin, Image: ImageAdmin}


@pytest.fixture
def superuser(db):
    return get_user_model().objects.create_superuser(username="root", password="pw", email="root@example.com")


def request_by(user):
    request = RequestFactory().get("/admin/")
    request.user = user
    return request


def test_every_admin_passes_the_django_checks():
    for model in MODELS:
        assert admin.site._registry[model].check() == [], model


def test_every_model_is_registered():
    for model, model_admin in MODELS.items():
        assert isinstance(admin.site._registry[model], model_admin), model


def test_nothing_is_added_or_deleted_from_the_admin(superuser):
    request = request_by(superuser)
    for model in MODELS:
        model_admin = admin.site._registry[model]
        assert model_admin.has_view_permission(request), model
        assert not model_admin.has_add_permission(request), model
        assert not model_admin.has_delete_permission(request), model


@pytest.mark.django_db
def test_only_whether_the_site_is_live_can_change(superuser):
    site = Site.objects.create(hub_id=uuid.uuid7())
    request = request_by(superuser)
    site_admin = admin.site._registry[Site]
    assert site_admin.has_change_permission(request, site)
    concrete = {field.name for field in Site._meta.get_fields() if field.concrete}
    assert set(site_admin.get_readonly_fields(request, site)) == concrete - {"is_live"}
    image_admin = admin.site._registry[Image]
    assert not image_admin.has_change_permission(request)


def test_the_staff_see_whose_hub_each_row_is():
    # Phase 1: every hub's rows share the tables, so the list says which hub each one belongs to.
    for model in MODELS:
        model_admin = admin.site._registry[model]
        assert "hub_id" in model_admin.list_display and "hub_id" in model_admin.fields, model


@pytest.mark.django_db
def test_the_admin_in_spanish_says_the_websites_own_words(client, superuser):
    """The staff read the site and its images in Página web's words (hub#661): the site is «Página web» and feminine
    («Actualizada el», «Actualizada por», like its «Publicada el»), an image «Creada el»; not Clientes' «Web» nor Demo's
    and Clientes' masculine."""
    site = Site.objects.create(hub_id=uuid.uuid7(), updated_by="ana")
    Image.objects.create(
        hub_id=site.hub_id, key="a/logo.png", sha256="0" * 64, content_type="image/png", width=1, height=1, size=1
    )
    client.force_login(superuser)
    spanish = {"HTTP_HOST": "hubs.localhost", "HTTP_ACCEPT_LANGUAGE": "es"}
    change = client.get(f"/admin/website/site/{site.pk}/change/", **spanish)
    images = client.get("/admin/website/image/", **spanish)
    assert (change.status_code, images.status_code) == (200, 200)
    page, listing = change.content.decode(), images.content.decode()
    assert "<label>Publicada el:</label>" in page  # the page is in Spanish: a label the site already says alone
    assert "<label>Actualizada el:</label>" in page and "<label>Actualizada por:</label>" in page
    assert "&rsaquo; Página web" in page  # the breadcrumb names the site
    assert ">Creada el</a>" in listing  # the images' column
    assert "Actualizado" not in page and "&rsaquo; Web\n" not in page and "Creado el" not in listing
