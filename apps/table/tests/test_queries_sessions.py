"""The checks of the room (``table.session.*``): each with its table, zone and waiter, closed as soon as Sales ends its
check, with what that check charged; filtered, sorted, found by the check of Sales, and the lines of a table's check.
"""

import uuid

import pytest
from django.utils import timezone, translation
from live.context import system_context
from live.errors import NotFound

from .conftest import (
    HUB_DB,
    A,
    add_line,
    charge,
    end_order,
    make_session,
    make_table,
    make_zone,
    open_check,
    run,
)

pytestmark = [HUB_DB, pytest.mark.usefixtures("noon")]


def sessions(**params) -> list[dict]:
    return [
        row.model_dump()
        for row in run("table.session.list", {"limit": 100, **params}).rows
    ]


def test_a_check_carries_its_table_zone_and_waiter():
    # The checks carry their zone.
    zone = make_zone("Terrace")
    session = make_session(
        make_table("7", zone=zone), waiter_id="12", waiter_name="Luis"
    )
    (row,) = sessions()
    assert (
        row["id"],
        row["table_number"],
        row["zone_name"],
        row["waiter_name"],
        row["status"],
    ) == (
        session.id,
        "7",
        "Terrace",
        "Luis",
        "open",
    )


def test_a_check_whose_sales_check_ended_reads_closed_with_its_hour():
    table = make_table("4", zone=make_zone())
    order = open_check("Table 4")
    session = make_session(table, order_id=order.id)
    end_order(order.id, "voided")
    (row,) = sessions()
    assert (row["id"], row["status"]) == (session.id, "closed")
    assert row["closed_at"] is not None
    assert sessions(status="open") == []
    assert [r["id"] for r in sessions(status="closed")] == [session.id]


@pytest.mark.parametrize("ending", ["completed", "voided"])
def test_a_parked_check_whose_sales_check_ended_reads_closed(ending):
    from apps.table.models import TableSession

    order = open_check("Ana")
    parked = TableSession.objects.create(table=None, status="parked", order_id=order.id)
    end_order(order.id, ending)
    (row,) = sessions()
    assert (row["id"], row["status"], row["table_id"]) == (parked.id, "closed", None)
    assert row["closed_at"] is not None
    assert sessions(status="parked") == []


def test_the_checks_filter_by_status_zone_waiter_table_and_search():
    room, terrace = make_zone("Dining room"), make_zone("Terrace")
    a = make_session(make_table("1", zone=room), waiter_id="1", minutes_ago=30)
    b = make_session(make_table("12", zone=terrace), waiter_id="2", minutes_ago=20)
    c = make_session(
        make_table("2", zone=room),
        waiter_id="1",
        status="closed",
        closed_at=timezone.now(),
    )
    from apps.table.models import TableSession

    d = TableSession.objects.create(status="parked", table=None, guests_count=2)
    make_session(
        make_table("3", zone=room),
        is_deleted=True,
        deleted_at=timezone.now(),
        status="closed",
    )
    ids = lambda **p: {r["id"] for r in sessions(**p)}  # noqa: E731
    assert ids() == {a.id, b.id, c.id, d.id}
    assert ids(status="open") == {a.id, b.id}
    assert ids(status="parked") == {d.id}
    assert ids(zone_id=str(terrace.id)) == {b.id}
    assert ids(waiter_id="1") == {a.id, c.id}
    assert ids(search="1") == {a.id, b.id}
    parked = next(r for r in sessions() if r["id"] == d.id)
    assert (parked["table_id"], parked["table_number"]) == (None, None)


def test_the_newest_checks_come_first():
    first = make_session(make_table("1"), minutes_ago=50)
    second = make_session(make_table("2"), minutes_ago=10)
    assert [r["id"] for r in sessions()] == [second.id, first.id]
    assert [r["id"] for r in sessions(sort="opened_at")] == [first.id, second.id]


def test_a_check_says_what_its_sales_check_charged_and_a_voided_sale_does_not_count(
    product,
):
    # What each check charged; a voided sale does not count.
    coffee = product()
    table = make_table("4", zone=make_zone())
    order = open_check("Table 4")
    session = make_session(table, order_id=order.id)
    assert sessions()[0]["paid_total"] is None
    first = add_line(order.id, coffee).lines[0]
    add_line(order.id, coffee)
    sale = charge(order.id, key="paid-1", line_ids=[first.id])
    assert sessions()[0]["paid_total"] == 150
    run("sale.sale.void", {"sale_id": str(sale.id), "reason": "Wrong table"})
    assert next(r for r in sessions() if r["id"] == session.id)["paid_total"] is None


def test_the_owner_can_sort_the_checks_by_what_they_charged(product):
    coffee = product()
    rows = []
    for number, cups in (("1", 2), ("2", 1)):
        order = open_check(f"Table {number}")
        for _ in range(cups):
            add_line(order.id, coffee)
        charge(order.id, key=f"sort-{number}")
        rows.append(
            make_session(
                make_table(number),
                order_id=order.id,
                status="closed",
                closed_at=timezone.now(),
            )
        )
    assert [r["id"] for r in sessions(sort="paid_total")] == [rows[1].id, rows[0].id]


def test_the_checks_of_a_sales_check_are_found_by_it():
    order = open_check("Table 4")
    session = make_session(make_table("4"), order_id=order.id)
    assert [
        r.id for r in run("table.session.by_order", {"order_id": str(order.id)}).rows
    ] == [session.id]
    assert run("table.session.by_order", {"order_id": str(uuid.uuid7())}).rows == []


def test_a_check_says_where_it_is_its_table_with_its_zone_or_parked():
    seated = make_session(make_table("5", zone=make_zone("Terrace")))
    away = make_session(None, status="parked")
    assert [run("table.session.get", {"id": str(s.id)}).label for s in (seated, away)] == ["5 (Terrace)", "Parked"]
    assert sorted(row["label"] for row in sessions()) == ["5 (Terrace)", "Parked"]
    with translation.override("es"):
        assert run("table.session.get", {"id": str(away.id)}).label == "Aparcada"


def test_a_line_of_the_check_of_a_table_is_found_by_its_id(product):
    """«Split check» lists the lines of the table's check of Sales: one of them by its id, with its name."""
    order = open_check("Table 5")
    make_session(make_table("5"), order_id=order.id)
    line = add_line(order.id, product(name="Caña", sku="CANA"), quantity="2").lines[-1]
    found = run("table.session.line", {"id": str(line.id)})
    assert (found.id, found.name, found.quantity, found.unit) == (line.id, "Caña", line.quantity, line.unit)


def test_a_line_no_table_holds_or_removed_is_not_found(product):
    """Tables reads only the lines of the checks of its tables, never any other check of Sales, nor a removed line."""
    elsewhere = open_check("Bar")
    loose = add_line(elsewhere.id, product(name="Caña", sku="CANA")).lines[-1]
    order = open_check("Table 5")
    make_session(make_table("5"), order_id=order.id)
    removed = add_line(order.id, product(name="Bravas", sku="BRAV")).lines[-1]
    run("sale.order.remove_line", {"order_id": str(order.id), "line_id": str(removed.id)}, system_context(A))
    for line in (loose, removed):
        with pytest.raises(NotFound) as missing:
            run("table.session.line", {"id": str(line.id)})
        assert missing.value.code == "table.line_not_found"
