"""Django admin of the combo app: full CRUD on every model, for the platform's staff.

Round 12 (PLAN §17, CLAUDE.md «Frontend y admin») gives the Hub admin full CRUD over all of a hub's
tables. A raw admin write records no event and checks no business rule beyond the database's.
"""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.combo.admin import (
    ChoiceGroupAdmin,
    ChoiceGroupInline,
    ChoiceOptionAdmin,
    ChoiceOptionInline,
    ComboAdmin,
)
from apps.combo.models import ChoiceGroup, ChoiceOption, Combo

from .conftest import (
    FOOD,
    make_combo,
    make_group,
    make_option,
    make_product,
    tax_category,
)

MODELS = {
    Combo: ComboAdmin,
    ChoiceGroup: ChoiceGroupAdmin,
    ChoiceOption: ChoiceOptionAdmin,
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


def test_every_model_is_registered_with_its_inlines():
    for model, model_admin in MODELS.items():
        assert isinstance(admin.site._registry[model], model_admin), model
    assert ComboAdmin.inlines == [ChoiceGroupInline]
    assert ChoiceGroupAdmin.inlines == [ChoiceOptionInline]


def test_full_crud_for_the_platform_staff(superuser):
    request = request_by(superuser)
    for model in MODELS:
        model_admin = admin.site._registry[model]
        assert model_admin.has_view_permission(request), model
        assert model_admin.has_add_permission(request), model
        assert model_admin.has_change_permission(request), model
        assert model_admin.has_delete_permission(request), model


@pytest.mark.django_db
def test_a_menu_is_added_and_changed_from_the_admin(client, superuser):
    client.force_login(superuser)
    inline = {
        "groups-TOTAL_FORMS": "0",
        "groups-INITIAL_FORMS": "0",
        "groups-MIN_NUM_FORMS": "0",
        "groups-MAX_NUM_FORMS": "1000",
    }
    form = {
        "name": "Menu of the day",
        "kitchen_name": "",
        "price": "1350",
        "supply_kind": "service",
        "tax_category": str(tax_category(FOOD).pk),
        "sort_order": "0",
        "is_active": "on",
        **inline,
    }
    added = client.post("/admin/combo/combo/add/", form, HTTP_HOST="hubs.localhost")
    assert added.status_code == 302, added.content[:800]
    combo = Combo.objects.get()
    changed = client.post(
        f"/admin/combo/combo/{combo.pk}/change/",
        {**form, "price": "1400"},
        HTTP_HOST="hubs.localhost",
    )
    assert changed.status_code == 302, changed.content[:800]
    combo.refresh_from_db()
    assert combo.price == 1400


@pytest.mark.django_db
def test_the_pages_render_on_the_platform_host(client, superuser):
    combo = make_combo("Menu of the day")
    group = make_group(combo, "Starters")
    option = make_option(group, make_product("Lentils"))
    client.force_login(superuser)
    for url, text in (
        ("/admin/combo/combo/", b"Menu of the day"),
        (f"/admin/combo/combo/{combo.pk}/change/", b"Starters"),
        ("/admin/combo/choicegroup/", b"Starters"),
        (f"/admin/combo/choicegroup/{group.pk}/change/", b"Lentils"),
        (f"/admin/combo/choiceoption/{option.pk}/change/", b"price_delta"),
    ):
        response = client.get(url, HTTP_HOST="hubs.localhost")
        assert response.status_code == 200, url
        assert text in response.content, url
