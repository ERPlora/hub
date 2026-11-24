"""The agenda the booking rules judge."""

from apps.appointment.queries.agenda import load_agenda

from .conftest import HUB_DB, MONDAY, at, ctx_for, make_appointment, make_block

pytestmark = HUB_DB


def test_a_professionals_agenda_holds_theirs_and_the_business_alone_only_its_own(salon):
    make_block(at(MONDAY, "08:00"), at(MONDAY, "09:00"), title="Meeting")
    make_block(at(MONDAY, "10:00"), at(MONDAY, "11:00"), member=salon.ana, title="Doctor")
    make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "12:00"), number="APT-ANA")
    make_appointment(salon.lucia, salon.bea, [salon.cut], at(MONDAY, "12:00"), number="APT-BEA")
    theirs = load_agenda(ctx_for(), salon.ana, MONDAY, MONDAY)
    assert sorted(block.label for block in theirs.blocks) == ["Doctor", "Meeting"]
    assert [period.label for period in theirs.busy] == ["APT-ANA Lucía Pérez"]
    alone = load_agenda(ctx_for(), None, MONDAY, MONDAY)
    assert ([block.label for block in alone.blocks], alone.busy, alone.staff) == (["Meeting"], [], None)
