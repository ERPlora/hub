"""Django admin of the attendance app, for the platform's staff only (round 12, PLAN §17).

The settings have full CRUD. Working days, breaks and corrections are shown whole and read-only, never
added nor deleted: the law keeps the working-day record four years and a time only changes with a
correction that leaves its trail (art. 34.9 ET), which is an operation (`attendance.record.correct`).
Only a day's internal note can be changed.
"""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.attendance.admin import (
    AttendanceSettingsAdmin,
    BreakInline,
    CorrectionAdmin,
    CorrectionInline,
    RecordAdmin,
)
from apps.attendance.models import AttendanceSettings, Break, Correction, Record

from .conftest import make_member, utc


@pytest.fixture
def superuser(db):
    return get_user_model().objects.create_superuser(
        username="root", password="pw", email="root@example.com"
    )


def request_by(user):
    request = RequestFactory().get("/admin/")
    request.user = user
    return request


def test_the_models_are_registered():
    assert isinstance(admin.site._registry[Record], RecordAdmin)
    assert isinstance(admin.site._registry[Correction], CorrectionAdmin)
    assert isinstance(admin.site._registry[AttendanceSettings], AttendanceSettingsAdmin)
    assert admin.site._registry[Record].inlines == [BreakInline, CorrectionInline]
    # Breaks are seen inside their day.
    assert Break not in admin.site._registry


def test_settings_have_full_crud(superuser):
    request = request_by(superuser)
    model_admin = admin.site._registry[AttendanceSettings]
    assert model_admin.has_add_permission(request)
    assert model_admin.has_change_permission(request)
    assert model_admin.has_delete_permission(request)


@pytest.mark.django_db
def test_working_days_are_read_only_but_their_note(superuser):
    request = request_by(superuser)
    model_admin = admin.site._registry[Record]
    day = Record.objects.create(
        member=make_member(),
        clock_in_at=utc("2026-10-06T07:00"),
        work_date=utc("2026-10-06T07:00").date(),
    )
    assert not model_admin.has_add_permission(request)
    assert not model_admin.has_delete_permission(request, day)
    readonly = set(model_admin.get_readonly_fields(request, day))
    concrete = {field.name for field in Record._meta.concrete_fields}
    assert concrete - readonly == {"note"}
    for inline in (
        BreakInline(Record, admin.site),
        CorrectionInline(Record, admin.site),
    ):
        assert not inline.has_add_permission(request, day)
        assert not inline.has_delete_permission(request, day)
        assert set(inline.get_readonly_fields(request, day)) >= set(inline.fields)


def test_corrections_are_never_written_in_the_admin(superuser):
    request = request_by(superuser)
    model_admin = admin.site._registry[Correction]
    assert not model_admin.has_add_permission(request)
    assert not model_admin.has_change_permission(request)
    assert not model_admin.has_delete_permission(request)
    assert model_admin.has_view_permission(request)


@pytest.mark.django_db
def test_the_pages_render(client, superuser):
    day = Record.objects.create(
        member=make_member(),
        clock_in_at=utc("2026-10-06T07:00"),
        work_date=utc("2026-10-06T07:00").date(),
    )
    Break.objects.create(record=day, started_at=utc("2026-10-06T09:00"))
    AttendanceSettings.objects.create()
    client.force_login(superuser)
    host = {"HTTP_HOST": "hubs.localhost"}
    for url in (
        "/admin/attendance/record/",
        f"/admin/attendance/record/{day.id}/change/",
        "/admin/attendance/correction/",
        "/admin/attendance/attendancesettings/",
    ):
        response = client.get(url, **host)
        assert response.status_code == 200, url
    page = client.get(f"/admin/attendance/record/{day.id}/change/", **host)
    assert b"Ana L" in page.content and b"2026-10-06" in page.content
