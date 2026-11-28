"""What of Appointments travels in an export of the business (BASE-F35): the agenda's blocks still to come (a holiday, a
training), the whole business's and each professional's by the professional's name, read and written with Appointments'
own operations, so that loading the file brings them back as they were. The appointments and the blocks that already
ended are what already happened: they never travel.

Every test runs against the real apps, in business A's own database, as production does.
"""

import base64
import datetime as dt

from apps.appointment.tests.conftest import HUB_DB, in_business_a, make_member
from base import blueprint
from base.tests.blueprint_round_trip import app_report, call, ctx, data_of, exported, loaded_back

__all__ = ["ctx", "in_business_a"]
pytestmark = HUB_DB

SHOWN = ("title", "block_type", "start", "end", "all_day", "staff_name", "reason")


def soon() -> dt.date:
    return dt.date.today() + dt.timedelta(days=10)


def day(offset: int) -> str:
    return (soon() + dt.timedelta(days=offset)).isoformat()


def a_diary(ctx):
    make_member("Inés", "Vidal")
    call(ctx, "appointment.blocked_time.create", title="Local holiday", block_type="holiday", start=day(0), end=day(1),
         all_day=True)  # fmt: skip
    call(ctx, "appointment.blocked_time.create", title="Training", block_type="other", start=f"{day(3)} 15:00",
         end=f"{day(3)} 18:00", staff="Inés Vidal", reason="Colour course")  # fmt: skip


def the_blocks(ctx) -> list[tuple]:
    """The agenda's blocks of the coming weeks as the business reads them, without ids."""
    rows = call(ctx, "appointment.blocked_time.list", date_from=soon() - dt.timedelta(days=5), date_to=day(30), limit=100)
    return sorted(tuple(getattr(row, name) for name in SHOWN) for row in rows.rows)


def emptied(ctx) -> None:
    rows = call(ctx, "appointment.blocked_time.list", date_from=soon() - dt.timedelta(days=40), date_to=day(20), limit=100)
    for row in rows.rows:
        call(ctx, "appointment.blocked_time.delete", id=row.id)


def blocks_part(report: dict) -> dict:
    return next(part for part in app_report(report, "appointment")["datasets"] if part["key"] == "appointment.blocked_time")


def test_a_backup_brings_the_agenda_s_coming_blocks_back_with_their_professional(ctx):
    a_diary(ctx)
    before = the_blocks(ctx)
    file = exported(ctx, ["appointment"])
    emptied(ctx)

    report = loaded_back(ctx, file)

    assert the_blocks(ctx) == before
    assert (blocks_part(report)["created"], blocks_part(report)["already"]) == (2, 0)


def test_loading_the_file_again_duplicates_nothing(ctx):
    a_diary(ctx)
    file = exported(ctx, ["appointment"])

    report = loaded_back(ctx, file)

    assert (blocks_part(report)["created"], blocks_part(report)["already"]) == (0, 2)


def test_a_block_that_already_ended_never_travels(ctx):
    past = dt.date.today() - dt.timedelta(days=30)
    call(ctx, "appointment.blocked_time.create", title="Old training", start=f"{past} 10:00", end=f"{past} 12:00")
    a_diary(ctx)

    titles = [row["title"] for row in data_of(ctx, ["appointment"])["appointment.blocked_time"]]

    assert sorted(titles) == ["Local holiday", "Training"]


def test_a_block_of_a_professional_the_business_does_not_have_is_told_and_the_others_load(ctx):
    a_diary(ctx)
    bundle = blueprint.archive.read_base64(exported(ctx, ["appointment"]))
    training = next(row for row in bundle.data["appointment.blocked_time"] if row["title"] == "Training")
    training["staff"] = "Marta Ruiz"
    emptied(ctx)

    report = loaded_back(ctx, base64.b64encode(blueprint.archive.write_zip(bundle)).decode())

    assert (blocks_part(report)["created"], blocks_part(report)["failed"]) == (1, 1)
    assert blocks_part(report)["problems"][0].startswith("«Training»: ")
    assert [block[0] for block in the_blocks(ctx)] == ["Local holiday"]
