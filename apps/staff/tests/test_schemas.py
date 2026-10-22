"""Input and output schemas of the staff app: what the API, the live stream and the assistant accept."""

import datetime as dt
import uuid
from decimal import Decimal

import pydantic
import pytest
from django.utils import translation

from apps.staff.schemas import (
    MEMBER_SORTS,
    ROLE_SORTS,
    TIME_OFF_SORTS,
    AvailabilityIn,
    AvailabilityOut,
    BulkCreatedOut,
    BulkCreateIn,
    BulkMemberIn,
    ByIdIn,
    CommissionOut,
    CommissionPage,
    CompensationListIn,
    CompensationOut,
    CompensationPage,
    DayIn,
    MemberDetailOut,
    MemberIn,
    MemberListIn,
    MemberMineOut,
    MemberOut,
    MemberPage,
    MemberPatchIn,
    MemberRefIn,
    MemberStatsOut,
    MineOut,
    Page,
    PageIn,
    RoleIn,
    RoleListIn,
    RoleOut,
    RolePage,
    RolePatchIn,
    ScheduleIn,
    ScheduleListIn,
    ScheduleOut,
    ScheduleUpdateIn,
    SetActiveIn,
    SettingsIn,
    SettingsOut,
    TerminateIn,
    TimeOffDetailOut,
    TimeOffIn,
    TimeOffListIn,
    TimeOffOut,
    TimeOffPage,
    TimeOffRequestIn,
)

ID = uuid.uuid7()
MONDAY = {"weekday": 0, "start_time": "09:00", "end_time": "18:00"}


def errors(schema, **data):
    with pytest.raises(pydantic.ValidationError) as excinfo:
        schema(**data)
    return {
        ".".join(str(part) for part in error["loc"]): error
        for error in excinfo.value.errors()
    }


def invalid_fields(schema, **data):
    return set(errors(schema, **data))


def message(schema, field, **data):
    error = errors(schema, **data)[field]
    return (
        str(error["ctx"]["error"]) if "error" in error.get("ctx", {}) else error["msg"]
    )


# Pages


def test_page_defaults_and_limits():
    assert PageIn().model_dump() == {"limit": 50, "offset": 0}
    assert PageIn(limit=100).limit == 100
    assert invalid_fields(PageIn, limit=0) == {"limit"}
    assert invalid_fields(PageIn, limit=101) == {"limit"}
    assert invalid_fields(PageIn, offset=-1) == {"offset"}


def test_pages_are_the_generic_page():
    assert MemberPage is Page[MemberOut]
    assert CompensationPage is Page[CompensationOut]
    assert CommissionPage is Page[CommissionOut]
    assert RolePage is Page[RoleOut]
    assert TimeOffPage is Page[TimeOffOut]
    assert list(MemberPage.model_fields) == ["rows", "total", "limit", "offset"]


def test_by_id_needs_a_uuid():
    assert ByIdIn(id=str(ID)).id == ID
    assert invalid_fields(ByIdIn, id="nope") == {"id"}


# A staff member is named by id or by name (the assistant speaks names)


def test_a_member_by_id_or_by_name():
    assert MemberRefIn(id=ID).model_dump() == {"id": ID, "member": None}
    assert MemberRefIn(member=" Ana López ").member == "Ana López"
    assert (
        message(MemberRefIn, "member")
        == "Say which staff member: their id or their name."
    )
    assert invalid_fields(MemberRefIn, member="  ") == {"member"}


@pytest.mark.parametrize("schema", [ScheduleListIn, AvailabilityIn, TimeOffIn])
def test_the_member_of_a_schedule_availability_or_time_off_by_id_or_by_name(schema):
    extra = {
        AvailabilityIn: {"date_from": "2026-10-12", "date_to": "2026-10-12"},
        TimeOffIn: {"start_date": "2026-10-12", "end_date": "2026-10-12"},
    }.get(schema, {})
    assert schema(member_id=ID, **extra).member_id == ID
    assert schema(member="Ana", **extra).member == "Ana"
    assert invalid_fields(schema, **extra) == {"member"}


def test_schedule_in_takes_the_member_by_id_or_by_name():
    assert ScheduleIn(member="Ana", days=[MONDAY]).member == "Ana"
    assert invalid_fields(ScheduleIn, days=[MONDAY]) == {"member"}


# Members


def test_member_list_filters_and_sorts():
    assert MemberListIn().model_dump() == {
        "limit": 50,
        "offset": 0,
        "search": None,
        "first_name": None,
        "last_name": None,
        "email": None,
        "phone": None,
        "status": None,
        "role_id": None,
        "role_name": None,
        "is_bookable": None,
        "hire_date_from": None,
        "hire_date_to": None,
        "color": None,
        "user_id": None,
        "sort": "name",
    }
    # A terminated record is never listed, so it is no filter either.
    assert invalid_fields(MemberListIn, status="terminated") == {"status"}
    assert MemberListIn(sort="-hire_date").sort == "-hire_date"
    assert invalid_fields(MemberListIn, sort="salary") == {"sort"}
    # Every column of the old table sorts both ways.
    assert set(MEMBER_SORTS) == {
        "name",
        "first_name",
        "last_name",
        "email",
        "phone",
        "role_name",
        "status",
        "is_bookable",
        "hire_date",
        "color",
        "user_id",
        "id",
    }


def test_member_in_defaults():
    assert MemberIn(first_name=" Ana ", last_name="López").model_dump() == {
        "first_name": "Ana",
        "last_name": "López",
        "email": "",
        "phone": "",
        "employee_number": "",
        "role_id": None,
        "role": None,
        "user_id": None,
        "hire_date": None,
        "status": "active",
        "is_bookable": True,
        "booking_buffer": 0,
        "color": "",
        "specialties": "",
        "bio": "",
        "hourly_rate": 0,
        "commission_rate": Decimal("0"),
        "notes": "",
    }


@pytest.mark.parametrize(
    ("data", "field"),
    [
        ({"first_name": "   "}, "first_name"),
        ({"first_name": "x" * 101}, "first_name"),
        ({"last_name": ""}, "last_name"),
        ({"email": "not-an-email"}, "email"),
        ({"phone": "1" * 21}, "phone"),
        ({"employee_number": "x" * 51}, "employee_number"),
        ({"color": "red"}, "color"),
        ({"color": "#12345"}, "color"),
        ({"hourly_rate": -1}, "hourly_rate"),
        ({"hourly_rate": 12.5}, "hourly_rate"),  # cents are whole
        ({"commission_rate": "100.01"}, "commission_rate"),
        ({"commission_rate": -1}, "commission_rate"),
        ({"commission_rate": "12.345"}, "commission_rate"),
        ({"booking_buffer": -5}, "booking_buffer"),
        ({"booking_buffer": 241}, "booking_buffer"),
        ({"role_id": "nope"}, "role_id"),
        ({"hire_date": "31/12/2026"}, "hire_date"),
        ({"status": "terminated"}, "status"),
    ],
)
def test_member_in_rejects(data, field):
    assert invalid_fields(
        MemberIn, **{"first_name": "Ana", "last_name": "López", **data}
    ) == {field}


def test_member_in_accepts_the_edges():
    member = MemberIn(
        first_name="Ana",
        last_name="López",
        email=" ana@example.com ",
        color="#A1b2C3",
        hourly_rate=1250,
        commission_rate="100",
        booking_buffer=240,
        status="inactive",
        role=" Stylist ",
    )
    assert (
        member.email,
        member.color,
        member.hourly_rate,
        member.commission_rate,
        member.status,
        member.role,
    ) == (
        "ana@example.com",
        "#A1b2C3",
        1250,
        Decimal("100"),
        "inactive",
        "Stylist",
    )


def test_the_email_message_is_translated():
    with translation.override("es"):
        assert message(
            MemberIn, "email", first_name="Ana", last_name="López", email="nope"
        ) == ("Introduzca una dirección de correo electrónico válida.")


def test_member_patch_carries_only_what_was_sent():
    patch = MemberPatchIn(id=ID, role_id=None, phone="600")
    assert patch.model_dump(exclude_unset=True) == {
        "id": ID,
        "role_id": None,
        "phone": "600",
    }
    assert MemberPatchIn(member="Ana", notes="").member == "Ana"
    assert invalid_fields(MemberPatchIn) == {"member"}
    assert invalid_fields(MemberPatchIn, id=ID, first_name="") == {"first_name"}


def test_member_patch_status_is_never_terminated():
    # Inactive is allowed (the form offers it, with Deactivate's check); terminated is staff.member.terminate.
    assert MemberPatchIn(id=ID, status="inactive").status == "inactive"
    assert invalid_fields(MemberPatchIn, id=ID, status="terminated") == {"status"}


def test_terminate_in():
    assert TerminateIn(id=ID).model_dump() == {
        "id": ID,
        "member": None,
        "termination_date": None,
        "reason": "",
    }
    assert TerminateIn(member="Ana", reason=" moved abroad ").reason == "moved abroad"
    assert invalid_fields(TerminateIn, id=ID, reason="x" * 501) == {"reason"}


def test_bulk_create_takes_one_to_a_hundred_rows():
    assert BulkCreateIn(members=[{"first_name": "Ana", "last_name": "López"}]).members[
        0
    ] == BulkMemberIn(first_name="Ana", last_name="López")
    assert invalid_fields(BulkCreateIn, members=[]) == {"members"}
    # Past the hundredth row the batch is refused, never cut in silence.
    assert invalid_fields(
        BulkCreateIn, members=[{"first_name": "A", "last_name": "B"}] * 101
    ) == {"members"}


def test_a_bulk_row_leaves_its_own_checks_to_the_batch():
    # A blank name, a bad date or a negative rate skips that row (with its reason); the rest go in.
    row = BulkMemberIn(
        first_name="  ",
        last_name="x",
        hire_date="not a date",
        hourly_rate=-5,
        email="nope",
    )
    assert (row.first_name, row.hire_date, row.hourly_rate, row.email) == (
        "",
        "not a date",
        -5,
        "nope",
    )
    assert invalid_fields(BulkMemberIn, first_name="x" * 101, last_name="x") == {
        "first_name"
    }
    assert list(BulkCreatedOut.model_fields) == ["created", "skipped"]


def test_compensation_list_filters():
    # The directory's filters and sort (the Rate/h column reads the same rows, page by page), plus id.
    assert CompensationListIn().model_dump() == {**MemberListIn().model_dump(), "id": None}


def test_member_outputs():
    assert list(MemberOut.model_fields) == [
        "id",
        "first_name",
        "last_name",
        "full_name",
        "email",
        "phone",
        "employee_number",
        "role_id",
        "role_name",
        "user_id",
        "status",
        "is_bookable",
        "hire_date",
        "color",
    ]
    assert issubclass(MemberDetailOut, MemberOut)
    assert list(MemberDetailOut.model_fields)[len(MemberOut.model_fields) :] == [
        "booking_buffer",
        "specialties",
        "bio",
        "created_at",
        "updated_at",
    ]
    # Pay and HR notes travel only in the caller's own record and in the compensation sheet.
    assert (
        "hourly_rate" not in MemberDetailOut.model_fields
        and "notes" not in MemberDetailOut.model_fields
    )
    assert issubclass(MemberMineOut, MemberDetailOut)
    assert list(MemberMineOut.model_fields)[-2:] == ["hourly_rate", "commission_rate"]
    assert MineOut(member=None).model_dump() == {"member": None}
    assert list(CompensationOut.model_fields) == [
        "id",
        "user_id",
        "full_name",
        "role_id",
        "role_name",
        "status",
        "hourly_rate",
        "commission_rate",
        "notes",
    ]
    assert list(CommissionOut.model_fields) == [
        "id",
        "user_id",
        "full_name",
        "role_id",
        "role_name",
        "commission_rate",
    ]
    assert list(MemberStatsOut.model_fields) == [
        "total",
        "active",
        "on_leave",
        "inactive",
        "absent_today",
        "pending_time_off",
    ]


# Roles


def test_role_inputs():
    assert RoleIn(name=" Stylist ").model_dump() == {
        "name": "Stylist",
        "description": "",
        "color": "",
        "order": 0,
    }
    assert invalid_fields(RoleIn, name="") == {"name"}
    assert invalid_fields(RoleIn, name="x" * 101) == {"name"}
    assert invalid_fields(RoleIn, name="x", description="x" * 501) == {"description"}
    assert invalid_fields(RoleIn, name="x", color="#zzzzzz") == {"color"}
    assert invalid_fields(RoleIn, name="x", order=-1) == {"order"}
    assert RolePatchIn(id=ID, is_active=False).model_dump(exclude_unset=True) == {
        "id": ID,
        "is_active": False,
    }
    assert list(RoleOut.model_fields) == [
        "id",
        "name",
        "description",
        "color",
        "order",
        "is_active",
        "member_count",
    ]


def test_role_list_filters_and_sorts():
    assert RoleListIn().model_dump() == {
        "limit": 50,
        "offset": 0,
        "search": None,
        "is_active": None,
        "color": None,
        "member_count_min": None,
        "member_count_max": None,
        "sort": "name",
    }
    assert set(ROLE_SORTS) == {
        "name",
        "description",
        "color",
        "order",
        "is_active",
        "member_count",
        "id",
    }
    assert RoleListIn(sort="-member_count").sort == "-member_count"


# Schedules


def test_a_day():
    day = DayIn(
        weekday=6,
        start_time="09:00",
        end_time="14:00",
        break_start="11:00",
        break_end="11:30",
    )
    assert (day.weekday, day.start_time, day.break_end, day.is_working) == (
        6,
        dt.time(9),
        dt.time(11, 30),
        True,
    )
    # The old module's defaults: 09:00 to 18:00.
    assert (DayIn(weekday=0).start_time, DayIn(weekday=0).end_time) == (
        dt.time(9),
        dt.time(18),
    )
    assert DayIn(weekday=5, is_working=False).is_working is False


@pytest.mark.parametrize(
    ("data", "field", "text"),
    [
        ({"weekday": 7}, "weekday", None),
        (
            {"start_time": "18:00", "end_time": "09:00"},
            "end_time",
            "The start time must be before the end time.",
        ),
        (
            {"end_time": "09:00"},
            "end_time",
            "The start time must be before the end time.",
        ),
        (
            {"break_start": "13:00"},
            "break_end",
            "The break needs a start and an end, or neither.",
        ),
        (
            {"break_end": "13:00"},
            "break_end",
            "The break needs a start and an end, or neither.",
        ),
        (
            {"break_start": "08:00", "break_end": "10:00"},
            "break_end",
            "The break must fall inside the working hours.",
        ),
        (
            {"break_start": "17:00", "break_end": "19:00"},
            "break_end",
            "The break must fall inside the working hours.",
        ),
        (
            {"break_start": "14:00", "break_end": "13:00"},
            "break_end",
            "The break must fall inside the working hours.",
        ),
        ({"start_time": "25:00"}, "start_time", None),
    ],
)
def test_a_day_rejects(data, field, text):
    data = {**MONDAY, **data}
    assert invalid_fields(DayIn, **data) == {field}
    if text:
        assert message(DayIn, field, **data) == text


def test_a_schedule():
    schedule = ScheduleIn(member_id=ID, name=" Usual ", days=[MONDAY])
    assert schedule.model_dump() == {
        "name": "Usual",
        "is_default": True,
        "effective_from": None,
        "effective_until": None,
        "days": [
            {
                "weekday": 0,
                "start_time": dt.time(9),
                "end_time": dt.time(18),
                "break_start": None,
                "break_end": None,
                "is_working": True,
            }
        ],
        "member_id": ID,
        "member": None,
    }
    # No name: the service names it «Regular schedule» in the caller's language.
    assert ScheduleIn(member_id=ID, days=[MONDAY]).name == ""


@pytest.mark.parametrize(
    ("data", "field", "text"),
    [
        ({"days": []}, "days", "A schedule needs at least one working day with hours."),
        (
            {"days": [{**MONDAY, "is_working": False}]},
            "days",
            "A schedule needs at least one working day with hours.",
        ),
        (
            {"days": [MONDAY, {**MONDAY, "start_time": "10:00"}]},
            "days",
            "Each weekday can appear only once.",
        ),
        (
            {"effective_from": "2026-10-02", "effective_until": "2026-10-01"},
            "effective_until",
            "The schedule's validity ends before it starts.",
        ),
        ({"name": "x" * 101}, "name", None),
    ],
)
def test_a_schedule_rejects(data, field, text):
    data = {"member_id": ID, "name": "Usual", "days": [MONDAY], **data}
    assert invalid_fields(ScheduleIn, **data) == {field}
    if text:
        assert message(ScheduleIn, field, **data) == text


def test_a_nested_day_error_names_its_field():
    data = {
        "member_id": ID,
        "days": [MONDAY, {"weekday": 1, "start_time": "18:00", "end_time": "09:00"}],
    }
    assert invalid_fields(ScheduleIn, **data) == {"days.1.end_time"}


def test_schedule_update_keeps_what_is_not_sent_and_replaces_the_week():
    update = ScheduleUpdateIn(id=ID, days=[MONDAY])
    # Only the id and the week were sent (exclude_unset also trims inside each day).
    assert set(update.model_dump(exclude_unset=True)) == {"id", "days"}
    assert (
        ScheduleUpdateIn(id=ID, days=[MONDAY], effective_until=None).model_dump(
            exclude_unset=True
        )["effective_until"]
        is None
    )
    assert invalid_fields(ScheduleUpdateIn, id=ID) == {"days"}
    assert invalid_fields(ScheduleUpdateIn, days=[MONDAY]) == {"id"}
    assert "member_id" not in ScheduleUpdateIn.model_fields
    assert SetActiveIn(id=ID, is_active=False).is_active is False


def test_schedule_out():
    assert list(ScheduleOut.model_fields) == [
        "id",
        "member_id",
        "name",
        "is_default",
        "effective_from",
        "effective_until",
        "is_active",
        "days",
    ]


# Availability


def test_availability_range():
    assert AvailabilityIn(
        member_id=ID, date_from="2026-10-01", date_to="2026-10-01"
    ).date_to == dt.date(2026, 10, 1)
    assert AvailabilityIn(
        member_id=ID, date_from="2026-01-01", date_to="2028-01-01"
    ).date_to == dt.date(2028, 1, 1)
    assert message(
        AvailabilityIn,
        "date_to",
        member_id=ID,
        date_from="2026-10-02",
        date_to="2026-10-01",
    ) == ("The end date cannot be before the start date.")
    assert message(
        AvailabilityIn,
        "date_to",
        member_id=ID,
        date_from="2026-01-01",
        date_to="2028-01-02",
    ) == ("Ask for at most 731 days at a time.")
    assert list(AvailabilityOut.model_fields) == ["member_id", "days"]


# Time off


def test_time_off_defaults():
    data = TimeOffIn(member_id=ID, start_date="2026-10-01", end_date="2026-10-03")
    assert data.model_dump() == {
        "leave_type": "vacation",
        "start_date": dt.date(2026, 10, 1),
        "end_date": dt.date(2026, 10, 3),
        "is_full_day": True,
        "start_time": None,
        "end_time": None,
        "reason": "",
        "notes": "",
        "member_id": ID,
        "member": None,
    }


def test_a_full_day_drops_any_hours_sent():
    data = TimeOffRequestIn(
        start_date="2026-10-01",
        end_date="2026-10-01",
        start_time="09:00",
        end_time="13:00",
    )
    assert (data.start_time, data.end_time) == (None, None)
    assert "member_id" not in TimeOffRequestIn.model_fields


def test_a_part_day_keeps_its_hours():
    data = TimeOffRequestIn(
        start_date="2026-10-01",
        end_date="2026-10-01",
        is_full_day=False,
        start_time="09:00",
        end_time="13:00",
    )
    assert (data.start_time, data.end_time) == (dt.time(9), dt.time(13))


@pytest.mark.parametrize(
    ("data", "fields", "text"),
    [
        (
            {"end_date": "2026-09-30"},
            {"end_date"},
            "The end date cannot be before the start date.",
        ),
        (
            {"is_full_day": False},
            {"start_time", "end_time"},
            "A half-day absence needs a start and an end time.",
        ),
        (
            {"is_full_day": False, "start_time": "09:00"},
            {"end_time"},
            "A half-day absence needs a start and an end time.",
        ),
        (
            {"is_full_day": False, "start_time": "13:00", "end_time": "09:00"},
            {"end_time"},
            "The start time must be before the end time.",
        ),
        ({"leave_type": "holiday"}, {"leave_type"}, None),
        ({"reason": "x" * 501}, {"reason"}, None),
        ({"notes": "x" * 2001}, {"notes"}, None),
    ],
)
def test_time_off_rejects(data, fields, text):
    data = {"start_date": "2026-10-01", "end_date": "2026-10-01", **data}
    assert invalid_fields(TimeOffRequestIn, **data) == fields
    if text:
        assert message(TimeOffRequestIn, sorted(fields)[0], **data) == text


def test_time_off_list_filters_and_sorts():
    assert TimeOffListIn().model_dump() == {
        "limit": 50,
        "offset": 0,
        "search": None,
        "member_id": None,
        "status": None,
        "leave_type": None,
        "is_full_day": None,
        "approved_by_id": None,
        "date_from": None,
        "date_to": None,
        "start_date_from": None,
        "start_date_to": None,
        "end_date_from": None,
        "end_date_to": None,
        "sort": "-start_date",
    }
    assert invalid_fields(TimeOffListIn, status="done") == {"status"}
    assert set(TIME_OFF_SORTS) == {
        "start_date",
        "end_date",
        "member_name",
        "leave_type",
        "status",
        "is_full_day",
        "approved_at",
        "id",
    }


def test_time_off_outputs():
    assert list(TimeOffOut.model_fields) == [
        "id",
        "member_id",
        "member_name",
        "leave_type",
        "start_date",
        "end_date",
        "is_full_day",
        "start_time",
        "end_time",
        "status",
        "approved_by_id",
        "approved_at",
    ]
    # The reason and the notes (health data for sick leave) only in the detail.
    assert "reason" not in TimeOffOut.model_fields
    assert list(TimeOffDetailOut.model_fields)[len(TimeOffOut.model_fields) :] == [
        "reason",
        "notes",
        "approved_by_name",
        "created_at",
    ]


# Settings


#: The old module's settings that nothing reads (FIX-STAFF-SETTINGS-ORPHANS): retired from the API.
RETIRED_SETTINGS = {
    "min_advance_booking": 1,
    "max_daily_hours": 8,
    "overtime_threshold": 40,
    "show_staff_photos": True,
    "show_staff_bio": True,
    "allow_staff_selection": True,
    "notify_new_appointment": True,
    "notify_cancellation": True,
}


def test_settings_are_sent_partially_with_the_old_ranges():
    assert SettingsIn().model_dump(exclude_unset=True) == {}
    assert SettingsIn(default_work_start="07:30:00").default_work_start == dt.time(
        7, 30
    )
    for field, value in (
        ("default_break_duration", -1),
        ("default_break_duration", 481),
        ("default_work_end", "24:00"),
    ):
        assert invalid_fields(SettingsIn, **{field: value}) == {field}, field


def test_a_retired_setting_is_refused_by_its_name():
    for field, value in RETIRED_SETTINGS.items():
        # The HTTP layer words it «This field is not allowed.» (test_api.py).
        assert errors(SettingsIn, **{field: value})[field]["type"] == "extra_forbidden", field


def test_the_settings_are_the_default_working_day_with_hours_as_hh_mm():
    assert list(SettingsOut.model_fields) == [
        "default_work_start",
        "default_work_end",
        "default_break_duration",
    ]
    assert SettingsOut.model_fields["default_work_start"].annotation is str


def test_a_long_hire_date_is_the_rows_problem_not_the_batchs():
    # STAFF-F07: «2026-01-15T00:00» skips its row with invalid_hire_date (services); the schema lets it in.
    assert BulkMemberIn(first_name="A", last_name="B", hire_date="2026-01-15T00:00").hire_date == "2026-01-15T00:00"
    assert invalid_fields(BulkMemberIn, first_name="A", last_name="B", hire_date="x" * 101) == {"hire_date"}


def test_a_role_order_fits_the_database():
    assert RoleIn(name="x", order=2_147_483_647).order == 2_147_483_647
    assert invalid_fields(RoleIn, name="x", order=2_147_483_648) == {"order"}
    assert invalid_fields(RolePatchIn, id=ID, order=2_147_483_648) == {"order"}
