"""Django admin of the kitchen app: full CRUD for support (round 12, PLAN §17).

A second write path, for the staff only on hubs.erplora.com: it adds, changes and deletes every table of
the app so support can repair; it does not go through the operations' rules and leaves no event. What the
database fills in (ids and timestamps) is shown, not edited.
"""

import datetime as dt

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.utils import timezone

from apps.kitchen.admin import (
    CategoryRouteAdmin,
    DayCounterAdmin,
    KitchenSettingsAdmin,
    LogEntryAdmin,
    ProductRouteAdmin,
    StationAdmin,
    TicketAdmin,
    TicketItemInline,
)
from apps.kitchen.models import (
    CategoryRoute,
    DayCounter,
    KitchenSettings,
    LogEntry,
    ProductRoute,
    Station,
    Ticket,
    TicketItem,
)

from .conftest import make_station

MODELS = {
    Station: StationAdmin,
    ProductRoute: ProductRouteAdmin,
    CategoryRoute: CategoryRouteAdmin,
    KitchenSettings: KitchenSettingsAdmin,
    DayCounter: DayCounterAdmin,
    Ticket: TicketAdmin,
    LogEntry: LogEntryAdmin,
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


def make_ticket(**fields):
    return Ticket.objects.create(
        number="20261014-0007",
        day=dt.date(2026, 10, 14),
        sequence=7,
        received_at=timezone.now(),
        **fields,
    )


def test_every_admin_passes_the_django_checks():
    for model in MODELS:
        assert admin.site._registry[model].check() == [], model


def test_every_model_is_registered_and_the_dishes_are_an_inline_of_their_ticket():
    for model, model_admin in MODELS.items():
        assert isinstance(admin.site._registry[model], model_admin), model
    assert TicketAdmin.inlines == [TicketItemInline]
    assert TicketItemInline.model is TicketItem


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
        StationAdmin,
        TicketAdmin,
        ProductRouteAdmin,
        CategoryRouteAdmin,
    ):
        assert {"id", "created_at", "updated_at"} <= set(model_admin.readonly_fields), (
            model_admin
        )
    assert {"id", "updated_at"} <= set(KitchenSettingsAdmin.readonly_fields)
    assert {"id"} <= set(LogEntryAdmin.readonly_fields)


@pytest.mark.django_db
def test_changelists_and_change_pages_render(client, superuser):
    station = make_station("Grill")
    ticket = make_ticket(label="Table 4")
    TicketItem.objects.create(
        ticket=ticket, position=1, name="Burger", quantity=1, station=station
    )
    LogEntry.objects.create(ticket=ticket, action="received", notes="First round")
    DayCounter.objects.create(day=dt.date(2026, 10, 14), last_number=7)
    client.force_login(superuser)
    for path, text in (
        ("/admin/kitchen/station/", b"Grill"),
        (f"/admin/kitchen/station/{station.pk}/change/", b"printer_usage"),
        ("/admin/kitchen/ticket/", b"Table 4"),
        (f"/admin/kitchen/ticket/{ticket.pk}/change/", b"Burger"),
        ("/admin/kitchen/logentry/", b"First round"),
        ("/admin/kitchen/kitchensettings/", b"15"),
        ("/admin/kitchen/daycounter/", b"2026"),
        ("/admin/kitchen/station/add/", b"destination"),
    ):
        response = client.get(path, HTTP_HOST="hubs.localhost")
        assert response.status_code == 200 and text in response.content, path


@pytest.mark.django_db
def test_support_can_repair_a_station_through_the_admin(client, superuser):
    station = make_station("Grill")
    client.force_login(superuser)
    data = {
        "name": "Charcoal grill",
        "color": "#E03131",
        "destination": "printer",
        "printer_usage": "kitchen",
        "printer_name": "",
        "sort_order": "1",
        "is_active": "on",
        "created_by": "",
        "updated_by": "",
    }
    response = client.post(
        f"/admin/kitchen/station/{station.pk}/change/", data, HTTP_HOST="hubs.localhost"
    )
    assert response.status_code == 302
    station.refresh_from_db()
    assert (station.name, station.destination) == ("Charcoal grill", "printer")
    assert KitchenSettings.objects.count() == 1
