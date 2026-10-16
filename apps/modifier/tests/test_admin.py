"""Django admin of the modifier app: full CRUD for support (round 12, PLAN §17).

The Hub admin, on hubs.erplora.com and for the staff only, adds, changes and deletes every table so that
support can repair; it is a second write path that warns rather than prevents, and the database still
refuses what must never be stored.
"""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.modifier.admin import (
    LinkInline,
    ModifierGroupAdmin,
    ModifierLinkAdmin,
    ModifierOptionAdmin,
    OptionInline,
)
from apps.modifier.models import ModifierGroup, ModifierLink, ModifierOption

from .conftest import make_product

MODELS = {
    ModifierGroup: ModifierGroupAdmin,
    ModifierOption: ModifierOptionAdmin,
    ModifierLink: ModifierLinkAdmin,
}


@pytest.fixture
def superuser(db):
    return get_user_model().objects.create_superuser(
        username="root", password="pw", email="root@example.com"
    )


def request_by(user):
    request = RequestFactory().get("/admin/")
    request.user = user
    return request


def test_every_admin_passes_the_django_checks():
    for model in MODELS:
        assert admin.site._registry[model].check() == [], model


def test_every_model_is_registered_and_a_group_shows_its_options_and_links():
    for model, model_admin in MODELS.items():
        assert isinstance(admin.site._registry[model], model_admin), model
    assert ModifierGroupAdmin.inlines == [OptionInline, LinkInline]


def test_full_crud_for_a_superuser(superuser):
    request = request_by(superuser)
    for model in MODELS:
        model_admin = admin.site._registry[model]
        assert model_admin.has_view_permission(request), model
        assert model_admin.has_add_permission(request), model
        assert model_admin.has_change_permission(request), model
        assert model_admin.has_delete_permission(request), model


@pytest.mark.django_db
def test_changelists_and_change_pages_render(client, superuser):
    group = ModifierGroup.objects.create(name="Sauces", kitchen_name="SAUCE")
    option = ModifierOption.objects.create(group=group, name="Mayo", price_delta=30)
    link = ModifierLink.objects.create(
        group=group, product_id=make_product("Burger", "BUR-01").id
    )
    client.force_login(superuser)

    # The admin lives only on the platform host (PLAN §18.1.3).
    for path, text in (
        ("/admin/modifier/modifiergroup/", b"Sauces"),
        (f"/admin/modifier/modifiergroup/{group.pk}/change/", b"Mayo"),
        ("/admin/modifier/modifieroption/", b"Mayo"),
        (f"/admin/modifier/modifieroption/{option.pk}/change/", b"price_delta"),
        ("/admin/modifier/modifierlink/", b"Sauces"),
        (f"/admin/modifier/modifierlink/{link.pk}/change/", b"Burger"),
        ("/admin/modifier/modifiergroup/add/", b"min_choices"),
        ("/admin/modifier/modifieroption/add/", b"is_default"),
        ("/admin/modifier/modifierlink/add/", b"category"),
    ):
        response = client.get(path, HTTP_HOST="hubs.localhost")
        assert response.status_code == 200 and text in response.content, path


@pytest.mark.django_db
def test_support_can_repair_a_group_through_the_admin(client, superuser):
    group = ModifierGroup.objects.create(name="Sacues")
    client.force_login(superuser)
    data = {
        "name": "Sauces",
        "kitchen_name": "",
        "min_choices": "0",
        "max_choices": "2",
        "sort_order": "0",
        "created_by": "",
        "updated_by": "",
        "options-TOTAL_FORMS": "0",
        "options-INITIAL_FORMS": "0",
        "links-TOTAL_FORMS": "0",
        "links-INITIAL_FORMS": "0",
    }
    response = client.post(
        f"/admin/modifier/modifiergroup/{group.pk}/change/",
        data,
        HTTP_HOST="hubs.localhost",
    )
    assert response.status_code == 302, response.content[:2000]
    group.refresh_from_db()
    assert (group.name, group.max_choices) == ("Sauces", 2)
