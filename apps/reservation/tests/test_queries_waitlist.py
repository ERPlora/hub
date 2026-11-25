"""The waitlist (``reservation.waitlist.list``), in the order people were written down."""

from .conftest import HUB_DB, make_entry, make_reservation, run

pytestmark = HUB_DB


def test_the_waitlist_keeps_its_order_and_filters():
    first = make_entry(time="20:30", guest_name="Luis", guest_phone="+34600333444")
    second = make_entry(time="21:00", guest_name="Marta", is_contacted=True)
    converted = make_reservation()
    make_entry(time="21:00", guest_name="Pepa", reservation=converted)
    make_entry(guest_name="Gone", is_deleted=True)
    page = run("reservation.waitlist.list")
    assert [row.guest_name for row in page.rows] == ["Luis", "Marta", "Pepa"]
    assert (page.rows[2].is_converted, page.rows[2].reservation_id) == (
        True,
        converted.id,
    )
    assert [
        row.id for row in run("reservation.waitlist.list", {"is_contacted": True}).rows
    ] == [second.id]
    assert [
        row.guest_name
        for row in run("reservation.waitlist.list", {"is_converted": False}).rows
    ] == [
        "Luis",
        "Marta",
    ]
    assert [
        row.id for row in run("reservation.waitlist.list", {"search": "600 333"}).rows
    ] == [first.id]
