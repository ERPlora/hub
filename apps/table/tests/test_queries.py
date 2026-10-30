"""The table app's reads (``READ ONLY``): the zones, the live floor (each table's status computed from
its checks, its block and its holds), the checks of the room with what Sales charged, the waiters, the
setup status and the settings.

Cases from the old module's tests: floor.postgres (natural order, who serves and since when, guests
visible), zones.postgres (occupancy per zone), sessions.postgres (the zone of a check, one check by id),
session_paid_total.postgres (what a check charged, a voided sale does not count), setup_status.postgres
(one table configures the floor, occupancy never unconfigures it) and settings.postgres.
"""

import datetime as dt
import random
import uuid

import pytest
from django.utils import timezone, translation
from live.context import system_context
from live.errors import Conflict, NotFound, PermissionDenied

from .conftest import (
    NOON,
    A,
    add_line,
    charge,
    ctx_for,
    make_customer,
    make_hold,
    make_session,
    make_table,
    make_zone,
    open_check,
    pin_clock,
    run,
)

pytestmark = pytest.mark.django_db

EMPLOYEE = "hub_employee"


@pytest.fixture(autouse=True)
def noon(monkeypatch):
    """The floor reads the business's «today»: these tests read it at a fixed noon, never across midnight."""
    pin_clock(monkeypatch, NOON)


def tables(**params) -> list[dict]:
    return [
        row.model_dump()
        for row in run("table.table.list", {"limit": 100, **params}).rows
    ]


def table_row(table) -> dict:
    return run("table.table.get", {"id": str(table.id)}).model_dump()


def sessions(**params) -> list[dict]:
    return [
        row.model_dump()
        for row in run("table.session.list", {"limit": 100, **params}).rows
    ]


def end_order(order_id, status: str = "completed"):
    """Sales ended the check (charged it whole or voided it): what its own operations leave behind."""
    from apps.sale.models import Order

    Order.objects.filter(pk=order_id).update(status=status, closed_at=timezone.now())


# ── Zones ────────────────────────────────────────────────────────────────────────────────────────


def test_the_zones_come_in_their_order_with_their_tables_and_the_free_ones():
    room = make_zone("Dining room", sort_order=1)
    terrace = make_zone("Terrace", sort_order=0)
    make_zone("Old", is_deleted=True, deleted_at=timezone.now())
    one, two = make_table("1", zone=room), make_table("2", zone=room)
    make_table("3", zone=room, is_active=False)
    make_table("4", zone=room, is_deleted=True, deleted_at=timezone.now())
    make_session(one)
    make_table("5", zone=room, blocked=True)
    del two

    rows = run("table.zone.list", {}).model_dump()["rows"]
    assert [(r["name"], r["table_count"], r["available_count"]) for r in rows] == [
        ("Terrace", 0, 0),
        ("Dining room", 3, 1),
    ]
    assert terrace.id == rows[0]["id"]


def test_the_zones_search_filter_sort_and_page():
    for index, name in enumerate(["Bar", "Terrace", "Garden", "Rooftop"]):
        make_zone(name, sort_order=index, is_active=name != "Garden")
    names = lambda **p: [r.name for r in run("table.zone.list", p).rows]  # noqa: E731
    assert names(search="ter") == ["Terrace"]
    assert names(is_active=False) == ["Garden"]
    assert names(sort="-name") == ["Terrace", "Rooftop", "Garden", "Bar"]
    page = run("table.zone.list", {"limit": 2, "offset": 2})
    assert (page.total, [r.name for r in page.rows]) == (4, ["Garden", "Rooftop"])


def test_a_zone_is_named_by_its_name_and_an_ambiguous_one_says_which():
    zone = make_zone("Terrace")
    make_zone("Terrace bar")
    assert run("table.zone.get", {"zone": "terrace"}).id == zone.id
    with pytest.raises(Conflict) as refused:
        run("table.zone.get", {"zone": "erra"})
    assert refused.value.code == "table.zone_ambiguous"
    with pytest.raises(NotFound) as missing:
        run("table.zone.get", {"id": str(uuid.uuid7())})
    assert missing.value.code == "table.zone_not_found"


# ── The floor: each table's status, computed ─────────────────────────────────────────────────────


def test_a_table_nobody_sits_at_is_available_with_its_seats():
    table = make_table("4", zone=make_zone(), capacity=6)
    row = table_row(table)
    assert (
        row["status"],
        row["capacity"],
        row["guests"],
        row["since"],
        row["checks"],
        row["hold"],
    ) == (
        "available",
        6,
        None,
        None,
        [],
        None,
    )


def test_an_occupied_table_says_who_sits_since_when_and_who_serves():
    # floor.postgres: the plan projects who serves and since when (tables#74, #64) and the guests (#32).
    table = make_table("4", zone=make_zone())
    session = make_session(table, guests_count=3, minutes_ago=35, waiter_name="Luis")
    row = table_row(table)
    assert (row["status"], row["guests"], row["waiter_name"]) == ("occupied", 3, "Luis")
    assert row["since"] == session.opened_at
    assert [check["id"] for check in row["checks"]] == [session.id]


def test_a_table_whose_check_sales_already_ended_is_free_again():
    # Phase 1 has no relay: what Sales did is read on every read (charged whole, or voided).
    table = make_table("4", zone=make_zone())
    order = open_check("Table 4")
    make_session(table, order_id=order.id)
    assert table_row(table)["status"] == "occupied"
    end_order(order.id)
    assert table_row(table)["status"] == "available"


def test_a_check_without_a_sales_check_still_occupies_its_table():
    table = make_table("4", zone=make_zone())
    make_session(table, order_id=None)
    assert table_row(table)["status"] == "occupied"


def test_a_blocked_table_is_blocked_unless_somebody_still_sits_there():
    zone = make_zone()
    blocked = make_table("1", zone=zone, blocked=True)
    seated = make_table("2", zone=zone, blocked=True)
    make_session(seated)
    assert (table_row(blocked)["status"], table_row(seated)["status"]) == (
        "blocked",
        "occupied",
    )


def test_a_reservation_paints_its_table_from_an_hour_before():
    zone = make_zone()
    soon = make_table("1", zone=zone)
    later = make_table("2", zone=zone)
    make_hold(soon, starts_in=30, label="Ana", party_size=4, ref="soon")
    make_hold(later, starts_in=180, label="Luis", ref="later")
    near, far = table_row(soon), table_row(later)
    assert (
        near["status"],
        near["hold"]["label"],
        near["hold"]["party_size"],
        near["hold"]["reserving"],
    ) == (
        "reserved",
        "Ana",
        4,
        True,
    )
    # Later today: the table stays free and shows its next reservation.
    assert (far["status"], far["hold"]["label"], far["hold"]["reserving"]) == (
        "available",
        "Luis",
        False,
    )


def test_late_in_the_evening_today_ends_at_the_business_midnight(monkeypatch):
    # 22:30 in Madrid: a reservation at 23:30 is still today's; one at 00:30 is tomorrow's.
    pin_clock(monkeypatch, dt.datetime(2026, 10, 14, 20, 30, tzinfo=dt.UTC))
    zone = make_zone()
    tonight, after = make_table("1", zone=zone), make_table("2", zone=zone)
    make_hold(tonight, starts_in=60, ref="tonight", label="Ana")
    make_hold(after, starts_in=120, ref="after", label="Luis")
    assert (table_row(tonight)["hold"]["label"], table_row(after)["hold"]) == ("Ana", None)


def test_a_reservation_of_another_day_or_already_over_is_not_shown():
    zone = make_zone()
    tomorrow = make_table("1", zone=zone)
    over = make_table("2", zone=zone)
    hours_to_midnight = (
        timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        + dt.timedelta(days=1)
        - timezone.now()
    )
    make_hold(
        tomorrow,
        starts_in=int(hours_to_midnight.total_seconds() // 60) + 90,
        ref="tomorrow",
    )
    make_hold(over, starts_in=-200, lasts=120, ref="over")
    assert (table_row(tomorrow)["hold"], table_row(tomorrow)["status"]) == (
        None,
        "available",
    )
    assert (table_row(over)["hold"], table_row(over)["status"]) == (None, "available")


def test_a_blocked_table_is_not_painted_reserved_and_an_erased_name_says_so():
    zone = make_zone()
    blocked = make_table("1", zone=zone, blocked=True)
    make_hold(blocked, starts_in=10, ref="b", label="Ana")
    erased = make_table("2", zone=zone)
    make_hold(erased, starts_in=10, ref="e", label="", customer_id=uuid.uuid7())
    assert table_row(blocked)["status"] == "blocked"
    shown = table_row(erased)["hold"]
    assert (shown["label"], shown["erased"]) == ("", True)


def test_the_earliest_reservation_of_today_is_the_one_shown():
    table = make_table("1", zone=make_zone())
    make_hold(table, starts_in=120, ref="second", label="Luis")
    make_hold(table, starts_in=20, ref="first", label="Ana")
    assert table_row(table)["hold"]["label"] == "Ana"


def test_a_split_table_lists_both_checks_oldest_first_with_the_customer_of_each():
    table = make_table("4", zone=make_zone())
    first_order, second_order = open_check("Table 4"), open_check("Table 4")
    first = make_session(table, order_id=first_order.id, minutes_ago=20, guests_count=3)
    second = make_session(
        table, order_id=second_order.id, minutes_ago=5, guests_count=1, split_from=first
    )
    ana = make_customer("Ana García")
    run(
        "customer.order.link",
        {"order_id": str(first_order.id), "customer_id": str(ana.id)},
        system_context(A),
    )
    row = table_row(table)
    assert row["guests"] == 4
    assert [
        (c["id"], c["customer_name"], c["split_from_id"]) for c in row["checks"]
    ] == [
        (first.id, "Ana García", None),
        (second.id, None, first.id),
    ]


# ── The tables list ──────────────────────────────────────────────────────────────────────────────

NATURAL_ORDER = [
    ["S1", "S2", "S3", "S9", "S10", "S11", "S12"],
    ["1", "2", "3", "10", "21"],
    ["Barra 1 Bis", "Barra 2 Bis", "Barra 10 Bis"],
    ["Sala 2 Mesa 2", "Sala 2 Mesa 10", "Sala 10 Mesa 1"],
    ["Barra", "Terraza A", "Terraza B"],
    ["Barra 2 Bis", "Barra 10 Bis", "S1", "S2", "S10", "Terraza A"],
]


@pytest.mark.parametrize("expected", NATURAL_ORDER)
def test_the_tables_come_in_natural_order(expected):
    # The old module's shared corpus (tests/natural-order-corpus.json, tables#68): every run of digits
    # is a number wherever it sits; the rest is text.
    zone = make_zone()
    for number in random.Random(7).sample(expected, len(expected)):
        make_table(number, zone=zone)
    assert [row["number"] for row in tables()] == expected
    assert [row["number"] for row in tables(sort="-number")] == expected[::-1]


def test_the_tables_filter_by_zone_status_search_and_service():
    room, terrace = make_zone("Dining room"), make_zone("Terrace", is_active=False)
    one = make_table("1", zone=room, name="Window")
    make_table("2", zone=room, blocked=True)
    make_table("3", zone=room, is_active=False)
    make_table("4", zone=terrace)
    make_table("5", zone=room, is_deleted=True, deleted_at=timezone.now())
    make_session(one)
    numbers = lambda **p: [row["number"] for row in tables(**p)]  # noqa: E731
    assert numbers() == ["1", "2", "3", "4"]
    assert numbers(zone_id=str(room.id)) == ["1", "2", "3"]
    assert numbers(zone="terrace") == ["4"]
    assert numbers(status="occupied") == ["1"]
    assert numbers(status="blocked") == ["2"]
    assert numbers(search="wind") == ["1"]
    assert numbers(in_service=True) == ["1", "2"]
    assert numbers(is_active=False) == ["3"]


def test_a_table_is_named_by_its_number_and_its_zone_when_the_number_repeats():
    room, terrace = make_zone("Dining room"), make_zone("Terrace")
    inside = make_table("4", zone=room)
    outside = make_table("4", zone=terrace)
    make_table("14", zone=room)
    with pytest.raises(Conflict) as refused:
        run("table.table.get", {"table": "4"})
    assert refused.value.code == "table.table_ambiguous"
    assert "Terrace" in refused.value.message
    assert run("table.table.get", {"table": "4", "zone": "terrace"}).id == outside.id
    assert (
        run("table.table.get", {"table": " 4", "zone": "Dining room"}).id == inside.id
    )
    with pytest.raises(NotFound) as missing:
        run("table.table.get", {"table": "99"})
    assert missing.value.code == "table.table_not_found"


# ── The checks of the room ───────────────────────────────────────────────────────────────────────


def test_a_check_carries_its_table_zone_and_waiter():
    # sessions.postgres: the checks carry their zone (tables#3 b).
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
    # session_paid_total.postgres: what each check charged (tables#96); a voided sale no longer counts.
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


def test_a_check_is_named_by_its_table_and_a_split_table_asks_which():
    table = make_table("4", zone=make_zone())
    first = make_session(table)
    assert run("table.session.get", {"table": "4"}).id == first.id
    make_session(table, split_from=first)
    with pytest.raises(Conflict) as refused:
        run("table.session.get", {"table": "4"})
    assert refused.value.code == "table.session_ambiguous"
    with pytest.raises(NotFound) as missing:
        run("table.session.get", {"id": str(uuid.uuid7())})
    assert missing.value.code == "table.session_not_found"


def test_the_checks_of_a_sales_check_are_found_by_it():
    order = open_check("Table 4")
    session = make_session(make_table("4"), order_id=order.id)
    assert [
        r.id for r in run("table.session.by_order", {"order_id": str(order.id)}).rows
    ] == [session.id]
    assert run("table.session.by_order", {"order_id": str(uuid.uuid7())}).rows == []


def test_the_waiters_are_who_opened_checks_once_each_by_name():
    make_session(make_table("1"), waiter_id="2", waiter_name="Luis")
    make_session(make_table("2"), waiter_id="1", waiter_name="Ana")
    make_session(
        make_table("3"),
        waiter_id="1",
        waiter_name="Ana",
        status="closed",
        closed_at=timezone.now(),
    )
    rows = run("table.waiter.list", {}).rows
    assert [(r.id, r.name) for r in rows] == [("1", "Ana"), ("2", "Luis")]


# ── Setup status and settings ────────────────────────────────────────────────────────────────────


def test_one_table_in_use_sets_the_floor_up_and_occupancy_never_unsets_it():
    # setup_status.postgres: always one answer; occupancy never unconfigures the floor.
    assert run("table.floor.status", {}).model_dump() == {
        "usable_tables": 0,
        "zones": 0,
    }
    zone = make_zone()
    make_table("1", zone=zone, is_active=False)
    assert run("table.floor.status", {}).usable_tables == 0
    table = make_table("2", zone=zone)
    make_session(table)
    assert run("table.floor.status", {}).model_dump() == {
        "usable_tables": 1,
        "zones": 1,
    }


def test_the_settings_are_the_factory_ones_until_saved_and_say_the_business_zone():
    from apps.table.models import TableSettings

    assert run("table.settings.get", {}).model_dump() == {
        "prompt_guests_on_seat": True,
        "timer_warning_minutes": 60,
        "timer_critical_minutes": 90,
        "reserved_lead_minutes": 60,
        "timezone": "Europe/Madrid",
    }
    TableSettings.objects.create(prompt_guests_on_seat=False, timer_warning_minutes=30)
    assert run("table.settings.get", {}).timer_warning_minutes == 30


# ── What names a record on the assistant's card (table-assistant-card) ───────────────────────────


def test_a_table_says_its_number_with_its_zone_in_the_language_of_whoever_reads_it():
    """The number of a table repeats across zones: its label says which one («5 (Terrace)»), as the room's lists do."""
    five, seven = make_table("5", zone=make_zone("Terrace")), make_table("7")
    assert [run("table.table.get", {"id": str(t.id)}).label for t in (five, seven)] == ["5 (Terrace)", "7 (no zone)"]
    assert sorted(row["label"] for row in tables()) == ["5 (Terrace)", "7 (no zone)"]
    with translation.override("es"):
        assert run("table.table.get", {"id": str(seven.id)}).label == "7 (sin zona)"


def test_a_check_says_where_it_is_its_table_with_its_zone_or_parked():
    seated = make_session(make_table("5", zone=make_zone("Terrace")))
    away = make_session(None, status="parked")
    assert [run("table.session.get", {"id": str(s.id)}).label for s in (seated, away)] == ["5 (Terrace)", "Parked"]
    assert sorted(row["label"] for row in sessions()) == ["5 (Terrace)", "Parked"]
    with translation.override("es"):
        assert run("table.session.get", {"id": str(away.id)}).label == "Aparcada"


def test_a_reservation_is_found_by_the_hold_it_keeps_on_its_table():
    """Tables knows a reservation of Reservations only by its hold: the name it paints on the table, while it holds."""
    booking, released, manual = uuid.uuid7(), uuid.uuid7(), uuid.uuid7()
    table = make_table("2", zone=make_zone("Terrace"))
    make_hold(table, source="reservation", ref=str(booking), label="Pedro")
    make_hold(table, source="reservation", ref=str(released), label="", status="released")
    make_hold(table, source="manual", ref=str(manual), label="Luis")
    held = run("table.hold.by_reservation", {"reservation_id": str(booking)})
    assert (held.label, held.table_id, held.source, held.status) == ("Pedro", table.id, "reservation", "held")
    for gone in (released, manual, uuid.uuid7()):
        with pytest.raises(NotFound) as missing:
            run("table.hold.by_reservation", {"reservation_id": str(gone)})
        assert missing.value.code == "table.hold_not_found"


def test_a_hold_whose_time_is_over_holds_nothing_even_before_the_sweep():
    booking = uuid.uuid7()
    make_hold(make_table("2"), source="reservation", ref=str(booking), label="Pedro", starts_in=-180, lasts=60)
    with pytest.raises(NotFound):
        run("table.hold.by_reservation", {"reservation_id": str(booking)})


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


def test_whoever_reads_the_checks_reads_their_lines_and_the_holds_whoever_reads_the_tables():
    booking = uuid.uuid7()
    make_hold(make_table("2"), source="reservation", ref=str(booking), label="Pedro")
    assert run("table.hold.by_reservation", {"reservation_id": str(booking)}, ctx_for(EMPLOYEE)).label == "Pedro"
    for name, data in (
        ("table.hold.by_reservation", {"reservation_id": str(booking)}),
        ("table.session.line", {"id": str(uuid.uuid7())}),
    ):
        with pytest.raises(PermissionDenied):
            run(name, data, ctx_for(permissions=set()))


# ── Permissions ──────────────────────────────────────────────────────────────────────────────────


def test_an_employee_reads_the_room_but_a_stranger_reads_nothing():
    make_table("1")
    assert run("table.table.list", {}, ctx_for(EMPLOYEE)).total == 1
    with pytest.raises(PermissionDenied):
        run("table.table.list", {}, ctx_for(permissions=set()))
