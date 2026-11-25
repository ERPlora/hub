"""A reservation by its id or as a person says it: by its guest's name or phone and its day."""

import datetime as dt

import pytest
from live.errors import Conflict, NotFound

from .conftest import HUB_DB, TODAY, TOMORROW, make_reservation, run

pytestmark = HUB_DB


def test_a_reservation_is_read_by_id_or_by_its_guest_and_day():
    ana = make_reservation(guest_name="Ana García", guest_phone="+34600111222")
    make_reservation(date=TODAY, time="14:00", guest_name="Luis")
    assert run("reservation.reservation.get", {"id": str(ana.id)}).id == ana.id
    assert run("reservation.reservation.get", {"guest": "ana"}).id == ana.id
    assert (
        run(
            "reservation.reservation.get", {"guest": "600111222", "day": "2026-10-15"}
        ).id
        == ana.id
    )


def test_a_guest_with_several_reservations_must_say_which_day():
    make_reservation(guest_name="Ana")
    make_reservation(date=TOMORROW + dt.timedelta(days=1), guest_name="Ana")
    with pytest.raises(Conflict) as caught:
        run("reservation.reservation.get", {"guest": "Ana"})
    assert caught.value.code == "reservation.reservation_ambiguous"
    assert "15/10" in caught.value.message or "2026-10-15" in caught.value.message


def test_a_missing_or_deleted_reservation_is_not_found():
    gone = make_reservation(is_deleted=True)
    for ref in ({"id": str(gone.id)}, {"guest": "Nadie"}):
        with pytest.raises(NotFound) as caught:
            run("reservation.reservation.get", ref)
        assert caught.value.code == "reservation.reservation_not_found"


def test_a_past_reservation_is_found_by_id_and_by_day_but_the_guest_alone_names_the_coming_ones():
    old = make_reservation(date=TODAY - dt.timedelta(days=3), guest_name="Ana")
    coming = make_reservation(guest_name="Ana")
    assert run("reservation.reservation.get", {"guest": "Ana"}).id == coming.id
    assert (
        run("reservation.reservation.get", {"guest": "Ana", "day": str(old.date)}).id
        == old.id
    )
