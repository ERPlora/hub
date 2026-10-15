"""Django admin of the table app: full CRUD for support (round 12, PLAN §17).

A second write path, for the staff only on hubs.erplora.com: it adds, changes and deletes every table of
the app so support can repair; it does not go through the operations' rules and leaves no event. What the
database fills in (ids and timestamps) is shown, not edited.
"""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.table.admin import (
    HoldAdmin,
    SessionMoveInline,
    TableAdmin,
    TableSessionAdmin,
    TableSettingsAdmin,
    ZoneAdmin,
)
from apps.table.models import (
    Hold,
    SessionMove,
    Table,
    TableSession,
    TableSettings,
    Zone,
)

from .conftest import make_hold, make_session, make_table, make_zone

MODELS = {
    Zone: ZoneAdmin,
    Table: TableAdmin,
    TableSession: TableSessionAdmin,
    Hold: HoldAdmin,
    TableSettings: TableSettingsAdmin,
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


def test_every_model_is_registered_and_the_trail_is_an_inline_of_its_check():
    for model, model_admin in MODELS.items():
        assert isinstance(admin.site._registry[model], model_admin), model
    assert TableSessionAdmin.inlines == [SessionMoveInline]
    assert SessionMoveInline.model is SessionMove


def test_full_crud_for_a_superuser(superuser):
    request = request_by(superuser)
    for model in MODELS:
        model_admin = admin.site._registry[model]
        assert model_admin.has_view_permission(request), model
        assert model_admin.has_add_permission(request), model
        assert model_admin.has_change_permission(request), model
        assert model_admin.has_delete_permission(request), model
    inline = SessionMoveInline(TableSession, admin.site)
    assert inline.has_add_permission(request, None) and inline.has_change_permission(
        request
    )


def test_ids_and_timestamps_are_read_only():
    for model_admin in (ZoneAdmin, TableAdmin, TableSessionAdmin, HoldAdmin):
        assert {"id", "created_at", "updated_at"} <= set(model_admin.readonly_fields), (
            model_admin
        )
    assert {"id", "updated_at"} <= set(TableSettingsAdmin.readonly_fields)


@pytest.mark.django_db
def test_changelists_and_change_pages_render(client, superuser):
    zone = make_zone("Terrace")
    table = make_table("T4", zone=zone)
    session = make_session(table, waiter_name="Luis")
    make_hold(table, label="Pedro")
    TableSettings.objects.create()
    client.force_login(superuser)
    for path, text in (
        ("/admin/table/zone/", b"Terrace"),
        (f"/admin/table/zone/{zone.pk}/change/", b"Terrace"),
        ("/admin/table/table/", b"T4"),
        (f"/admin/table/table/{table.pk}/change/", b"position_x"),
        ("/admin/table/tablesession/", b"Luis"),
        (f"/admin/table/tablesession/{session.pk}/change/", b"assignment_reason"),
        ("/admin/table/hold/", b"Pedro"),
        ("/admin/table/tablesettings/", b"60"),
        ("/admin/table/table/add/", b"capacity"),
    ):
        response = client.get(path, HTTP_HOST="hubs.localhost")
        assert response.status_code == 200 and text in response.content, path


@pytest.mark.django_db
def test_support_can_repair_a_table_through_the_admin(client, superuser):
    table = make_table("4", zone=make_zone())
    client.force_login(superuser)
    data = {
        "zone": str(table.zone_id),
        "number": "4A",
        "name": "",
        "capacity": "6",
        "shape": "round",
        "position_x": "16",
        "position_y": "16",
        "width": "72",
        "height": "72",
        "created_by": "",
        "updated_by": "",
        "is_active": "on",
    }
    response = client.post(
        f"/admin/table/table/{table.pk}/change/", data, HTTP_HOST="hubs.localhost"
    )
    assert response.status_code == 302
    table.refresh_from_db()
    assert (table.number, table.capacity, table.shape) == ("4A", 6, "round")
