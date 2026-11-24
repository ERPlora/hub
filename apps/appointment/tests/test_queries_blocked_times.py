"""The blocked periods of the agenda and how a person names one."""

import datetime as dt

from apps.appointment.queries.blocked_times import block_label, blocked_out
from apps.schedule.queries import day_label

from .conftest import HUB_DB, MONDAY, TUESDAY, at, ctx_for, make_block, run

pytestmark = HUB_DB


def test_a_block_is_named_by_its_title_its_day_its_hour_and_its_professional(salon):
    visit = make_block(at(MONDAY, "10:00"), at(MONDAY, "11:00"), member=salon.ana, title="Doctor")
    holiday = make_block(at(MONDAY, "00:00"), at(TUESDAY, "00:00"), title="Holiday", all_day=True)
    day = day_label(MONDAY, "en")
    assert block_label(ctx_for(), blocked_out(visit)) == f"Doctor · {day} · 10:00 · Ana López"
    assert block_label(ctx_for(), blocked_out(holiday)) == f"Holiday · {day}"


def test_the_blocks_of_a_range_are_the_business_ones_and_the_professionals(salon):
    everyone = make_block(at(MONDAY, "08:00"), at(MONDAY, "09:00"), title="Meeting")
    ana_s = make_block(
        at(MONDAY, "10:00"), at(MONDAY, "11:00"), member=salon.ana, title="Doctor"
    )
    make_block(
        at(MONDAY, "12:00"), at(MONDAY, "13:00"), member=salon.bea, title="Dentist"
    )
    make_block(
        at(TUESDAY + dt.timedelta(days=1), "12:00"),
        at(TUESDAY + dt.timedelta(days=1), "13:00"),
    )
    page = run(
        "appointment.blocked_time.list",
        {"date_from": MONDAY, "staff_id": str(salon.ana.id)},
    )
    assert [b.id for b in page.rows] == [everyone.id, ana_s.id]
    assert page.rows[1].staff_name == "Ana López"
    assert (
        run(
            "appointment.blocked_time.list", {"date_from": MONDAY, "date_to": TUESDAY}
        ).total
        == 3
    )
