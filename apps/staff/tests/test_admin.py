"""Django admin of the staff app: full CRUD on every model.

Round 12 (PLAN §17, CLAUDE.md «Frontend y admin») gives the Hub admin full CRUD over all of a hub's
tables; it repeals the read-only admin that apps/demo still copies from round 9 (PLAN §14.3).
"""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.staff.admin import (
    MemberAdmin,
    RoleAdmin,
    ScheduleAdmin,
    ScheduleDayInline,
    StaffSettingsAdmin,
    TimeOffAdmin,
)
from apps.staff.models import Member, Role, Schedule, StaffSettings, TimeOff

from .conftest import make_member, make_role, make_schedule, make_time_off

MODELS = {
    Member: MemberAdmin,
    Role: RoleAdmin,
    Schedule: ScheduleAdmin,
    TimeOff: TimeOffAdmin,
    StaffSettings: StaffSettingsAdmin,
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


def test_every_model_is_registered():
    for model, model_admin in MODELS.items():
        assert isinstance(admin.site._registry[model], model_admin), model
    assert ScheduleAdmin.inlines == [ScheduleDayInline]


def test_full_crud_for_the_platform_staff(superuser):
    # Round 12 (PLAN §17): CRUD, not read only.
    request = request_by(superuser)
    for model in MODELS:
        model_admin = admin.site._registry[model]
        assert model_admin.has_view_permission(request), model
        assert model_admin.has_add_permission(request), model
        assert model_admin.has_change_permission(request), model
        assert model_admin.has_delete_permission(request), model
    inline = ScheduleDayInline(Schedule, admin.site)
    assert inline.has_add_permission(request, None) and inline.has_change_permission(request)
    assert inline.has_delete_permission(request)


@pytest.mark.django_db
def test_a_role_is_added_and_changed_from_the_admin(client, superuser):
    client.force_login(superuser)
    added = client.post(
        "/admin/staff/role/add/",
        {"name": "Stylist", "description": "", "color": "", "order": 0, "is_active": "on"},
        HTTP_HOST="hubs.localhost",
    )
    assert added.status_code == 302, added.content[:500]
    role = Role.objects.get()
    changed = client.post(
        f"/admin/staff/role/{role.pk}/change/",
        {"name": "Senior stylist", "description": "", "color": "", "order": 1},
        HTTP_HOST="hubs.localhost",
    )
    assert changed.status_code == 302
    role.refresh_from_db()
    assert (role.name, role.order, role.is_active) == ("Senior stylist", 1, False)


@pytest.mark.django_db
def test_the_pages_render_on_the_platform_host(client, superuser):
    member = make_member(role=make_role("Stylist"), notes="Private")
    schedule = make_schedule(member)
    leave = make_time_off(member, "2026-10-12", reason="Flu")
    StaffSettings.objects.create()
    client.force_login(superuser)

    for url, text in (
        ("/admin/staff/member/add/", b"first_name"),
        ("/admin/staff/schedule/add/", b"weekday"),
        ("/admin/staff/member/", b"Ana"),
        (f"/admin/staff/member/{member.pk}/change/", b"Private"),
        ("/admin/staff/role/", b"Stylist"),
        (f"/admin/staff/schedule/{schedule.pk}/change/", b"09:00"),
        (f"/admin/staff/timeoff/{leave.pk}/change/", b"Flu"),
        ("/admin/staff/staffsettings/", b"staff settings"),
    ):
        # The admin lives only on the platform host (PLAN §18.1.3).
        response = client.get(url, HTTP_HOST="hubs.localhost")
        assert response.status_code == 200, url
        assert text in response.content, url


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("how", ["page", "list"])
def test_a_record_is_deleted_with_what_hangs_from_it(client, superuser, how):
    # Its «Delete» locks the record before Django deletes the rest (test_concurrency.py), in a transaction
    # of its own: the list's «Delete selected» runs outside the one of the delete page.
    member = make_member()
    make_schedule(member)
    make_time_off(member, "2026-11-02")
    client.force_login(superuser)
    if how == "page":
        url, data = f"/admin/staff/member/{member.pk}/delete/", {"post": "yes"}
    else:
        url, data = "/admin/staff/member/", {"action": "delete_selected", "_selected_action": [str(member.pk)], "post": "yes"}
    response = client.post(url, data, HTTP_HOST="hubs.localhost")
    assert response.status_code == 302, response.content[:500]
    assert not (Member.objects.exists() or Schedule.objects.exists() or TimeOff.objects.exists())
