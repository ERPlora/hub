"""Models of the staff app: UUIDv7 keys, defaults, orderings and the rules the database itself keeps."""

import datetime as dt
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from apps.staff.models import Member, Role, Schedule, ScheduleDay, StaffSettings, TimeOff

pytestmark = pytest.mark.django_db

NINE, ONE, TWO, SIX = dt.time(9), dt.time(13), dt.time(14), dt.time(18)


def member(first="Ana", last="López", **fields):
    return Member.objects.create(first_name=first, last_name=last, **fields)


def user(username="ana"):
    return get_user_model().objects.create_user(username=username, password="pw")


def violates(constraint, create):
    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        create()
    assert constraint in str(excinfo.value)


# Keys and defaults


def test_keys_are_uuid7():
    ana = member()
    role = Role.objects.create(name="Stylist")
    schedule = Schedule.objects.create(member=ana, name="Usual")
    day = ScheduleDay.objects.create(
        schedule=schedule, weekday=0, start_time=NINE, end_time=SIX
    )
    leave = TimeOff.objects.create(
        member=ana, start_date=dt.date(2026, 10, 1), end_date=dt.date(2026, 10, 2)
    )
    assert {obj.pk.version for obj in (ana, role, schedule, day, leave)} == {7}


def test_member_defaults():
    ana = member()
    ana.refresh_from_db()
    assert (ana.status, ana.is_bookable, ana.booking_buffer) == (
        Member.Status.ACTIVE,
        True,
        0,
    )
    assert (
        ana.email,
        ana.phone,
        ana.employee_number,
        ana.color,
        ana.specialties,
        ana.bio,
    ) == ("",) * 6
    assert (
        ana.role,
        ana.user,
        ana.hire_date,
        ana.termination_date,
        ana.termination_reason,
    ) == (None, None, None, None, "")
    assert (ana.hourly_rate, ana.commission_rate, ana.notes) == (0, Decimal("0.00"), "")
    assert ana.created_at is not None and ana.updated_at is not None


def test_member_full_name_and_str():
    ana = member("Ana", "López")
    assert ana.full_name == str(ana) == "Ana López"


def test_status_choices():
    assert Member.Status.values == ["active", "inactive", "on_leave", "terminated"]
    assert TimeOff.LeaveType.values == [
        "vacation",
        "sick",
        "personal",
        "training",
        "other",
    ]
    assert TimeOff.Status.values == ["pending", "approved", "rejected", "cancelled"]


def test_role_defaults_and_str():
    role = Role.objects.create(name="Stylist")
    role.refresh_from_db()
    assert (role.description, role.color, role.is_active, str(role)) == (
        "",
        "",
        True,
        "Stylist",
    )


def test_schedule_and_time_off_defaults():
    ana = member()
    schedule = Schedule.objects.create(member=ana, name="Usual")
    leave = TimeOff.objects.create(
        member=ana, start_date=dt.date(2026, 10, 1), end_date=dt.date(2026, 10, 1)
    )
    schedule.refresh_from_db()
    leave.refresh_from_db()
    assert (
        schedule.is_default,
        schedule.is_active,
        schedule.effective_from,
        schedule.effective_until,
    ) == (True, True, None, None)
    assert (leave.leave_type, leave.status, leave.is_full_day, leave.reason) == (
        "vacation",
        "pending",
        True,
        "",
    )
    assert (leave.start_time, leave.end_time, leave.approved_by, leave.approved_at) == (
        None,
        None,
        None,
        None,
    )


def test_commission_keeps_two_decimals():
    ana = member(commission_rate=Decimal("12.5"))
    ana.refresh_from_db()
    assert ana.commission_rate == Decimal("12.50")


# Orderings


def test_members_are_ordered_by_name_then_id():
    bea = member("Bea", "Ruiz")
    ana_b = member("Ana", "Zamora")
    ana_a = member("Ana", "Alonso")
    assert list(Member.objects.all()) == [ana_a, ana_b, bea]


def test_roles_are_ordered_by_name():
    second, first = (
        Role.objects.create(name="Washer"),
        Role.objects.create(name="Barber"),
    )
    assert list(Role.objects.all()) == [first, second]


def test_days_are_ordered_by_weekday():
    schedule = Schedule.objects.create(member=member(), name="Usual")
    friday = ScheduleDay.objects.create(
        schedule=schedule, weekday=4, start_time=NINE, end_time=SIX
    )
    monday = ScheduleDay.objects.create(
        schedule=schedule, weekday=0, start_time=NINE, end_time=SIX
    )
    assert list(schedule.days.all()) == [monday, friday]


def test_time_off_is_ordered_by_start_date_most_recent_first():
    ana = member()
    old = TimeOff.objects.create(
        member=ana, start_date=dt.date(2026, 1, 1), end_date=dt.date(2026, 1, 2)
    )
    new = TimeOff.objects.create(
        member=ana, start_date=dt.date(2026, 6, 1), end_date=dt.date(2026, 6, 2)
    )
    assert list(TimeOff.objects.all()) == [new, old]


# Relations


def test_deleting_a_role_unlinks_its_members():
    role = Role.objects.create(name="Stylist")
    ana = member(role=role)
    role.delete()
    ana.refresh_from_db()
    assert ana.role is None


def test_deleting_a_user_unlinks_the_record_and_the_approval():
    account = user()
    ana = member(user=account)
    leave = TimeOff.objects.create(
        member=ana,
        start_date=dt.date(2026, 10, 1),
        end_date=dt.date(2026, 10, 1),
        approved_by=account,
    )
    account.delete()
    ana.refresh_from_db()
    leave.refresh_from_db()
    assert (ana.user, leave.approved_by) == (None, None)


def test_deleting_a_member_deletes_its_schedules_days_and_time_off():
    ana = member()
    schedule = Schedule.objects.create(member=ana, name="Usual")
    ScheduleDay.objects.create(
        schedule=schedule, weekday=0, start_time=NINE, end_time=SIX
    )
    TimeOff.objects.create(
        member=ana, start_date=dt.date(2026, 10, 1), end_date=dt.date(2026, 10, 1)
    )
    ana.delete()
    assert not (
        Schedule.objects.exists()
        or ScheduleDay.objects.exists()
        or TimeOff.objects.exists()
    )


# The rules the database keeps


def test_one_user_one_live_member():
    account = user()
    member("Ana", user=account)
    violates("staff_member_user_unique", lambda: member("Bea", user=account))


def test_a_terminated_member_frees_the_user_and_many_members_have_no_user():
    account = user()
    member("Ana", user=account, status=Member.Status.TERMINATED)
    member("Bea", user=account)
    member("Carla")
    member("Dora")
    assert Member.objects.filter(user__isnull=True).count() == 2


def test_the_commission_is_a_percentage():
    violates(
        "staff_member_commission_range",
        lambda: member(commission_rate=Decimal("100.01")),
    )
    violates(
        "staff_member_commission_range", lambda: member(commission_rate=Decimal("-1"))
    )


def test_role_names_are_unique_whatever_the_case():
    Role.objects.create(name="Stylist")
    violates("staff_role_name_unique", lambda: Role.objects.create(name="STYLIST"))


def test_one_default_schedule_per_member():
    ana, bea = member("Ana"), member("Bea")
    Schedule.objects.create(member=ana, name="Usual", is_default=True)
    Schedule.objects.create(member=ana, name="Summer", is_default=False)
    Schedule.objects.create(member=bea, name="Usual", is_default=True)
    violates(
        "staff_schedule_one_default",
        lambda: Schedule.objects.create(member=ana, name="Other", is_default=True),
    )


def test_a_schedule_does_not_end_before_it_starts():
    ana = member()
    Schedule.objects.create(
        member=ana,
        name="One day",
        is_default=False,
        effective_from=dt.date(2026, 10, 1),
        effective_until=dt.date(2026, 10, 1),
    )
    violates(
        "staff_schedule_valid_range",
        lambda: Schedule.objects.create(
            member=ana,
            name="Wrong",
            is_default=False,
            effective_from=dt.date(2026, 10, 2),
            effective_until=dt.date(2026, 10, 1),
        ),
    )


def test_a_weekday_once_per_schedule_and_within_monday_to_sunday():
    schedule = Schedule.objects.create(member=member(), name="Usual")
    ScheduleDay.objects.create(
        schedule=schedule, weekday=0, start_time=NINE, end_time=SIX
    )
    violates(
        "staff_schedule_day_unique",
        lambda: ScheduleDay.objects.create(
            schedule=schedule, weekday=0, start_time=NINE, end_time=SIX
        ),
    )
    violates(
        "staff_schedule_day_weekday",
        lambda: ScheduleDay.objects.create(
            schedule=schedule, weekday=7, start_time=NINE, end_time=SIX
        ),
    )


def test_a_day_starts_before_it_ends_and_its_break_falls_inside():
    schedule = Schedule.objects.create(member=member(), name="Usual")
    ScheduleDay.objects.create(
        schedule=schedule,
        weekday=0,
        start_time=NINE,
        end_time=SIX,
        break_start=ONE,
        break_end=TWO,
    )
    violates(
        "staff_schedule_day_order",
        lambda: ScheduleDay.objects.create(
            schedule=schedule, weekday=1, start_time=SIX, end_time=NINE
        ),
    )
    violates(
        "staff_schedule_day_break",
        lambda: ScheduleDay.objects.create(
            schedule=schedule, weekday=2, start_time=NINE, end_time=SIX, break_start=ONE
        ),
    )
    violates(
        "staff_schedule_day_break",
        lambda: ScheduleDay.objects.create(
            schedule=schedule,
            weekday=3,
            start_time=NINE,
            end_time=ONE,
            break_start=ONE,
            break_end=TWO,
        ),
    )


def test_time_off_does_not_end_before_it_starts():
    violates(
        "staff_time_off_dates",
        lambda: TimeOff.objects.create(
            member=member(),
            start_date=dt.date(2026, 10, 2),
            end_date=dt.date(2026, 10, 1),
        ),
    )


def test_time_off_has_hours_only_when_it_is_not_a_full_day():
    ana = member()
    TimeOff.objects.create(
        member=ana,
        start_date=dt.date(2026, 10, 1),
        end_date=dt.date(2026, 10, 1),
        is_full_day=False,
        start_time=NINE,
        end_time=ONE,
    )
    violates(
        "staff_time_off_times",
        lambda: TimeOff.objects.create(
            member=ana,
            start_date=dt.date(2026, 10, 2),
            end_date=dt.date(2026, 10, 2),
            is_full_day=False,
        ),
    )
    violates(
        "staff_time_off_times",
        lambda: TimeOff.objects.create(
            member=ana,
            start_date=dt.date(2026, 10, 3),
            end_date=dt.date(2026, 10, 3),
            is_full_day=False,
            start_time=ONE,
            end_time=NINE,
        ),
    )
    violates(
        "staff_time_off_times",
        lambda: TimeOff.objects.create(
            member=ana,
            start_date=dt.date(2026, 10, 4),
            end_date=dt.date(2026, 10, 4),
            start_time=NINE,
            end_time=ONE,
        ),
    )


# The settings of the app: one row, born with the old module's defaults


def test_settings_defaults_are_the_old_modules():
    settings = StaffSettings.objects.create()
    settings.refresh_from_db()
    assert (settings.default_work_start, settings.default_work_end) == (NINE, SIX)
    assert (
        settings.default_break_duration,
        settings.min_advance_booking,
        settings.max_daily_hours,
        settings.overtime_threshold,
    ) == (60, 1, 12, 40)
    assert (
        settings.show_staff_photos,
        settings.show_staff_bio,
        settings.allow_staff_selection,
        settings.notify_new_appointment,
        settings.notify_cancellation,
    ) == (True,) * 5


def test_there_is_one_settings_row():
    StaffSettings.objects.create()
    violates("staff_settings_singleton", lambda: StaffSettings.objects.create())


def test_the_settings_ranges_are_kept_by_the_database():
    for field, value in (
        ("default_break_duration", 481),
        ("min_advance_booking", 169),
        ("max_daily_hours", 0),
        ("max_daily_hours", 25),
        ("overtime_threshold", 0),
        ("overtime_threshold", 169),
    ):
        violates("staff_settings_ranges", lambda: StaffSettings.objects.create(**{field: value}))
