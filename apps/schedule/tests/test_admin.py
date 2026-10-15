"""Django admin of the schedule app: full CRUD on every model, the intervals as lines of their day.

Round 12 (PLAN §17, CLAUDE.md «Frontend y admin») gives the Hub admin full CRUD over all of a hub's
tables; ids and audit dates are read only.
"""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.schedule.admin import (
    OverrideAdmin,
    OverrideIntervalInline,
    ScheduleSettingsAdmin,
    SpecialDayAdmin,
    SpecialDayIntervalInline,
    WeekDayAdmin,
    WeekDayIntervalInline,
)
from apps.schedule.models import Override, ScheduleSettings, SpecialDay, WeekDay

from .conftest import make_override, make_special_day

MODELS = {
    WeekDay: (WeekDayAdmin, WeekDayIntervalInline),
    SpecialDay: (SpecialDayAdmin, SpecialDayIntervalInline),
    Override: (OverrideAdmin, OverrideIntervalInline),
    ScheduleSettings: (ScheduleSettingsAdmin, None),
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


def test_every_model_is_registered_with_its_intervals_inline():
    for model, (model_admin, inline) in MODELS.items():
        assert isinstance(admin.site._registry[model], model_admin), model
        assert list(model_admin.inlines) == ([inline] if inline else []), model


def test_full_crud_for_the_platform_staff(superuser):
    request = request_by(superuser)
    for model, (_model_admin, inline) in MODELS.items():
        model_admin = admin.site._registry[model]
        assert model_admin.has_view_permission(request), model
        assert model_admin.has_add_permission(request), model
        assert model_admin.has_change_permission(request), model
        assert model_admin.has_delete_permission(request), model
        if inline:
            lines = inline(model, admin.site)
            assert lines.has_add_permission(
                request, None
            ) and lines.has_change_permission(request), model
            assert lines.has_delete_permission(request), model


def test_ids_and_audit_dates_are_read_only():
    assert set(SpecialDayAdmin.readonly_fields) == {"id", "created_at", "updated_at"}
    assert set(OverrideAdmin.readonly_fields) == {"id", "created_at", "updated_at"}
    assert set(WeekDayAdmin.readonly_fields) == {"id", "updated_at"}
    assert set(ScheduleSettingsAdmin.readonly_fields) == {"id", "updated_at"}


@pytest.mark.django_db
def test_a_special_day_is_added_from_the_admin(client, superuser):
    client.force_login(superuser)
    added = client.post(
        "/admin/schedule/specialday/add/",
        {
            "date": "2026-12-25",
            "name": "Christmas",
            "is_closed": "on",
            "notes": "",
            "intervals-TOTAL_FORMS": "0",
            "intervals-INITIAL_FORMS": "0",
            "intervals-MIN_NUM_FORMS": "0",
            "intervals-MAX_NUM_FORMS": "1000",
        },
        HTTP_HOST="hubs.localhost",
    )
    assert added.status_code == 302, added.content[:800]
    assert SpecialDay.objects.get().name == "Christmas"


@pytest.mark.django_db
def test_the_pages_render_on_the_platform_host(client, superuser):
    eve = make_special_day("2026-12-24", "Christmas Eve", ("10:00", "13:00"))
    summer = make_override(
        "2026-08-01", "2026-08-31", "Summer hours", ("10:00", "14:00")
    )
    monday = WeekDay.objects.get(weekday=0)
    ScheduleSettings.objects.create()
    client.force_login(superuser)
    for url, text in (
        ("/admin/schedule/weekday/", b"Monday"),
        (f"/admin/schedule/weekday/{monday.pk}/change/", b"09:00"),
        ("/admin/schedule/specialday/", b"Christmas Eve"),
        (f"/admin/schedule/specialday/{eve.pk}/change/", b"10:00"),
        ("/admin/schedule/override/", b"Summer hours"),
        (f"/admin/schedule/override/{summer.pk}/change/", b"14:00"),
        ("/admin/schedule/schedulesettings/", b"schedule settings"),
        ("/admin/schedule/specialday/add/", b"recurring_yearly"),
    ):
        response = client.get(url, HTTP_HOST="hubs.localhost")
        assert response.status_code == 200, url
        assert text in response.content, url
