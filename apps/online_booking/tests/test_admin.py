"""Django admin of the online booking app: full CRUD on both tables for support (round 12, PLAN §17).

A second write path, for the staff only on hubs.erplora.com: it does not go through the operations' rules,
so it warns rather than prevents. What the database fills in (ids and timestamps) is shown, not edited; a
link's hash can be emptied (revoked), never read back as a link.
"""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.online_booking.admin import BookingAdmin, SettingsAdmin
from apps.online_booking.models import Booking, Settings

from .conftest import TUESDAY, at, make_appointment

MODELS = {Settings: SettingsAdmin, Booking: BookingAdmin}


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


def test_every_model_is_registered():
    for model, model_admin in MODELS.items():
        assert isinstance(admin.site._registry[model], model_admin), model


def test_full_crud_for_a_superuser(superuser):
    request = request_by(superuser)
    for model in MODELS:
        model_admin = admin.site._registry[model]
        assert model_admin.has_view_permission(request), model
        assert model_admin.has_add_permission(request), model
        assert model_admin.has_change_permission(request), model
        assert model_admin.has_delete_permission(request), model


def test_ids_and_timestamps_are_read_only_and_every_field_is_reachable():
    assert {"id", "updated_at"} <= set(SettingsAdmin.readonly_fields)
    assert {"id", "created_at"} <= set(BookingAdmin.readonly_fields)
    for model, model_admin in MODELS.items():
        automatic = set(model_admin.readonly_fields)
        editable = (
            {field.name for field in model._meta.get_fields() if field.concrete}
            - automatic
            - {"singleton"}
        )
        assert editable <= set(model_admin.fields), model


@pytest.mark.django_db
def test_changelists_and_change_pages_render(client, superuser, salon):
    appointment = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(TUESDAY, "10:00"), number="APT-ADMIN-1"
    )
    booking = Booking.objects.create(
        appointment=appointment, token_hash="a" * 64, requester="f" * 64
    )
    client.force_login(superuser)
    for path, text in (
        ("/admin/online_booking/booking/", b"APT-ADMIN-1"),
        (f"/admin/online_booking/booking/{booking.pk}/change/", b"APT-ADMIN-1"),
        ("/admin/online_booking/settings/", b"#6366f1"),
        ("/admin/online_booking/settings/add/", b"page_title"),
    ):
        response = client.get(path, HTTP_HOST="hubs.localhost")
        assert response.status_code == 200 and text in response.content, path
