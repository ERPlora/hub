"""The table app's service writes: seating, closing, moving, joining and splitting the checks of the room,
with the real Sales app (each check of a table is an open check of Sales, opened, retitled, split and
merged by Sales' own operations in the same transaction).

Cases from the old module's tests: session_history.hub (opening occupies, closing frees, transferring
moves the occupation instead of doubling it, parking frees without closing, restoring occupies its new
table, half of a split table moved or merged keeps it occupied, moving the only check frees it),
session_history.postgres (one live stretch per check; parking ends it and restoring opens the next),
sessions.postgres (the waiter follows the check through its moves), floor.postgres (the transfer repoints
the order, split and merge keep the check, guests visible and correctable) and write_gates.postgres (a
check no longer open refuses the write; closing by hand must name the bill the check carries).
"""

import uuid

import pytest
from django.utils import timezone
from live.errors import Conflict, NotFound, OperationError, PermissionDenied
from live.models import OutboxEvent

from apps.sale.models import Order
from apps.table.models import Hold, SessionMove, Table, TableSession

from .conftest import (
    add_line,
    charge,
    ctx_for,
    make_customer,
    make_hold,
    make_session,
    make_table,
    make_zone,
    open_check,
    run,
)

pytestmark = pytest.mark.django_db

EMPLOYEE = "hub_employee"
MANAGER = "hub_manager"


def names(prefix: str = "table.") -> list[str]:
    return list(
        OutboxEvent.objects.filter(name__startswith=prefix)
        .order_by("created_at", "id")
        .values_list("name", flat=True)
    )


def status(table) -> str:
    return run("table.table.get", {"id": str(table.id)}).status


def seat(table, **more):
    return run("table.session.open", {"table_id": str(table.id), **more})


def order_of(session) -> Order:
    return Order.objects.get(pk=session.order_id)


@pytest.fixture
def room():
    return make_zone("Dining room")


# ── Seating (TABLE-F10, F12, F28, F32) ───────────────────────────────────────────────────────────


def test_seating_occupies_the_table_and_opens_its_check_in_sales(room):
    table = make_table("4", zone=room, capacity=4)
    session = seat(table, guests_count=3)
    assert (
        session.status,
        session.table_number,
        session.guests_count,
        session.waiter_name,
    ) == ("open", "4", 3, "tester")
    order = order_of(session)
    assert (order.status, order.label) == ("open", "Table 4")
    assert status(table) == "occupied"
    move = SessionMove.objects.get(session_id=session.id)
    assert (move.table_id, move.assignment_reason, move.released_at) == (
        table.id,
        "opened",
        None,
    )
    assert names() == ["table.session.opened"]
    assert names("sale.") == ["sale.order.opened"]


def test_the_check_is_titled_in_the_language_of_whoever_seats():
    make_table("4")
    session = run("table.session.open", {"table": "4"}, ctx_for(language="es"))
    assert order_of(session).label == "Mesa 4"


def test_without_guests_the_table_seats_its_capacity_or_the_reservations_party(room):
    plain = make_table("1", zone=room, capacity=6)
    booked = make_table("2", zone=room, capacity=6)
    make_hold(booked, starts_in=15, party_size=3, label="Ana")
    assert seat(plain).guests_count == 6
    assert seat(booked).guests_count == 3


def test_a_waiter_seats_and_the_waiter_is_who_seats(make_user):
    luis = make_user("luis", role="hub_employee")
    luis.first_name, luis.last_name = "Luis", "Pérez"
    luis.save()
    make_table("4")
    session = run("table.session.open", {"table": "4"}, ctx_for(EMPLOYEE, actor=luis))
    assert (session.waiter_id, session.waiter_name) == (str(luis.pk), "Luis Pérez")


def test_a_taken_blocked_or_inactive_table_is_not_seated(room):
    taken = make_table("1", zone=room)
    seat(taken)
    blocked = make_table("2", zone=room, blocked=True)
    idle = make_table("3", zone=room, is_active=False)
    closed_zone = make_table("4", zone=make_zone("Terrace", is_active=False))
    for table in (taken, blocked, idle, closed_zone):
        with pytest.raises(Conflict) as refused:
            seat(table)
        assert refused.value.code == "table.table_not_available", table.number
    assert TableSession.objects.count() == 1
    assert Order.objects.count() == 1


def test_a_table_whose_check_sales_ended_is_seated_again(room):
    table = make_table("4", zone=room)
    first = seat(table)
    Order.objects.filter(pk=first.order_id).update(
        status="completed", closed_at=timezone.now()
    )
    second = seat(table)
    assert TableSession.objects.get(pk=first.id).status == "closed"
    assert TableSession.objects.get(pk=second.id).status == "open"


def test_seating_a_reserved_table_spends_its_reservation_but_not_a_later_one(room):
    # TABLE-F28: only the holds already painting the table Reserved are spent.
    table = make_table("6", zone=room)
    near = make_hold(table, starts_in=20, ref="near", label="Ana")
    later = make_hold(table, starts_in=240, ref="later", label="Luis")
    assert status(table) == "reserved"
    seat(table)
    near.refresh_from_db()
    later.refresh_from_db()
    assert (near.status, near.label) == ("consumed", "")
    assert (later.status, later.label) == ("held", "Luis")


def test_seating_without_saying_the_reservation_spends_every_hold_painting_the_table(room):
    # TABLE-F28 from the floor plan: nobody says whose party sits, so every hold already painting the table goes.
    table = make_table("6", zone=room)
    first = make_hold(table, starts_in=-50, ref="first", source="reservation")
    second = make_hold(table, starts_in=50, ref="second", source="reservation")
    seat(table)
    assert [
        Hold.objects.get(pk=hold.pk).status for hold in (first, second)
    ] == ["consumed", "consumed"]


def test_seating_a_reservations_party_spends_only_its_own_hold(room):
    # TABLE-F28 from Reservations: A of 19:00 seated late (20:10) leaves B of 21:00 held, still Reserved later.
    table = make_table("6", zone=room, capacity=6)
    ana, bea = str(uuid.uuid7()), str(uuid.uuid7())
    first = make_hold(table, starts_in=-50, ref=ana, source="reservation", party_size=2, label="Ana")
    second = make_hold(table, starts_in=50, ref=bea, source="reservation", party_size=4, label="Bea")
    session = seat(table, reservation_id=ana)
    assert session.guests_count == 2
    first.refresh_from_db()
    second.refresh_from_db()
    assert (first.status, first.label) == ("consumed", "")
    assert (second.status, second.label) == ("held", "Bea")


def test_without_guests_a_reservations_party_seats_its_own_party(room):
    table = make_table("6", zone=room, capacity=6)
    make_hold(table, starts_in=-50, ref=str(uuid.uuid7()), source="reservation", party_size=2)
    bea = str(uuid.uuid7())
    make_hold(table, starts_in=50, ref=bea, source="reservation", party_size=4)
    assert seat(table, reservation_id=bea).guests_count == 4


def test_seating_a_reservation_that_holds_nothing_there_spends_no_hold(room):
    table = make_table("6", zone=room)
    mine = str(uuid.uuid7())
    hold = make_hold(table, starts_in=20, ref=str(uuid.uuid7()), source="reservation")
    by_hand = make_hold(table, starts_in=20, ref=mine, source="manual")
    seat(table, reservation_id=mine)
    assert [Hold.objects.get(pk=row.pk).status for row in (hold, by_hand)] == ["held", "held"]


def test_a_party_seated_hours_before_a_reservation_does_not_spend_it(room):
    table = make_table("6", zone=room)
    hold = make_hold(table, starts_in=300, ref="night")
    seat(table)
    hold.refresh_from_db()
    assert hold.status == "held"


def test_an_open_check_is_brought_to_a_table_and_takes_its_title(room):
    bar = open_check("Ana — bar")
    table = make_table("4", zone=room)
    session = seat(table, order_id=str(bar.id))
    assert session.order_id == bar.id
    assert Order.objects.get(pk=bar.id).label == "Table 4"
    assert Order.objects.count() == 1


def test_the_till_seats_its_check_on_screen_and_follows_its_table(room, product):
    # Sales' «Choose table» (TABLE-F12, F13, F24 from the till), as the waiter: the check on screen,
    # with its round, is seated without asking the guests; the till then follows its table by order,
    # takes the table away (park) and seats it again at another one. One check of Sales throughout.
    waiter = ctx_for(EMPLOYEE)
    check = open_check(ctx=waiter)
    add_line(check.id, product(), quantity="2", ctx=waiter)
    four, seven = (
        make_table("4", zone=room, capacity=4),
        make_table("7", zone=room, capacity=6),
    )

    seated = run(
        "table.session.open",
        {"table_id": str(four.id), "order_id": str(check.id)},
        waiter,
    )

    def followed():
        rows = run("table.session.by_order", {"order_id": str(check.id)}, waiter).rows
        return [(r.id, r.table_id, r.status) for r in rows]

    assert (seated.order_id, seated.guests_count) == (check.id, 4)
    assert followed() == [(seated.id, four.id, "open")]
    assert (order_of(seated).label, order_of(seated).lines.count()) == ("Table 4", 1)
    parked = run("table.session.park", {"id": str(seated.id)}, waiter)
    assert followed() == [(parked.id, None, "parked")]
    assert status(four) == "available"
    again = run(
        "table.session.restore",
        {"id": str(parked.id), "table_id": str(seven.id)},
        waiter,
    )
    assert followed() == [(again.id, seven.id, "open")]
    assert (order_of(again).label, order_of(again).lines.count()) == ("Table 7", 1)
    assert Order.objects.count() == 1


def test_a_check_that_is_not_open_or_already_at_a_table_is_not_brought(room):
    paid = open_check("Paid")
    Order.objects.filter(pk=paid.id).update(status="completed")
    with pytest.raises(Conflict) as refused:
        seat(make_table("1", zone=room), order_id=str(paid.id))
    assert refused.value.code == "table.order_not_open"
    seated = seat(make_table("2", zone=room))
    with pytest.raises(Conflict) as elsewhere:
        seat(make_table("3", zone=room), order_id=str(seated.order_id))
    assert elsewhere.value.code == "table.order_elsewhere"
    assert "2" in elsewhere.value.message


def test_seating_with_a_customer_links_her_to_the_check(room):
    ana = make_customer("Ana García", phone="+34600111222")
    session = seat(make_table("4", zone=room), customer="Ana García")
    assert (session.customer_id, session.customer_name) == (ana.id, "Ana García")


def test_two_tables_seated_get_two_checks_and_the_same_table_twice_does_not():
    table = make_table("4")
    seat(table)
    with pytest.raises(Conflict):
        seat(table)
    assert TableSession.objects.filter(status="open").count() == 1


# ── Closing by hand (TABLE-F21) ──────────────────────────────────────────────────────────────────


def test_a_table_whose_check_has_something_ordered_is_not_closed_by_hand(room, product):
    table = make_table("4", zone=room)
    session = seat(table)
    add_line(session.order_id, product())
    with pytest.raises(Conflict) as refused:
        run(
            "table.session.close",
            {"id": str(session.id), "order_id": str(session.order_id)},
        )
    assert refused.value.code == "table.session_bill_open"
    assert status(table) == "occupied"


def test_a_table_whose_check_is_empty_closes_and_its_empty_check_is_voided(room):
    # A party that leaves without ordering does not need a manager: Sales lets whoever builds checks void
    # an empty one (no lines, no charges) without the void permission.
    table = make_table("4", zone=room)
    session = seat(table, notes="Window")
    out = run("table.session.close", {"table": "4", "notes": "Left"}, ctx_for(EMPLOYEE))
    assert (out.status, out.notes) == ("closed", "Window\nLeft")
    assert out.closed_at is not None
    assert order_of(session).status == "voided"
    assert status(table) == "available"
    assert SessionMove.objects.get(session_id=session.id).release_reason == "closed"
    assert names() == ["table.session.opened", "table.session.closed"]


def test_closing_an_empty_check_voids_it_with_the_waiters_own_session_never_more(
    room, monkeypatch
):
    # Tables never widens a caller's permissions: Sales decides with the waiter's real context.
    from apps.table import services

    seen = []
    original = services.call_app

    def spy(ctx, name, data):
        seen.append((name, ctx.permissions))
        return original(ctx, name, data)

    monkeypatch.setattr(services, "call_app", spy)
    seat(make_table("4", zone=room))
    waiter = ctx_for(EMPLOYEE)
    run("table.session.close", {"table": "4"}, waiter)
    ((name, permissions),) = [call for call in seen if call[0] == "sale.order.void"]
    assert "sale.void_sale" not in permissions
    assert permissions == waiter.permissions


def test_closing_must_name_the_bill_the_check_carries(room):
    session = seat(make_table("4", zone=room))
    with pytest.raises(Conflict) as refused:
        run(
            "table.session.close",
            {"id": str(session.id), "order_id": str(uuid.uuid7())},
        )
    assert refused.value.code == "table.session_bill_mismatch"


def test_a_check_no_longer_open_refuses_every_service_write(room):
    session = seat(make_table("4", zone=room))
    run("table.session.close", {"id": str(session.id)})
    for name, more in (
        ("table.session.close", {}),
        ("table.session.set_guests", {"guests_count": 2}),
        ("table.session.park", {}),
        ("table.session.split", {}),
        ("table.session.transfer", {"to_table": "5"}),
    ):
        make_table("5", zone=room) if name == "table.session.transfer" else None
        with pytest.raises(Conflict) as refused:
            run(name, {"id": str(session.id), **more})
        assert refused.value.code == "table.session_not_active", name


def test_a_check_closed_by_sales_meanwhile_refuses_the_close():
    session = seat(make_table("4"))
    Order.objects.filter(pk=session.order_id).update(
        status="completed", closed_at=timezone.now()
    )
    with pytest.raises(Conflict) as refused:
        run("table.session.close", {"id": str(session.id)})
    assert refused.value.code == "table.session_not_active"
    # A refused write changes nothing; the read already says what Sales did.
    assert run("table.session.get", {"id": str(session.id)}).status == "closed"


# ── Guests (TABLE-F14) ───────────────────────────────────────────────────────────────────────────


def test_the_guests_of_an_occupied_table_are_corrected(room):
    table = make_table("4", zone=room, capacity=4)
    seat(table, guests_count=2)
    out = run(
        "table.session.set_guests", {"table": "4", "guests_count": 6}, ctx_for(EMPLOYEE)
    )
    assert out.guests_count == 6
    assert run("table.table.get", {"id": str(table.id)}).guests == 6
    assert names()[-1] == "table.session.updated"


# ── Transfer (TABLE-F15) ─────────────────────────────────────────────────────────────────────────


def test_a_transfer_moves_the_occupation_and_the_check_with_its_waiter_and_title(room):
    origin, target = make_table("4", zone=room), make_table("6", zone=room)
    hold = make_hold(target, starts_in=10, ref="near")
    session = seat(origin, guests_count=3, notes="Allergy: nuts")
    moved = run(
        "table.session.transfer", {"table": "4", "to_table": "6"}, ctx_for(EMPLOYEE)
    )
    old = TableSession.objects.get(pk=session.id)
    assert (old.status, old.order_id, old.closed_at is not None) == (
        "transferred",
        None,
        True,
    )
    assert (
        moved.table_number,
        moved.order_id,
        moved.guests_count,
        moved.notes,
        moved.waiter_name,
    ) == (
        "6",
        session.order_id,
        3,
        "Allergy: nuts",
        "tester",
    )
    assert TableSession.objects.get(pk=moved.id).transferred_from_id == session.id
    assert (status(origin), status(target)) == ("available", "occupied")
    assert Order.objects.get(pk=session.order_id).label == "Table 6"
    hold.refresh_from_db()
    assert hold.status == "consumed"
    assert [
        (m.table.number, m.assignment_reason, m.release_reason)
        for m in SessionMove.objects.order_by("assigned_at", "id")
    ] == [
        ("4", "opened", "transferred"),
        ("6", "transferred", ""),
    ]
    assert names()[-1] == "table.session.transferred"


def test_a_transfer_to_a_taken_table_is_refused(room):
    seat(make_table("4", zone=room))
    seat(make_table("6", zone=room))
    with pytest.raises(Conflict) as refused:
        run("table.session.transfer", {"table": "4", "to_table": "6"})
    assert refused.value.code == "table.table_not_available"


def test_moving_half_of_a_split_table_keeps_it_occupied_and_moving_the_only_check_frees_it(
    room,
):
    origin, target, third = (
        make_table("4", zone=room),
        make_table("6", zone=room),
        make_table("8", zone=room),
    )
    first = seat(origin)
    second = run("table.session.split", {"id": str(first.id)}).new_session
    run("table.session.transfer", {"id": str(second.id), "to_table_id": str(target.id)})
    assert (status(origin), status(target)) == ("occupied", "occupied")
    run("table.session.transfer", {"id": str(first.id), "to_table_id": str(third.id)})
    assert status(origin) == "available"


# ── Merge (TABLE-F16) ────────────────────────────────────────────────────────────────────────────


def test_merging_joins_the_lines_in_sales_and_frees_the_origin(room, product):
    coffee = product()
    origin, target = make_table("4", zone=room), make_table("6", zone=room)
    source = seat(origin)
    staying = seat(target)
    add_line(source.order_id, coffee)
    add_line(staying.order_id, coffee)
    out = run(
        "table.session.merge", {"table": "4", "into_table": "6"}, ctx_for(EMPLOYEE)
    )
    merged = TableSession.objects.get(pk=source.id)
    # The absorbed check keeps its (voided) check of Sales: what it charged before still counts as its own.
    assert (merged.status, merged.merged_into_id, merged.order_id) == (
        "merged",
        staying.id,
        source.order_id,
    )
    assert out.id == staying.id
    assert order_of(staying).lines.count() == 2
    assert Order.objects.get(pk=source.order_id).status == "voided"
    assert (status(origin), status(target)) == ("available", "occupied")
    assert "table.session.merged" in names()
    assert "sale.order.merged" in names("sale.")


def test_merging_into_a_check_without_a_sales_check_hands_it_over(room):
    origin, target = make_table("4", zone=room), make_table("6", zone=room)
    source = seat(origin)
    staying = make_session(target, order_id=None)
    run("table.session.merge", {"id": str(source.id), "into_table_id": str(target.id)})
    staying.refresh_from_db()
    assert staying.order_id == source.order_id
    assert Order.objects.get(pk=source.order_id).label == "Table 6"


def test_merging_into_a_free_table_or_into_itself_is_refused(room):
    source = seat(make_table("4", zone=room))
    make_table("6", zone=room)
    with pytest.raises(Conflict) as free:
        run("table.session.merge", {"id": str(source.id), "into_table": "6"})
    assert free.value.code == "table.nothing_to_merge"
    with pytest.raises(Conflict) as itself:
        run(
            "table.session.merge",
            {"id": str(source.id), "into_session_id": str(source.id)},
        )
    assert itself.value.code == "table.nothing_to_merge"


def test_the_two_checks_of_a_split_table_merge_back_into_one(room, product):
    table = make_table("4", zone=room)
    first = seat(table)
    line = add_line(first.order_id, product()).lines[0]
    second = run(
        "table.session.split", {"id": str(first.id), "line_ids": [str(line.id)]}
    ).new_session
    run("table.session.merge", {"id": str(second.id), "into_session_id": str(first.id)})
    assert order_of(first).lines.count() == 1
    assert run("table.table.get", {"id": str(table.id)}).checks[0].id == first.id
    assert len(run("table.table.get", {"id": str(table.id)}).checks) == 1


def test_merging_half_of_a_split_table_keeps_it_occupied(room):
    origin, target = make_table("4", zone=room), make_table("6", zone=room)
    first = seat(origin)
    seat(target)
    run("table.session.split", {"id": str(first.id)})
    run("table.session.merge", {"id": str(first.id), "into_table": "6"})
    assert status(origin) == "occupied"


# ── Split (TABLE-F17) ────────────────────────────────────────────────────────────────────────────


def test_splitting_opens_a_second_check_at_the_table_and_moves_the_lines_in_sales(
    room, product
):
    coffee = product()
    table = make_table("4", zone=room)
    first = seat(table, guests_count=4)
    keep = add_line(first.order_id, coffee).lines[0]
    move = add_line(first.order_id, coffee).lines[1]
    out = run(
        "table.session.split",
        {"table": "4", "line_ids": [str(move.id)]},
        ctx_for(EMPLOYEE),
    )
    new = out.new_session
    assert (new.table_number, new.guests_count, new.split_from_id, new.waiter_name) == (
        "4",
        1,
        first.id,
        "tester",
    )
    assert [line.id for line in order_of(first).lines.all()] == [keep.id]
    assert [line.id for line in Order.objects.get(pk=new.order_id).lines.all()] == [
        move.id
    ]
    assert Order.objects.get(pk=new.order_id).label == "Table 4"
    assert len(run("table.table.get", {"id": str(table.id)}).checks) == 2
    assert SessionMove.objects.get(session_id=new.id).assignment_reason == "split"
    assert "table.session.split" in names()


def test_charging_one_half_of_a_split_table_leaves_the_other_seated(room):
    table = make_table("4", zone=room)
    first = seat(table)
    second = run("table.session.split", {"id": str(first.id)}).new_session
    Order.objects.filter(pk=second.order_id).update(
        status="completed", closed_at=timezone.now()
    )
    row = run("table.table.get", {"id": str(table.id)})
    assert (row.status, [c.id for c in row.checks]) == ("occupied", [first.id])


# ── Park and restore (TABLE-F13, F24) ────────────────────────────────────────────────────────────


def test_parking_frees_the_table_without_closing_the_check(room):
    table = make_table("4", zone=room)
    session = seat(table, guests_count=3)
    out = run("table.session.park", {"table": "4"}, ctx_for(EMPLOYEE))
    assert (out.status, out.table_id, out.guests_count, out.order_id) == (
        "parked",
        None,
        3,
        session.order_id,
    )
    assert order_of(session).status == "open"
    assert status(table) == "available"
    assert SessionMove.objects.get(session_id=session.id).release_reason == "parked"
    assert names()[-1] == "table.session.parked"


def test_a_parked_check_sits_again_at_a_free_table(room):
    table, other = make_table("4", zone=room), make_table("6", zone=room)
    session = seat(table, guests_count=3)
    run("table.session.park", {"id": str(session.id)})
    make_hold(other, starts_in=10, ref="near")
    out = run(
        "table.session.restore",
        {"id": str(session.id), "table": "6"},
        ctx_for(EMPLOYEE),
    )
    assert (out.status, out.table_number, out.guests_count, out.opened_at) == (
        "open",
        "6",
        3,
        session.opened_at,
    )
    assert status(other) == "occupied"
    assert order_of(session).label == "Table 6"
    assert Hold.objects.get().status == "consumed"
    assert [
        m.assignment_reason
        for m in SessionMove.objects.filter(session_id=session.id).order_by(
            "assigned_at", "id"
        )
    ] == [
        "opened",
        "restored",
    ]


def test_restoring_needs_a_parked_check_and_a_free_table(room):
    session = seat(make_table("4", zone=room))
    with pytest.raises(Conflict) as not_parked:
        run("table.session.restore", {"id": str(session.id), "table": "4"})
    assert not_parked.value.code == "table.session_not_parked"
    run("table.session.park", {"id": str(session.id)})
    seat(make_table("6", zone=room))
    with pytest.raises(Conflict) as taken:
        run("table.session.restore", {"id": str(session.id), "table": "6"})
    assert taken.value.code == "table.table_not_available"


# ── Link an order, delete a check ────────────────────────────────────────────────────────────────


def test_an_open_check_of_sales_is_linked_to_a_table_check_without_one(room):
    table = make_table("4", zone=room)
    session = make_session(table, order_id=None)
    order = open_check("bar")
    out = run(
        "table.session.link_order", {"id": str(session.id), "order_id": str(order.id)}
    )
    assert out.order_id == order.id
    assert Order.objects.get(pk=order.id).label == "Table 4"
    assert names() == ["table.session.updated"]


def test_a_finished_check_is_deleted_from_the_history_by_the_admin_alone(room):
    session = seat(make_table("4", zone=room))
    with pytest.raises(Conflict) as still_open:
        run("table.session.delete", {"id": str(session.id)})
    assert still_open.value.code == "table.session_still_open"
    run("table.session.close", {"id": str(session.id)})
    with pytest.raises(PermissionDenied):
        run("table.session.delete", {"id": str(session.id)}, ctx_for(MANAGER))
    assert run("table.session.delete", {"id": str(session.id)}).id == session.id
    deleted = TableSession.objects.get(pk=session.id)
    assert (deleted.is_deleted, deleted.moves.count()) == (True, 1)
    assert run("table.session.list", {"status": "closed"}).total == 0
    with pytest.raises(NotFound):
        run("table.session.get", {"id": str(session.id)})


def test_closing_by_order_closes_the_checks_of_that_order_as_the_system(room):
    session = seat(make_table("4", zone=room))
    out = run(
        "table.session.close_by_order",
        {"order_id": str(session.order_id)},
        ctx_for(permissions={"*"}),
    )
    assert out.closed == 1
    assert TableSession.objects.get(pk=session.id).status == "closed"


# ── Review fixes: parked checks Sales ended, partial charges kept, split anywhere, all or nothing ──


def _parked_with_ended_order(room, status: str = "completed"):
    session = seat(make_table("4", zone=room))
    run("table.session.park", {"id": str(session.id)})
    Order.objects.filter(pk=session.order_id).update(
        status=status, closed_at=timezone.now()
    )
    return session


def test_a_parked_check_whose_sales_check_ended_is_deleted_like_any_finished_one(room):
    session = _parked_with_ended_order(room)
    assert run("table.session.delete", {"id": str(session.id)}).id == session.id
    assert TableSession.objects.get(pk=session.id).is_deleted is True


def test_a_parked_check_whose_sales_check_ended_is_not_seated_again(room):
    session = _parked_with_ended_order(room, "voided")
    make_table("6", zone=room)
    with pytest.raises(Conflict) as refused:
        run("table.session.restore", {"id": str(session.id), "table": "6"})
    assert refused.value.code == "table.session_not_parked"
    assert run("table.session.get", {"id": str(session.id)}).status == "closed"


def test_closing_by_order_closes_a_parked_check_too(room):
    session = seat(make_table("4", zone=room))
    run("table.session.park", {"id": str(session.id)})
    out = run(
        "table.session.close_by_order",
        {"order_id": str(session.order_id)},
        ctx_for(permissions={"*"}),
    )
    assert out.closed == 1
    closed = TableSession.objects.get(pk=session.id)
    assert (closed.status, closed.table_id) == ("closed", None)


def test_merging_keeps_what_the_absorbed_check_already_charged(room, product):
    # A partial charge before the merge stays on the merged check: «Charged» never loses it.
    coffee = product()
    origin, target = make_table("4", zone=room), make_table("6", zone=room)
    source = seat(origin)
    staying = seat(target)
    paid = add_line(source.order_id, coffee).lines[0]
    add_line(source.order_id, coffee)
    charge(source.order_id, key="merge-partial", line_ids=[paid.id])
    run("table.session.merge", {"id": str(source.id), "into_table_id": str(target.id)})
    merged = TableSession.objects.get(pk=source.id)
    assert (merged.status, merged.order_id) == ("merged", source.order_id)
    assert run("table.session.get", {"id": str(source.id)}).paid_total == 150
    assert run("table.session.get", {"id": str(staying.id)}).paid_total is None
    assert order_of(staying).lines.count() == 1


def test_a_blocked_or_inactive_table_is_split_all_the_same(room):
    # Splitting does not seat anybody new: the table only has to be the check's own.
    table = make_table("4", zone=room)
    first = seat(table)
    Table.objects.filter(pk=table.pk).update(blocked=True, is_active=False)
    new = run("table.session.split", {"id": str(first.id)}).new_session
    assert (new.table_id, new.status) == (table.id, "open")


@pytest.mark.parametrize("said", ["Nobody At All", "García"])
def test_a_customer_that_cannot_be_put_on_the_check_does_not_stop_the_seating(
    room, said
):
    # WORKBOOK TABLE-F32: «Si falla: el motivo de Clientes; la mesa se sienta igual».
    make_customer("Ana García", phone="+34600111222")
    make_customer("Luis García", phone="+34600333444")
    table = make_table("4", zone=room)
    session = seat(table, customer=said)
    assert (session.status, session.customer_id) == ("open", None)
    assert status(table) == "occupied"


def test_a_split_sales_refuses_leaves_the_table_as_it_was(room, product):
    coffee = product()
    table = make_table("4", zone=room)
    first = seat(table)
    other = seat(make_table("6", zone=room))
    foreign = add_line(other.order_id, coffee).lines[0]
    before = (TableSession.objects.count(), SessionMove.objects.count())
    with pytest.raises(OperationError) as refused:
        run("table.session.split", {"id": str(first.id), "line_ids": [str(foreign.id)]})
    assert refused.value.code == "sale.order_changed"
    assert (TableSession.objects.count(), SessionMove.objects.count()) == before
    assert TableSession.objects.get(pk=first.id).status == "open"
    assert len(run("table.table.get", {"id": str(table.id)}).checks) == 1


def test_a_merge_sales_refuses_leaves_both_tables_as_they_were(room, monkeypatch):
    from apps.table import services

    origin, target = make_table("4", zone=room), make_table("6", zone=room)
    source = seat(origin)
    staying = seat(target)
    original = services.call_app

    def refusing(ctx, name, data):
        if name == "sale.order.merge":
            raise Conflict("The check has changed.", code="sale.order_changed")
        return original(ctx, name, data)

    monkeypatch.setattr(services, "call_app", refusing)
    with pytest.raises(Conflict) as refused:
        run(
            "table.session.merge",
            {"id": str(source.id), "into_table_id": str(target.id)},
        )
    assert refused.value.code == "sale.order_changed"
    kept = TableSession.objects.get(pk=source.id)
    assert (kept.status, kept.order_id, kept.merged_into_id) == (
        "open",
        source.order_id,
        None,
    )
    assert SessionMove.objects.get(session_id=source.id).released_at is None
    assert (status(origin), status(target)) == ("occupied", "occupied")
    assert TableSession.objects.get(pk=staying.id).status == "open"
