"""How the book names a reservation (its ``label``): its guest, its day and its time, in the caller's language."""

import pytest

from apps.reservation.queries.naming import _who

from .conftest import HUB_DB, WHEN, in_, make_reservation, run


@HUB_DB
@pytest.mark.parametrize("language", ["es", "en"])
def test_a_reservation_is_named_by_its_guest_its_day_and_its_time_as_its_dialog_says_it(language):
    booked = make_reservation()
    assert run("reservation.reservation.get", {"id": str(booked.id)}, in_(language)).label == f"Ana García · {WHEN[language]}"


@HUB_DB
def test_a_guest_booked_under_her_phone_is_named_by_it_and_an_erased_one_by_when_alone():
    """A guest who booked herself by WhatsApp without a name goes by her phone; once her data are erased, nothing of
    hers is left to say: the reservation is named by its day and its time."""
    by_phone = make_reservation(guest_name="", guest_phone="+34600111222")
    erased = make_reservation(guest_name="", guest_phone="", time="22:30")
    assert [_who(in_("es"), row) for row in (by_phone, erased)] == ["+34600111222", ""]
    assert run("reservation.reservation.get", {"id": str(by_phone.id)}, in_("es")).label == f"+34600111222 · {WHEN['es']}"
    assert run("reservation.reservation.get", {"id": str(erased.id)}, in_("es")).label == "15 oct 2026 · 22:30"
