"""Read operations of the attendance app: what each one shows, to whom, and how the durations count.

The cases come from the old module's batteries (data.pg «records.mine only returns the caller's rows»,
«presence.count counts only open days», «local_date is the business day»), its screens' tests (minutes,
csv, the clock's «today») and the WORKBOOK: an employee sees only their own days and history, a day
waiting for review has no worked time, a night shift counts on the day it started.
"""

import csv
import datetime as dt
import io

import pytest
from django.utils import timezone, translation
from live.errors import NotFound, PermissionDenied

from apps.attendance import queries
from apps.attendance.models import AttendanceSettings, Break, Correction, Record
from apps.attendance.schemas import (
    CorrectionPage,
    CurrentOut,
    ExportOut,
    PersonOut,
    PersonPage,
    PresenceCountOut,
    PresencePage,
    RecordDetailOut,
    RecordPage,
    SettingsOut,
)
from apps.staff.models import Member

from .conftest import ctx_for, make_member, run, utc

pytestmark = pytest.mark.django_db

NOW = "2026-10-06T10:30"  # 12:30 in Madrid (UTC+2 in October)


def day(
    member, clock_in, clock_out=None, *, status=None, breaks=(), **fields
) -> Record:
    """A working day straight in the table: times in UTC, ``breaks`` as ``(start, end or None)``."""
    start = utc(clock_in)
    record = Record.objects.create(
        member=member,
        clock_in_at=start,
        clock_out_at=utc(clock_out) if clock_out else None,
        status=status or ("closed" if clock_out else "open"),
        work_date=timezone.localdate(start),
        **fields,
    )
    for begin, end in breaks:
        Break.objects.create(
            record=record, started_at=utc(begin), ended_at=utc(end) if end else None
        )
    return record


def correction(record, reason="Forgot to clock out", by=None, at=None) -> Correction:
    trail = Correction.objects.create(
        record=record,
        old_clock_in_at=record.clock_in_at,
        old_clock_out_at=record.clock_out_at,
        old_status=record.status,
        new_clock_in_at=record.clock_in_at,
        new_clock_out_at=record.clock_out_at,
        new_status=record.status,
        reason=reason,
        created_by=None if by is None else by.person,
        is_system=by is None,
        created_by_name=queries.user_name(None if by is None else by.person),
    )
    if at:
        Correction.objects.filter(pk=trail.pk).update(created_at=utc(at))
    return trail


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


def test_a_night_shift_counts_on_the_day_it_started(person, clock):
    # 22:00 → 06:00 in Madrid: one day, on the 5th; today (the 6th) has nothing running.
    clock("2026-10-06T03:00")  # 05:00 in Madrid
    ana, ctx = person()
    night = day(ana, "2026-10-05T20:00")
    result = run("attendance.record.current", {}, ctx)
    assert result.open.id == night.id and result.open.work_date == dt.date(2026, 10, 5)
    assert (result.today.worked_seconds, result.today.running) == (0, None)


def test_the_business_day_is_madrids_not_utcs(person, clock):
    # 23:30 UTC on the 5th is already 01:30 on the 6th in Madrid (old data.pg case).
    clock("2026-10-06T00:30")
    ana, ctx = person()
    day(ana, "2026-10-05T23:30")
    result = run("attendance.record.current", {}, ctx)
    assert result.open.work_date == dt.date(2026, 10, 6)
    assert (result.today.worked_seconds, result.today.running) == (3600, "work")


# Durations


def test_a_closed_day_counts_its_breaks_out(person, clock):
    clock(NOW)
    ana, ctx = person()
    day(
        ana,
        "2026-10-05T07:02:41",
        "2026-10-05T15:05:03",
        breaks=[("2026-10-05T11:00", "2026-10-05T11:30")],
    )
    row = run("attendance.record.list", {}, ctx).rows[0]
    assert (row.break_count, row.break_seconds) == (1, 1800)
    assert row.worked_seconds == (8 * 3600 + 2 * 60 + 22) - 1800
    assert row.break_started_at is None


def test_an_open_day_counts_until_now_and_its_running_break_too(person, clock):
    clock(NOW)
    ana, ctx = person()
    day(ana, "2026-10-06T08:00", breaks=[("2026-10-06T10:00", None)])
    row = run("attendance.record.list", {}, ctx).rows[0]
    assert (row.break_seconds, row.worked_seconds) == (30 * 60, 2 * 3600)
    assert row.as_of == utc(NOW)


def test_a_day_waiting_for_review_has_no_worked_time(person, clock):
    # «Until now» would count the days nobody worked: it stays empty until a manager corrects it.
    clock(NOW)
    ana, ctx = person()
    day(ana, "2026-10-04T08:00", status="needs_review")
    row = run("attendance.record.list", {}, ctx).rows[0]
    assert (row.status, row.worked_seconds) == ("needs_review", None)


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


# attendance.correction.list: the history (ATTENDANCE-F09; the employee's own, attendance#8)


def test_the_history_newest_first_with_who(person, make_user):
    ana, ctx = person()
    record = day(ana, "2026-10-05T07:00", "2026-10-05T15:00")
    boss = make_user("boss", role="hub_manager", first_name="Marta", last_name="Jefa")
    older = correction(record, "First", by=boss, at="2026-10-05T18:00")
    newer = correction(record, "Second", by=boss, at="2026-10-06T09:00")
    page = run("attendance.correction.list", {"record_id": str(record.id)}, ctx)
    assert isinstance(page, CorrectionPage)
    assert [c.id for c in page.rows] == [newer.id, older.id]
    assert (
        page.rows[0].reason,
        page.rows[0].created_by_name,
        page.rows[0].is_system,
    ) == ("Second", "Marta Jefa", False)


def test_an_employee_reads_the_history_of_their_own_days_only(person):
    ana, ctx = person()
    bea, _ = person("Bea", "Ruiz")
    mine = day(ana, "2026-10-05T07:00", "2026-10-05T15:00")
    theirs = day(bea, "2026-10-05T07:00", "2026-10-05T15:00")
    correction(mine)
    correction(theirs)
    with pytest.raises(NotFound):
        run("attendance.correction.list", {"record_id": str(theirs.id)}, ctx)
    assert {c.record_id for c in run("attendance.correction.list", {}, ctx).rows} == {
        mine.id
    }
    assert run("attendance.correction.list", {}, ctx_for("hub_manager")).total == 2


def test_a_system_correction_speaks_the_readers_language(person):
    ana, ctx = person()
    record = day(ana, "2026-10-05T07:00", "2026-10-05T15:00")
    correction(record, str(queries.TERMINATED_REASON))
    with translation.override("es"):
        row = run(
            "attendance.correction.list", {"record_id": str(record.id)}, ctx
        ).rows[0]
    assert row.is_system is True and row.created_by_name == ""
    assert row.reason == "Jornada cerrada al dar de baja a la persona en Personal."


# attendance.presence.list: who is in now (ATTENDANCE-F11)


def test_who_is_in_now_leaves_out_closed_and_forgotten_days(person, clock):
    clock(NOW)
    ana, _ = person()
    bea, _ = person("Bea", "Ruiz")
    carlos, _ = person("Carlos", "Gil")
    dani, _ = person("Dani", "Paz")
    day(ana, "2026-10-06T07:00")
    day(bea, "2026-10-06T08:00", breaks=[("2026-10-06T10:00", None)])
    day(carlos, "2026-10-06T06:00", "2026-10-06T09:00")
    day(dani, "2026-10-04T07:00", status="needs_review")
    page = run("attendance.presence.list", {}, ctx_for("hub_manager"))
    assert isinstance(page, PresencePage)
    assert page.total == 2
    assert [(p.member_name, p.break_started_at) for p in page.rows] == [
        ("Ana López", None),
        ("Bea Ruiz", utc("2026-10-06T10:00")),
    ]
    assert [
        p.member_name
        for p in run(
            "attendance.presence.list", {"search": "bea"}, ctx_for("hub_manager")
        ).rows
    ] == ["Bea Ruiz"]


def test_only_who_sees_the_team_sees_who_is_in(person):
    _, ctx = person()
    with pytest.raises(PermissionDenied):
        run("attendance.presence.list", {}, ctx)


# attendance.presence.count: how many are in now (the Home's «Clocked in now», ATTENDANCE-F11)


def test_how_many_are_in_now_counts_what_the_list_shows(person, clock):
    # The old battery's «presence.count counts only open days»: the count is the list's total, whatever its page.
    clock(NOW)
    assert run("attendance.presence.count", {}, ctx_for("hub_manager")) == PresenceCountOut(count=0)
    ana, _ = person()
    bea, _ = person("Bea", "Ruiz")
    carlos, _ = person("Carlos", "Gil")
    dani, _ = person("Dani", "Paz")
    gone = make_member("Eva", "Sanz", status=Member.Status.TERMINATED)
    day(ana, "2026-10-06T07:00")
    day(bea, "2026-10-06T08:00", breaks=[("2026-10-06T10:00", None)])  # on a break: in
    day(carlos, "2026-10-06T06:00", "2026-10-06T09:00")  # closed
    day(dani, "2026-10-04T07:00", status="needs_review")
    day(gone, "2026-10-06T08:00")
    day(make_member("Fina", "Vidal"), "2026-10-05T20:00")  # 14 h 30 min open: forgotten
    count = run("attendance.presence.count", {}, ctx_for("hub_manager"))
    assert isinstance(count, PresenceCountOut)
    assert count.count == 2
    assert count.count == run("attendance.presence.list", {"limit": 1}, ctx_for("hub_manager")).total


def test_only_who_sees_the_team_counts_who_is_in(person):
    _, ctx = person()
    with pytest.raises(PermissionDenied):
        run("attendance.presence.count", {}, ctx)


# attendance.person.list: the «Person» filter


def test_the_people_of_the_filter_include_who_left_with_days(person):
    person()
    gone = make_member("Carlos", "Gil", status=Member.Status.TERMINATED)
    make_member(
        "Dora", "Sin", status=Member.Status.TERMINATED
    )  # left without a single day
    day(gone, "2026-09-01T07:00", "2026-09-01T15:00")
    page = run("attendance.person.list", {}, ctx_for("hub_manager"))
    assert isinstance(page, PersonPage)
    assert [(p.name, p.status) for p in page.rows] == [
        ("Ana López", "active"),
        ("Carlos Gil", "terminated"),
    ]
    assert [
        p.name
        for p in run(
            "attendance.person.list", {"search": "gil"}, ctx_for("hub_manager")
        ).rows
    ] == ["Carlos Gil"]


# attendance.person.detail: one person by id, as the «Person» filter shows them (the assistant's card names by it)


def test_an_employee_reads_their_own_person_by_its_id(person):
    ana, ctx = person()
    found = run("attendance.person.detail", {"id": str(ana.id)}, ctx)
    assert isinstance(found, PersonOut)
    assert (found.id, found.name, found.status) == (ana.id, "Ana López", "active")


def test_someone_else_does_not_exist_for_an_employee(person):
    _, ctx = person()
    bea = make_member("Bea", "Ruiz")
    with pytest.raises(NotFound):
        run("attendance.person.detail", {"id": str(bea.id)}, ctx)


@pytest.mark.parametrize(
    "extra", ["attendance.view_all", "attendance.clock_others", "attendance.correct"]
)
def test_who_sees_the_team_clocks_others_or_corrects_reads_anyone(extra):
    bea = make_member("Bea", "Ruiz")
    ctx = ctx_for(permissions={"attendance.clock", extra})
    assert run("attendance.person.detail", {"id": str(bea.id)}, ctx).name == "Bea Ruiz"


def test_who_left_is_read_while_they_have_days_as_the_filter_lists_them():
    gone = make_member("Carlos", "Gil", status=Member.Status.TERMINATED)
    nobody = make_member("Dora", "Sin", status=Member.Status.TERMINATED)
    day(gone, "2026-09-01T07:00", "2026-09-01T15:00")
    found = run("attendance.person.detail", {"id": str(gone.id)}, ctx_for("hub_manager"))
    assert (found.name, found.status) == ("Carlos Gil", "terminated")
    for missing in (nobody.id, "0192f0b2-3333-7000-8000-000000000003"):
        with pytest.raises(NotFound):
            run("attendance.person.detail", {"id": str(missing)}, ctx_for("hub_manager"))


def test_a_person_needs_the_time_clock():
    bea = make_member("Bea", "Ruiz")
    with pytest.raises(PermissionDenied):
        run("attendance.person.detail", {"id": str(bea.id)}, ctx_for(permissions={"staff.view"}))


def test_nobody_behind_the_request_reads_no_person():
    """«Clock in» alone with no account behind it (the platform, an anonymous caller): there is no own record to read,
    so nobody is named — never anyone."""
    bea = make_member("Bea", "Ruiz")
    with pytest.raises(NotFound):
        run("attendance.person.detail", {"id": str(bea.id)}, ctx_for(actor=None, permissions={"attendance.clock"}))


# attendance.settings.get


def test_the_settings_are_the_defaults_until_saved(person):
    _, ctx = person()
    defaults = run("attendance.settings.get", {}, ctx)
    assert isinstance(defaults, SettingsOut)
    assert (
        defaults.require_location,
        defaults.geofence_radius_m,
        defaults.auto_close_after_hours,
    ) == (False, 100, 12)
    assert (defaults.workplace_set, defaults.saved, defaults.updated_at) == (
        False,
        False,
        None,
    )
    AttendanceSettings.objects.create(
        require_location=True, workplace_lat=40.4, workplace_lng=-3.7
    )
    saved = run("attendance.settings.get", {}, ctx)
    assert (saved.require_location, saved.workplace_set, saved.saved) == (
        True,
        True,
        True,
    )


# attendance.record.export: the CSV (ATTENDANCE-F10; the old csv.test.ts cases)


def rows_of(export: ExportOut) -> list[list[str]]:
    return list(csv.reader(io.StringIO(export.csv)))


def test_the_csv_header_and_its_lines(person, clock):
    clock(NOW)
    ana, _ = person()
    gone = make_member("Carlos", "Gil", status=Member.Status.TERMINATED)
    day(
        ana,
        "2026-10-05T07:02:41",
        "2026-10-05T15:05:03",
        breaks=[("2026-10-05T11:00", "2026-10-05T11:30")],
        in_within_radius=True,
        out_within_radius=False,
    )
    day(gone, "2026-10-06T08:00", breaks=[("2026-10-06T10:00", None)])
    day(gone, "2026-10-04T08:00", status="needs_review")

    export = run(
        "attendance.record.export",
        {"date_from": "2026-10-01", "date_to": "2026-10-31", "sort": "clock_in_at"},
        ctx_for("hub_manager"),
    )

    assert isinstance(export, ExportOut)
    assert (export.filename, export.content_type, export.rows) == (
        "attendance-2026-10.csv",
        "text/csv",
        3,
    )
    assert export.csv.split("\r\n")[0] == (
        "date,user,clock_in,clock_out,break_minutes,worked_minutes,status,within_radius_in,within_radius_out"
    )
    assert export.csv.endswith("\r\n")
    assert rows_of(export)[1:] == [
        [
            "2026-10-04",
            "Carlos Gil",
            "2026-10-04 10:00",
            "",
            "0",
            "",
            "needs_review",
            "",
            "",
        ],
        [
            "2026-10-05",
            "Ana López",
            "2026-10-05 09:02",
            "2026-10-05 17:05",
            "30",
            "452",
            "closed",
            "1",
            "0",
        ],
        # Open: worked until the export instant, the running break taken off.
        [
            "2026-10-06",
            "Carlos Gil",
            "2026-10-06 10:00",
            "",
            "30",
            "120",
            "open",
            "",
            "",
        ],
    ]


def test_the_csv_defuses_formulas_and_quotes_commas(clock):
    clock(NOW)
    tricky = make_member('Pérez, Ana "La', 'jefa"')
    formula = make_member("=HYPERLINK(", '"x")')
    day(tricky, "2026-10-05T07:00", "2026-10-05T15:00")
    day(formula, "2026-10-06T07:00", "2026-10-06T08:00")
    text = run(
        "attendance.record.export", {"sort": "clock_in_at"}, ctx_for("hub_manager")
    ).csv
    assert '"Pérez, Ana ""La jefa"""' in text
    assert '"\'=HYPERLINK( ""x"")"' in text


def test_an_empty_filter_exports_only_the_header(person):
    _, ctx = person()
    export = run(
        "attendance.record.export",
        {"date_from": "2026-01-01", "date_to": "2026-01-31"},
        ctx,
    )
    assert (export.rows, export.csv.count("\r\n"), export.filename) == (
        0,
        1,
        "attendance-2026-01.csv",
    )


def test_an_employee_exports_only_their_own_days(person, clock):
    clock(NOW)
    ana, ctx = person()
    bea, _ = person("Bea", "Ruiz")
    day(ana, "2026-10-05T07:00", "2026-10-05T15:00")
    day(bea, "2026-10-05T07:00", "2026-10-05T15:00")
    assert [
        row[1] for row in rows_of(run("attendance.record.export", {}, ctx))[1:]
    ] == ["Ana López"]
    with pytest.raises(PermissionDenied):
        run("attendance.record.export", {"member_id": str(bea.id)}, ctx)


def test_the_file_name_follows_the_dates():
    assert (
        queries.export_filename(dt.date(2026, 2, 1), dt.date(2026, 2, 28))
        == "attendance-2026-02.csv"
    )
    assert (
        queries.export_filename(dt.date(2026, 2, 1), dt.date(2026, 2, 27))
        == "attendance-2026-02-01_2026-02-27.csv"
    )
    assert queries.export_filename(None, None) == "attendance.csv"


# A forgotten day (open longer than the settings' hours) reads as waiting for review, whether or not
# the worker's review has run yet (every quarter of an hour): it never counts «until now» (review of
# 2026-10-15, findings 1–3).


def test_is_stale_is_an_open_day_past_the_hours():
    start = utc("2026-10-05T07:00")
    open_day = Record(clock_in_at=start, status="open")
    assert queries.is_stale(open_day, 12, utc("2026-10-05T19:01")) is True
    assert queries.is_stale(open_day, 12, utc("2026-10-05T19:00")) is False
    assert queries.is_stale(open_day, 24, utc("2026-10-05T19:01")) is False
    for status in ("closed", "needs_review"):
        assert queries.is_stale(Record(clock_in_at=start, status=status), 12, utc("2026-10-07T07:00")) is False


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


def test_a_forgotten_day_lists_as_needs_review_and_filters_so(person, clock):
    AttendanceSettings.objects.create(auto_close_after_hours=10)
    clock("2026-10-06T20:00")
    ana, ctx = person(role="hub_manager")
    stale = day(ana, "2026-10-06T07:00")
    bea, _ = person("Bea", "Ruiz")
    fresh = day(bea, "2026-10-06T12:00")
    rows = {row.id: row for row in run("attendance.record.list", {}, ctx).rows}
    assert (rows[stale.id].status, rows[stale.id].worked_seconds) == ("needs_review", None)
    assert (rows[fresh.id].status, rows[fresh.id].worked_seconds) == ("open", 8 * 3600)
    assert [r.id for r in run("attendance.record.list", {"status": "open"}, ctx).rows] == [fresh.id]
    assert [r.id for r in run("attendance.record.list", {"status": "needs_review"}, ctx).rows] == [stale.id]


def test_a_running_break_of_a_day_waiting_for_review_does_not_grow(person, clock):
    clock("2026-10-08T07:00")
    ana, ctx = person()
    day(
        ana,
        "2026-10-05T07:00",
        status="needs_review",
        breaks=[("2026-10-05T09:00", "2026-10-05T09:30"), ("2026-10-05T12:00", None)],
    )
    row = run("attendance.record.list", {}, ctx).rows[0]
    assert (row.break_seconds, row.worked_seconds) == (1800, None)


def test_who_is_in_leaves_out_forgotten_days_and_terminated_records(person, clock):
    clock("2026-10-06T20:00")
    ana, _ = person()
    bea, _ = person("Bea", "Ruiz")
    gone = make_member("Carlos", "Gil", status=Member.Status.TERMINATED)
    day(ana, "2026-10-06T07:00")  # 13 h: forgotten
    day(bea, "2026-10-06T12:00")
    day(gone, "2026-10-06T15:00")
    assert [p.member_name for p in run("attendance.presence.list", {}, ctx_for("hub_manager")).rows] == ["Bea Ruiz"]


def test_the_csv_writes_a_forgotten_day_as_needs_review_without_worked_time(person, clock):
    clock("2026-10-06T07:00")
    ana, _ = person()
    day(ana, "2026-10-05T07:00")
    line = rows_of(run("attendance.record.export", {}, ctx_for("hub_manager")))[1]
    assert line[4:7] == ["0", "", "needs_review"]


def test_a_correction_keeps_who_made_it_when_their_user_is_deleted(person, make_user):
    # Review of 2026-10-15, finding 4: «System» is only the system, never a deleted user.
    ana, ctx = person()
    record = day(ana, "2026-10-05T07:00", "2026-10-05T15:00")
    boss = make_user("boss", role="hub_manager", first_name="Marta", last_name="Jefa")
    correction(record, "First", by=boss)
    boss.person.delete()
    row = run("attendance.correction.list", {"record_id": str(record.id)}, ctx).rows[0]
    assert (row.is_system, row.created_by_name) == (False, "Marta Jefa")
