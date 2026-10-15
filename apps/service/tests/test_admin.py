"""Django admin of the service app: full CRUD for support (round 12, PLAN §17).

A second write path, for the staff only on hubs.erplora.com: it adds, changes and deletes every table,
so that support can repair; it does not go through the operations' rules, so it warns rather than
prevents. What the database fills in (ids and timestamps) is shown, not edited.
"""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.service.admin import (
    AssignmentAdmin,
    CategoryAdmin,
    GrantAdjustmentInline,
    GrantAdmin,
    PackageAdmin,
    PackageItemInline,
    RedemptionInline,
    ServiceAdmin,
    ServiceSettingsAdmin,
)
from apps.service.models import (
    Assignment,
    Category,
    Grant,
    GrantAdjustment,
    Package,
    PackageItem,
    Redemption,
    Service,
    ServiceSettings,
)

from .conftest import (
    make_customer,
    make_grant,
    make_member,
    make_package,
    make_redemption,
    make_service,
    make_tax,
)

MODELS = {
    Service: ServiceAdmin,
    Category: CategoryAdmin,
    Assignment: AssignmentAdmin,
    Package: PackageAdmin,
    Grant: GrantAdmin,
    ServiceSettings: ServiceSettingsAdmin,
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


def test_every_model_is_registered_and_the_children_are_inlines():
    for model, model_admin in MODELS.items():
        assert isinstance(admin.site._registry[model], model_admin), model
    assert PackageAdmin.inlines == [PackageItemInline]
    assert GrantAdmin.inlines == [GrantAdjustmentInline, RedemptionInline]
    assert (
        PackageItemInline.model,
        GrantAdjustmentInline.model,
        RedemptionInline.model,
    ) == (PackageItem, GrantAdjustment, Redemption)


def test_full_crud_for_a_superuser(superuser):
    request = request_by(superuser)
    for model in MODELS:
        model_admin = admin.site._registry[model]
        assert model_admin.has_view_permission(request), model
        assert model_admin.has_add_permission(request), model
        assert model_admin.has_change_permission(request), model
        assert model_admin.has_delete_permission(request), model
    for inline_class, parent in (
        (PackageItemInline, Package),
        (GrantAdjustmentInline, Grant),
        (RedemptionInline, Grant),
    ):
        inline = inline_class(parent, admin.site)
        assert inline.has_add_permission(
            request, None
        ) and inline.has_change_permission(request), inline_class


def test_ids_and_timestamps_are_read_only():
    assert {"id", "created_at", "updated_at"} <= set(ServiceAdmin.readonly_fields)
    assert {"id", "created_at", "updated_at"} <= set(GrantAdmin.readonly_fields)
    assert {"id", "updated_at"} <= set(ServiceSettingsAdmin.readonly_fields)


@pytest.mark.django_db
def test_changelists_and_change_pages_render(client, superuser):
    tax = make_tax()
    cut = make_service("Haircut", tax=tax)
    package = make_package("Bono 5", [cut], max_uses=5)
    grant = make_grant(package, make_customer("Lucía"))
    make_redemption(grant, cut)
    Assignment.objects.create(service=cut, member=make_member("Ana"))
    Category.objects.create(name="Hair")
    ServiceSettings.objects.create()
    client.force_login(superuser)
    for path, text in (
        ("/admin/service/service/", b"Haircut"),
        (f"/admin/service/service/{cut.pk}/change/", b"Haircut"),
        ("/admin/service/category/", b"Hair"),
        ("/admin/service/assignment/", b"Ana"),
        ("/admin/service/package/", b"Bono 5"),
        (f"/admin/service/package/{package.pk}/change/", b"sessions"),
        ("/admin/service/grant/", b"Bono 5"),
        (f"/admin/service/grant/{grant.pk}/change/", b"redeemed_at"),
        ("/admin/service/servicesettings/", b"60"),
        ("/admin/service/service/add/", b"tax_category"),
        ("/admin/service/grant/add/", b"customer"),
    ):
        response = client.get(path, HTTP_HOST="hubs.localhost")
        assert response.status_code == 200 and text in response.content, path


@pytest.mark.django_db
def test_support_can_repair_a_category_through_the_admin(client, superuser):
    category = Category.objects.create(name="Hiar")
    client.force_login(superuser)
    data = {
        "name": "Hair",
        "description": "",
        "icon": "",
        "color": "",
        "sort_order": "0",
        "created_by": "",
        "updated_by": "",
    }
    response = client.post(
        f"/admin/service/category/{category.pk}/change/",
        data,
        HTTP_HOST="hubs.localhost",
    )
    assert response.status_code == 302
    category.refresh_from_db()
    assert category.name == "Hair"


@pytest.mark.django_db
def test_the_admin_refuses_a_parent_that_closes_a_loop(client, superuser):
    hair = Category.objects.create(name="Hair")
    colour = Category.objects.create(name="Colour", parent=hair)
    client.force_login(superuser)
    data = {"name": "Hair", "description": "", "parent": str(colour.pk), "icon": "", "color": "", "sort_order": "0", "created_by": "", "updated_by": ""}
    response = client.post(f"/admin/service/category/{hair.pk}/change/", data, HTTP_HOST="hubs.localhost")
    assert response.status_code == 200
    assert b"A category cannot hang from itself or from one of its subcategories." in response.content
    hair.refresh_from_db()
    assert hair.parent is None


def test_support_sees_and_repairs_every_step_of_a_session():
    # A session of the till moves through its states; support reads and fixes every one of them.
    editable = {
        field.name
        for field in Redemption._meta.get_fields()
        if field.concrete and field.name not in ("id", "grant")
    }
    assert editable <= set(RedemptionInline.fields)
