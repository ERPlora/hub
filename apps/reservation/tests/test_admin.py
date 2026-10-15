"""Django admin of the reservation app: full CRUD for support (round 12, PLAN §17).

A second write path, for the staff only on hubs.erplora.com: it adds, changes and deletes every table of
the app so support can repair; it does not go through the operations' rules and leaves no event. What the
database fills in (ids and timestamps) is shown, not edited.
"""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.reservation.admin import (
    BlockedDateAdmin,
    ReservationAdmin,
    SettingsAdmin,
    TimeSlotAdmin,
    WaitlistEntryAdmin,
)
from apps.reservation.models import (
    BlockedDate,
    Reservation,
    Settings,
    TimeSlot,
    WaitlistEntry,
)

from .conftest import make_blocked, make_entry, make_reservation, make_slot, set_rules

MODELS = {
    Settings: SettingsAdmin,
    TimeSlot: TimeSlotAdmin,
    BlockedDate: BlockedDateAdmin,
    Reservation: ReservationAdmin,
    WaitlistEntry: WaitlistEntryAdmin,
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


def test_ids_and_timestamps_are_read_only():
    for model_admin in (
        TimeSlotAdmin,
        BlockedDateAdmin,
        ReservationAdmin,
        WaitlistEntryAdmin,
    ):
        assert {"id", "created_at", "updated_at"} <= set(model_admin.readonly_fields), (
            model_admin
        )
    assert {"id", "updated_at"} <= set(SettingsAdmin.readonly_fields)


@pytest.mark.django_db
def test_changelists_and_change_pages_render(client, superuser):
    reservation = make_reservation(guest_name="Ana Admin")
    make_entry(guest_name="Luis Admin")
    make_slot(max_covers=44)
    make_blocked(reason="Holiday Admin")
    set_rules(max_party_size=17)
    client.force_login(superuser)
    for path, text in (
        ("/admin/reservation/reservation/", b"Ana Admin"),
        (f"/admin/reservation/reservation/{reservation.pk}/change/", b"internal_notes"),
        ("/admin/reservation/waitlistentry/", b"Luis Admin"),
        ("/admin/reservation/timeslot/", b"44"),
        ("/admin/reservation/blockeddate/", b"Holiday Admin"),
        ("/admin/reservation/settings/", b"17"),
        ("/admin/reservation/reservation/add/", b"party_size"),
    ):
        response = client.get(path, HTTP_HOST="hubs.localhost")
        assert response.status_code == 200 and text in response.content, path


@pytest.mark.django_db
def test_support_can_repair_a_reservation_through_the_admin(client, superuser):
    reservation = make_reservation()
    client.force_login(superuser)
    data = {
        "guest_name": "Ana García",
        "guest_phone": "",
        "guest_email": "",
        "date": "2026-10-15",
        "time": "21:30",
        "party_size": "5",
        "duration_minutes": "120",
        "status": "confirmed",
        "source": "phone",
        "notes": "",
        "internal_notes": "",
        "cancellation_reason": "",
        "created_by": "",
        "updated_by": "",
    }
    response = client.post(
        f"/admin/reservation/reservation/{reservation.pk}/change/",
        data,
        HTTP_HOST="hubs.localhost",
    )
    assert response.status_code == 302
    reservation.refresh_from_db()
    assert (
        reservation.party_size,
        reservation.status,
        f"{reservation.time:%H:%M}",
    ) == (5, "confirmed", "21:30")
