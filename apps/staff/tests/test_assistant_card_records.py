"""The card of a write of Staff (hub#495) says which person, role, schedule or time-off request it acts on by its name,
read as whoever asks, never by its id, and left out when that person may not read it. A schedule says whose it is and a
time-off request says whose, of what kind and which days: every person has a «Regular schedule», and one person can ask
for several absences.
"""

import pytest
from live.context import Scope
from live.errors import NotFound, PermissionDenied
from live.operations import get
from pydantic import ValidationError

from apps.staff.models import Member
from apps.staff.schemas import TimeOffDetailOut
from base import assistant
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_assistant_card_values import AN_ID

from .conftest import ctx_for, make_member, make_role, make_schedule, make_time_off

WEEK = [{"weekday": 0, "start_time": "09:00", "end_time": "17:00"}]
A_MISSING_ID = "0192f0b2-3333-7000-8000-000000000003"


def fields_of(write: str, arguments: dict, language: str = "en", ctx=None) -> dict:
    card = assistant.card(get(write), arguments, language, ctx or ctx_for(language=language))
    return {field["name"]: field for field in card["fields"]}


def shown(write: str, arguments: dict, language: str = "en", ctx=None) -> dict:
    return {name: field["value"] for name, field in fields_of(write, arguments, language, ctx).items()}


def read(name: str, data: dict, ctx=None):
    op = get(name)
    return op(ctx or ctx_for(), op.input.model_validate(data))


# ── A person ──────────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "title"), [("en", "Staff member"), ("es", "Miembro del personal")])
@pytest.mark.parametrize("write", ["staff.member.update", "staff.member.deactivate", "staff.member.terminate"])
def test_a_write_on_a_record_says_whose_it_is_and_titles_it_as_the_card_titles_a_name(write, language, title):
    member = make_member("Ana", "López")
    field = fields_of(write, {"id": str(member.id)}, language)["id"]
    assert (field["value"], field["label"]) == ("Ana López", title)


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "title"), [("en", "Staff member"), ("es", "Miembro del personal")])
def test_a_new_schedule_and_a_new_absence_say_whose_they_are(language, title):
    member = make_member("Bea", "Ruiz")
    new_schedule = fields_of("staff.schedule.create", {"member_id": str(member.id), "days": WEEK}, language)
    new_absence = fields_of(
        "staff.time_off.create",
        {"member_id": str(member.id), "start_date": "2026-11-02", "end_date": "2026-11-02"},
        language,
    )
    for field in (new_schedule["member_id"], new_absence["member_id"]):
        assert (field["value"], field["label"]) == ("Bea Ruiz", title)


# ── A role ────────────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "title"), [("en", "Role"), ("es", "Rol")])
def test_a_record_says_its_role_by_its_name(language, title):
    role = make_role("Stylist")
    member = make_member()
    for write, arguments in (
        ("staff.member.create", {"first_name": "Bea", "last_name": "Ruiz", "role_id": str(role.id)}),
        ("staff.member.update", {"id": str(member.id), "role_id": str(role.id)}),
    ):
        field = fields_of(write, arguments, language)["role_id"]
        assert (field["value"], field["label"]) == ("Stylist", title)


@pytest.mark.django_db
def test_each_row_of_a_batch_says_its_role_by_its_name():
    """The case the issue names: the people a batch adds, each with the role they take, never by its id."""
    stylist, waiter = make_role("Stylist"), make_role("Waiter")
    batch = {
        "members": [
            {"first_name": "Ana", "last_name": "Gil", "role_id": str(stylist.id)},
            {"first_name": "Bea", "last_name": "Ruiz", "role_id": str(waiter.id)},
        ]
    }
    rows = shown("staff.member.bulk_create", batch)["members"]
    assert [row["role_id"] for row in rows] == ["Stylist", "Waiter"]
    assert not AN_ID.search(str(rows))


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "title"), [("en", "Role"), ("es", "Rol")])
def test_editing_a_role_says_which_one_and_also_one_retired_to_bring_it_back(language, title):
    """A retired role can be brought back (STAFF-F04): the only way to read it is by this name."""
    active, retired = make_role("Stylist"), make_role("Waiter", is_active=False)
    for role, name in ((active, "Stylist"), (retired, "Waiter")):
        field = fields_of("staff.role.update", {"id": str(role.id), "is_active": True}, language)["id"]
        assert (field["value"], field["label"]) == (name, title)


# ── A schedule ────────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "title"), [("en", "Schedule"), ("es", "Horario")])
@pytest.mark.parametrize(
    ("write", "extra"),
    [
        ("staff.schedule.update", {"days": WEEK}),
        ("staff.schedule.delete", {}),
        ("staff.schedule.set_active", {"is_active": False}),
    ],
)
def test_a_write_on_a_schedule_says_whose_it_is_and_its_name(write, extra, language, title):
    """Everyone may have a schedule of that name: its name alone says nothing about which one."""
    schedule = make_schedule(make_member("Ana", "López"), name="Summer")
    field = fields_of(write, {"id": str(schedule.id), **extra}, language)["id"]
    assert (field["value"], field["label"]) == ("Ana López · Summer", title)


@pytest.mark.django_db
def test_the_read_of_a_schedule_answers_its_week_and_how_the_card_names_it():
    schedule = make_schedule(make_member("Ana", "López"), name="Summer")
    answer = read("staff.schedule.detail", {"id": str(schedule.id)})
    assert answer.label == "Ana López · Summer"
    assert [day.weekday for day in answer.days] == [0]


# ── A time-off request ────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("language", "title", "expected"),
    [
        ("en", "Time off", "Ana López · Vacation · Nov 2, 2026 – Nov 5, 2026"),
        ("es", "Ausencia", "Ana López · Vacaciones · 2 nov 2026 – 5 nov 2026"),
    ],
)
@pytest.mark.parametrize("write", ["staff.time_off.approve", "staff.time_off.reject", "staff.time_off.cancel"])
def test_a_write_on_a_time_off_says_whose_it_is_of_what_kind_and_which_days(write, language, title, expected):
    time_off = make_time_off(make_member("Ana", "López"), "2026-11-02", "2026-11-05")
    field = fields_of(write, {"id": str(time_off.id)}, language)["id"]
    assert (field["value"], field["label"]) == (expected, title)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("language", "expected"), [("en", "Ana López · Vacation · Nov 2, 2026"), ("es", "Ana López · Vacaciones · 2 nov 2026")]
)
def test_a_time_off_of_one_day_says_that_day_once(language, expected):
    time_off = make_time_off(make_member("Ana", "López"), "2026-11-02")
    assert shown("staff.time_off.approve", {"id": str(time_off.id)}, language)["id"] == expected


@pytest.mark.django_db
def test_an_employee_withdrawing_their_own_request_reads_which_one():
    """An employee holds neither «see the detail of time off» nor «manage time off», and withdraws their own request
    (STAFF-F19): the card names it with what their list already shows them."""
    time_off = make_time_off(make_member("Ana", "López"), "2026-11-02")
    employee = ctx_for("hub_employee")
    assert "staff.view_time_off_detail" not in employee.permissions  # positive control
    assert shown("staff.time_off.cancel", {"id": str(time_off.id)}, ctx=employee)["id"] == (
        "Ana López · Vacation · Nov 2, 2026"
    )


@pytest.mark.django_db
def test_the_read_that_names_a_time_off_never_carries_what_is_private():
    """Its reason and notes are only for managers and the person: the read that names it has them nowhere."""
    time_off = make_time_off(make_member(), "2026-11-02", reason="Surgery", notes="Private")
    answer = read("staff.time_off.get", {"id": str(time_off.id)}, ctx_for("hub_employee"))
    assert not {"reason", "notes", "approved_by_name"} & set(answer.model_dump())
    assert {"reason", "notes"} <= set(TimeOffDetailOut.model_fields)  # positive control: the detail does


# ── A closed list, by the word of its screen ──────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("language", "status", "leave_type"), [("en", "On leave", "Sick leave"), ("es", "De baja", "Baja por enfermedad")]
)
def test_a_status_and_a_type_of_absence_go_by_their_word_in_both_languages(language, status, leave_type):
    member = make_member()
    said = shown("staff.member.update", {"id": str(member.id), "status": "on_leave"}, language)
    assert said["status"] == status
    absence = {"member_id": str(member.id), "leave_type": "sick", "start_date": "2026-11-02", "end_date": "2026-11-03"}
    assert shown("staff.time_off.create", absence, language)["leave_type"] == leave_type


# ── What is not theirs to read, or no longer there ────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("needed", "write", "datum"),
    [
        ("staff.view", "staff.member.deactivate", "id"),
        ("staff.view", "staff.role.update", "id"),
        ("staff.view", "staff.schedule.delete", "id"),
        ("staff.view_time_off", "staff.time_off.approve", "id"),
    ],
)
def test_what_the_person_may_not_read_is_left_out_never_said_by_its_id(needed, write, datum):
    member = make_member()
    target = {
        "staff.member.deactivate": member,
        "staff.role.update": make_role(),
        "staff.schedule.delete": make_schedule(member),
        "staff.time_off.approve": make_time_off(member, "2026-11-02"),
    }[write]
    allowed = ctx_for()
    arguments = {"id": str(target.id)}
    assert datum in shown(write, arguments, ctx=allowed)  # positive control
    denied = ctx_for(permissions=set(allowed.permissions) - {needed})
    said = shown(write, arguments, ctx=denied)
    assert datum not in said
    assert not AN_ID.search(str(said))


@pytest.mark.django_db
@pytest.mark.parametrize("write", ["staff.member.deactivate", "staff.role.update", "staff.schedule.delete", "staff.time_off.approve"])
def test_what_does_not_exist_is_left_out(write):
    assert shown(write, {"id": A_MISSING_ID}) == {}


@pytest.mark.django_db
def test_the_records_of_someone_who_left_are_left_out_as_their_screens_leave_them_out():
    member = make_member(status=Member.Status.TERMINATED)
    schedule = make_schedule(member)
    time_off = make_time_off(member, "2026-11-02")
    assert shown("staff.member.deactivate", {"id": str(member.id)}) == {}
    assert shown("staff.schedule.delete", {"id": str(schedule.id)}) == {}
    assert shown("staff.time_off.approve", {"id": str(time_off.id)}) == {}


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.usefixtures("no_test_fallback")
def test_a_record_of_another_business_is_left_out(hub_a, hub_b):
    """Each business in its own database, as production: an id of A names nothing in B."""
    in_a, in_b = ctx_for(scope=Scope("host", hub_a.slug)), ctx_for(scope=Scope("host", hub_b.slug))
    with use_hub(hub_a):
        member = make_member()
        role = make_role()
        schedule = make_schedule(member)
        time_off = make_time_off(member, "2026-11-02")
        writes = [
            ("staff.member.deactivate", member),
            ("staff.role.update", role),
            ("staff.schedule.delete", schedule),
            ("staff.time_off.approve", time_off),
        ]
        for write, record in writes:  # positive control
            assert "id" in shown(write, {"id": str(record.id)}, ctx=in_a), write
    with use_hub(hub_b):
        for write, record in writes:
            assert shown(write, {"id": str(record.id)}, ctx=in_b) == {}, write


# ── The reads that name them ──────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_the_read_of_a_role_needs_the_right_to_see_the_staff():
    role = make_role()
    allowed = ctx_for()
    assert read("staff.role.detail", {"id": str(role.id)}, allowed).name == role.name
    with pytest.raises(PermissionDenied):
        read("staff.role.detail", {"id": str(role.id)}, ctx_for(permissions=set(allowed.permissions) - {"staff.view"}))


@pytest.mark.django_db
def test_the_read_of_a_time_off_needs_the_right_to_see_the_time_off():
    time_off = make_time_off(make_member(), "2026-11-02")
    allowed = ctx_for()
    assert read("staff.time_off.get", {"id": str(time_off.id)}, allowed).id == time_off.id
    with pytest.raises(PermissionDenied):
        read("staff.time_off.get", {"id": str(time_off.id)}, ctx_for(permissions=set(allowed.permissions) - {"staff.view_time_off"}))


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["staff.role.detail", "staff.time_off.get"])
def test_the_reads_say_not_found_for_what_is_not_there(name):
    with pytest.raises(NotFound):
        read(name, {"id": A_MISSING_ID})


@pytest.mark.parametrize("name", ["staff.role.detail", "staff.time_off.get"])
def test_the_reads_refuse_no_id(name):
    with pytest.raises(ValidationError):
        get(name).input.model_validate({})


@pytest.mark.parametrize("name", ["staff.role.detail", "staff.time_off.get"])
def test_the_reads_are_no_tool_of_the_assistant(name):
    """The model finds them in its lists; only the card reads them."""
    assert not assistant.is_tool(get(name))
