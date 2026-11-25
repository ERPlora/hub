"""The history of corrections of the working days (attendance.correction.list): newest first, with who made them, in the
reader's language when the system made them; an employee reads the history of their own days only."""

import pytest
from django.utils import translation
from live.errors import NotFound

from apps.attendance import queries
from apps.attendance.schemas import CorrectionPage

from .conftest import HUB_DB, correction, ctx_for, day, run

pytestmark = HUB_DB


# attendance.correction.list: the history (ATTENDANCE-F09; the employee's own)


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
    correction(record, str(queries.corrections.TERMINATED_REASON))
    with translation.override("es"):
        row = run(
            "attendance.correction.list", {"record_id": str(record.id)}, ctx
        ).rows[0]
    assert row.is_system is True and row.created_by_name == ""
    assert row.reason == "Jornada cerrada al dar de baja a la persona en Personal."


def test_a_correction_keeps_who_made_it_when_their_user_is_deleted(person, make_user):
    # «System» is only the system, never a deleted user.
    ana, ctx = person()
    record = day(ana, "2026-10-05T07:00", "2026-10-05T15:00")
    boss = make_user("boss", role="hub_manager", first_name="Marta", last_name="Jefa")
    correction(record, "First", by=boss)
    boss.person.delete()
    row = run("attendance.correction.list", {"record_id": str(record.id)}, ctx).rows[0]
    assert (row.is_system, row.created_by_name) == (False, "Marta Jefa")
