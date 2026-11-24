"""Your working day today, the list of working days and one day with its breaks (attendance.record.current, .list
and .detail): what each shows and to whom. An employee sees only their own days; whoever sees the team, everyone's."""

import datetime as dt

import pytest
from django.utils import translation
from live.errors import NotFound, PermissionDenied

from apps.attendance.schemas import CurrentOut, RecordDetailOut, RecordPage
from apps.staff.models import Member

from .conftest import HUB_DB, NOW, correction, ctx_for, day, make_member, run, utc

pytestmark = HUB_DB


# attendance.record.current: «my working day today» (ATTENDANCE-F01, F02)


def test_without_a_linked_staff_record_there_is_nothing_to_clock(make_user, clock):
    clock(NOW)
    me = make_user("ana")
    result = run("attendance.record.current", {}, ctx_for("hub_employee", actor=me))
    assert isinstance(result, CurrentOut)
    assert (result.member, result.open, result.recent) == (None, None, [])
    assert (
        result.today.worked_seconds,
        result.today.break_seconds,
        result.today.running,
    ) == (0, 0, None)


def test_my_open_day_with_its_running_break_and_todays_totals(person, clock):
    clock(NOW)
    ana, ctx = person()
    other, _ = person("Bea", "Ruiz")
    day(other, "2026-10-06T07:00")  # somebody else's day never shows
    day(
        ana,
        "2026-10-05T07:00",
        "2026-10-05T15:00",
        breaks=[("2026-10-05T11:00", "2026-10-05T11:30")],
    )
    today = day(
        ana,
        "2026-10-06T07:00",
        breaks=[("2026-10-06T09:00", "2026-10-06T09:15"), ("2026-10-06T10:00", None)],
    )

    result = run("attendance.record.current", {}, ctx)

    assert result.member.id == ana.id and result.member.name == "Ana López"
    assert result.open.id == today.id
    assert result.open.break_started_at == utc("2026-10-06T10:00")
    assert result.as_of == utc(NOW)
    # 3 h 30 since the clock-in, 15 min + 30 min (running) of breaks.
    assert (result.today.worked_seconds, result.today.break_seconds) == (
        2 * 3600 + 45 * 60,
        45 * 60,
    )
    assert result.today.running == "break"
    assert result.today.date == dt.date(2026, 10, 6)
    assert [r.work_date for r in result.recent] == [
        dt.date(2026, 10, 6),
        dt.date(2026, 10, 5),
    ]


def test_recent_days_are_the_last_ten(person, clock):
    clock(NOW)
    ana, ctx = person()
    for n in range(12):
        day(ana, f"2026-09-{10 + n:02d}T07:00", f"2026-09-{10 + n:02d}T15:00")
    recent = run("attendance.record.current", {}, ctx).recent
    assert len(recent) == 10 and recent[0].work_date == dt.date(2026, 9, 21)


# attendance.record.list: an employee sees their own, a manager the team (ATTENDANCE-F06, F07)


def test_an_employee_sees_only_their_own_days(person, clock):
    clock(NOW)
    ana, ctx = person()
    bea, _ = person("Bea", "Ruiz")
    mine = day(ana, "2026-10-06T07:00")
    day(bea, "2026-10-06T07:30")
    page = run("attendance.record.list", {}, ctx)
    assert isinstance(page, RecordPage)
    assert [row.id for row in page.rows] == [mine.id] and page.total == 1


def test_an_employee_cannot_ask_for_someone_elses_days(person):
    _, ctx = person()
    bea, _ = person("Bea", "Ruiz")
    for params in ({"member_id": str(bea.id)}, {"member": "Bea"}):
        with pytest.raises(PermissionDenied):
            run("attendance.record.list", params, ctx)
    # Their own, named, is fine.
    assert run("attendance.record.list", {"member": "Ana"}, ctx).total == 0


def test_an_employee_without_a_staff_record_sees_nothing(make_user, person):
    bea, _ = person("Bea", "Ruiz")
    day(bea, "2026-10-06T07:30")
    nobody = ctx_for("hub_employee", actor=make_user("zoe"))
    assert run("attendance.record.list", {}, nobody).total == 0


def test_a_manager_sees_the_team_with_names_including_who_left(person, clock):
    clock(NOW)
    ana, _ = person()
    bea, _ = person("Bea", "Ruiz")
    gone = make_member("Carlos", "Gil", status=Member.Status.TERMINATED)
    day(ana, "2026-10-06T07:00")
    day(bea, "2026-10-06T07:30")
    day(gone, "2026-09-01T07:00", "2026-09-01T15:00")
    page = run("attendance.record.list", {}, ctx_for("hub_manager"))
    assert [row.member_name for row in page.rows] == [
        "Bea Ruiz",
        "Ana López",
        "Carlos Gil",
    ]


def test_the_filters(person, clock):
    clock(NOW)
    ana, ctx = person(role="hub_manager")
    bea, _ = person("Bea", "Ruiz")
    day(ana, "2026-09-30T07:00", "2026-09-30T15:00")
    october = day(ana, "2026-10-02T07:00", "2026-10-02T15:00")
    flagged = day(bea, "2026-10-03T07:00", status="needs_review")
    day(bea, "2026-10-06T07:00")

    def ids(**params):
        return {row.id for row in run("attendance.record.list", params, ctx).rows}

    assert ids(date_from="2026-10-01", date_to="2026-10-03") == {october.id, flagged.id}
    assert ids(status="needs_review") == {flagged.id}
    assert ids(member_id=str(ana.id)) == ids(member="Ana López") == ids(mine=True)
    assert len(ids(mine=True)) == 2
    assert ids(search="ruiz", status="needs_review") == {flagged.id}


def test_the_sort_and_the_pages(person, clock):
    clock(NOW)
    ana, ctx = person(role="hub_manager")
    bea, _ = person("Bea", "Ruiz")
    first = day(bea, "2026-10-01T07:00", "2026-10-01T15:00")
    second = day(ana, "2026-10-02T07:00", "2026-10-02T15:00")
    third = day(ana, "2026-10-03T07:00", "2026-10-03T15:00")
    assert [r.id for r in run("attendance.record.list", {}, ctx).rows] == [
        third.id,
        second.id,
        first.id,
    ]
    assert [
        r.id for r in run("attendance.record.list", {"sort": "clock_in_at"}, ctx).rows
    ] == [
        first.id,
        second.id,
        third.id,
    ]
    by_name = run("attendance.record.list", {"sort": "member_name"}, ctx).rows
    assert [r.member_name for r in by_name] == ["Ana López", "Ana López", "Bea Ruiz"]
    page = run("attendance.record.list", {"limit": 2, "offset": 2}, ctx)
    assert (page.total, page.limit, page.offset, [r.id for r in page.rows]) == (
        3,
        2,
        2,
        [first.id],
    )


def test_ties_go_by_id_in_the_lists_own_direction(person, clock):
    """hub#684 (as in Sales, Cash register, Inventory and Tasks): a descending list is
    the ascending one read backwards, ties included, and its pages neither repeat nor lose rows. Same person,
    day, status and (empty) clock-out: only the id tells these days apart."""
    clock(NOW)
    ana, ctx = person(role="hub_manager")
    by_id = sorted(
        day(ana, f"2026-10-01T0{hour}:00", status="needs_review").id
        for hour in range(4)
    )

    def listed(sort, **page):
        data = {"sort": sort, **page}
        return [r.id for r in run("attendance.record.list", data, ctx).rows]

    for column in ("work_date", "member_name", "status", "clock_out_at", "id"):
        assert listed(column) == by_id, column
        assert listed(f"-{column}") == by_id[::-1], f"-{column}"
    assert [
        row for offset in (0, 2) for row in listed("-status", limit=2, offset=offset)
    ] == by_id[::-1]


def test_days_without_a_clock_out_stay_where_the_database_puts_them(person, clock):
    """hub#684: this list does not ask for empties last, so they go last ascending and first descending."""
    clock(NOW)
    ana, ctx = person(role="hub_manager")
    closed = day(ana, "2026-10-01T07:00", "2026-10-01T15:00").id
    forgotten = day(ana, "2026-10-02T07:00", status="needs_review").id

    def listed(sort):
        return [r.id for r in run("attendance.record.list", {"sort": sort}, ctx).rows]

    assert listed("clock_out_at") == [closed, forgotten]
    assert listed("-clock_out_at") == [forgotten, closed]


def test_a_corrected_day_says_how_many_times(person, clock):
    clock(NOW)
    ana, ctx = person()
    record = day(ana, "2026-10-05T07:00", "2026-10-05T15:00")
    correction(record)
    correction(record, "Second fix")
    assert run("attendance.record.list", {}, ctx).rows[0].correction_count == 2


# attendance.record.detail


def test_the_detail_carries_the_breaks_and_where_it_was_clocked(
    person, clock, make_user
):
    clock(NOW)
    ana, ctx = person()
    boss = make_user("boss", role="hub_manager", first_name="Marta", last_name="Jefa")
    record = day(
        ana,
        "2026-10-06T07:00",
        breaks=[("2026-10-06T09:00", "2026-10-06T09:15")],
        source="personal",
        in_lat=40.4168,
        in_lng=-3.7038,
        in_accuracy_m=9.5,
        in_distance_m=12.0,
        in_within_radius=True,
        created_by=boss.person,
    )
    detail = run("attendance.record.detail", {"id": str(record.id)}, ctx)
    assert isinstance(detail, RecordDetailOut)
    assert (
        detail.in_lat,
        detail.in_lng,
        detail.in_accuracy_m,
        detail.in_within_radius,
    ) == (40.4168, -3.7038, 9.5, True)
    assert [(b.started_at, b.seconds) for b in detail.breaks] == [
        (utc("2026-10-06T09:00"), 900)
    ]
    assert detail.created_by_name == "Marta Jefa"


def test_someone_elses_day_does_not_exist_for_an_employee(person):
    _, ctx = person()
    bea, _ = person("Bea", "Ruiz")
    record = day(bea, "2026-10-06T07:00")
    with pytest.raises(NotFound):
        run("attendance.record.detail", {"id": str(record.id)}, ctx)
    assert (
        run(
            "attendance.record.detail", {"id": str(record.id)}, ctx_for("hub_manager")
        ).id
        == record.id
    )


@pytest.mark.parametrize(
    ("language", "named"), [("es", "Bea Ruiz · 6 oct 2026"), ("en", "Bea Ruiz · Oct 6, 2026")]
)
def test_the_detail_names_the_day_by_its_person_and_its_day(person, language, named):
    """As «Correct working day» names it (the person and the day, in the reader's language): the assistant's card
    of a correction says which day by it."""
    bea, ctx = person("Bea", "Ruiz")
    record = day(bea, "2026-10-06T07:00", "2026-10-06T15:00")
    with translation.override(language):
        assert run("attendance.record.detail", {"id": str(record.id)}, ctx).name == named


def test_whoever_corrects_days_reads_the_one_they_correct(person):
    """«Correct» rewrites any day, so its holder reads it (and its history) even without seeing the team."""
    bea, _ = person("Bea", "Ruiz")
    record = day(bea, "2026-10-06T07:00", "2026-10-06T15:00")
    corrects = ctx_for(permissions={"attendance.clock", "attendance.correct"})
    assert run("attendance.record.detail", {"id": str(record.id)}, corrects).id == record.id
    assert run("attendance.correction.list", {"record_id": str(record.id)}, corrects).total == 0
    # Positive control: without it, someone else's day still does not exist.
    with pytest.raises(NotFound):
        run("attendance.record.detail", {"id": str(record.id)}, ctx_for(permissions={"attendance.clock"}))


def test_a_forgotten_day_is_no_open_day_on_the_clock(person, clock):
    clock("2026-10-06T07:00")
    ana, ctx = person()
    forgotten = day(ana, "2026-10-05T07:00", breaks=[("2026-10-05T11:00", None)])
    result = run("attendance.record.current", {}, ctx)
    assert result.open is None
    assert result.today.running is None
    row = result.recent[0]
    assert (row.id, row.status, row.worked_seconds) == (forgotten.id, "needs_review", None)
    # Its running break does not grow either: the day's end is unknown.
    assert row.break_seconds == 0
