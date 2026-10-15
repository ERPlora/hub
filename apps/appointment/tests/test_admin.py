"""Django admin of the appointment app: full CRUD on every table for support (round 12, PLAN §17).

A second write path, for the staff only on hubs.erplora.com: it adds, changes and deletes every table so
that support can repair; it does not go through the operations' rules, so it warns rather than prevents.
What the database fills in (ids and timestamps) is shown, not edited.
"""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.appointment.admin import (
    AppointmentAdmin,
    AppointmentServiceInline,
    BlockedTimeAdmin,
    CounterAdmin,
    HistoryInline,
    RecurringAdmin,
    RecurringServiceInline,
    SettingsAdmin,
)
from apps.appointment.models import (
    Appointment,
    AppointmentService,
    BlockedTime,
    Counter,
    History,
    Recurring,
    RecurringService,
    Settings,
)

from .conftest import MONDAY, at, make_appointment, make_block

MODELS = {
    Appointment: AppointmentAdmin,
    BlockedTime: BlockedTimeAdmin,
    Recurring: RecurringAdmin,
    Settings: SettingsAdmin,
    Counter: CounterAdmin,
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
    assert AppointmentAdmin.inlines == [AppointmentServiceInline, HistoryInline]
    assert RecurringAdmin.inlines == [RecurringServiceInline]
    assert (
        AppointmentServiceInline.model,
        HistoryInline.model,
        RecurringServiceInline.model,
    ) == (
        AppointmentService,
        History,
        RecurringService,
    )


def test_full_crud_for_a_superuser(superuser):
    request = request_by(superuser)
    for model in MODELS:
        model_admin = admin.site._registry[model]
        assert model_admin.has_view_permission(request), model
        assert model_admin.has_add_permission(request), model
        assert model_admin.has_change_permission(request), model
        assert model_admin.has_delete_permission(request), model
    for inline_class, parent in (
        (AppointmentServiceInline, Appointment),
        (HistoryInline, Appointment),
        (RecurringServiceInline, Recurring),
    ):
        inline = inline_class(parent, admin.site)
        assert inline.has_add_permission(
            request, None
        ) and inline.has_change_permission(request), inline_class


def test_ids_and_timestamps_are_read_only():
    assert {"id", "created_at", "updated_at"} <= set(AppointmentAdmin.readonly_fields)
    assert {"id", "created_at", "updated_at"} <= set(RecurringAdmin.readonly_fields)
    assert {"id", "created_at", "updated_at"} <= set(BlockedTimeAdmin.readonly_fields)
    assert {"id", "updated_at"} <= set(SettingsAdmin.readonly_fields)
    assert {"id", "at"} <= set(HistoryInline.readonly_fields)


def test_support_sees_and_repairs_every_field_of_an_appointment():
    automatic = {"id", "created_at", "updated_at"}
    editable = {
        field.name for field in Appointment._meta.get_fields() if field.concrete
    } - automatic
    assert editable <= set(AppointmentAdmin.fields)


@pytest.mark.django_db
def test_changelists_and_change_pages_render(client, superuser, salon):
    appointment = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"), number="APT-ADMIN-1"
    )
    History.objects.create(appointment=appointment, action="created", actor="Ana")
    block = make_block(at(MONDAY, "12:00"), at(MONDAY, "13:00"), title="Training")
    Settings.objects.create()
    Counter.objects.create(day=MONDAY, last_number=4)
    client.force_login(superuser)
    for path, text in (
        ("/admin/appointment/appointment/", b"APT-ADMIN-1"),
        (f"/admin/appointment/appointment/{appointment.pk}/change/", b"Haircut"),
        ("/admin/appointment/appointment/add/", b"customer"),
        ("/admin/appointment/blockedtime/", b"Training"),
        (f"/admin/appointment/blockedtime/{block.pk}/change/", b"Training"),
        ("/admin/appointment/recurring/", b"0"),
        ("/admin/appointment/recurring/add/", b"frequency"),
        ("/admin/appointment/settings/", b"60"),
        ("/admin/appointment/counter/", b"4"),
    ):
        response = client.get(path, HTTP_HOST="hubs.localhost")
        assert response.status_code == 200 and text in response.content, path
