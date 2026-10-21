"""The reads of the kitchen app: the board, what is left to cook, the tickets, a check's tickets, the
stations, the routing, the settings and the history.

Phase 1 has no relay: a round Sales fired shows up on every read (a ticket «not saved yet», with the
number it will have), and what Sales did after (a line voided, the check voided or charged) changes the
state read, without writing (WORKBOOK «A qué reacciona»). Sales and Inventory are the real apps.
"""

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from live.context import system_context
from live.errors import Conflict, NotFound, PermissionDenied

from .conftest import (
    A,
    add_line,
    charge,
    ctx_for,
    fire,
    fired_round,
    make_station,
    open_check,
    route_category,
    route_product,
    run,
)

pytestmark = pytest.mark.django_db


def board(**params):
    return run("kitchen.ticket.board", params)


def void_line(order_id, line_id, reason="Customer changed it"):
    return run(
        "sale.order.void_line",
        {"order_id": str(order_id), "line_id": str(line_id), "reason": reason},
    )


def save_everything():
    """A write of the kitchen: it saves what is pending and what Sales did."""
    return run("kitchen.ticket.sync", {}, system_context(A))


# ── A round fired shows up (KITCHEN-F05, F10) ────────────────────────────────────────────────────


def test_a_round_fired_by_sales_is_on_the_board_before_the_kitchen_writes_anything(
    clock, product
):
    order, lines = fired_round(product, "Burger", "Fries", label="Table 4")
    result = board()
    assert result.cooking_count == 1 and result.ready_count == 0
    ticket = result.cooking[0]
    assert (ticket.id, ticket.saved, ticket.status, ticket.label, ticket.round_no) == (
        lines[0].id,
        False,
        "pending",
        "Table 4",
        1,
    )
    assert (ticket.number, ticket.short_number) == ("20261014-0001", "0001")
    assert ticket.received_at == clock.now and ticket.order_id == order.id
    assert [
        (item.id, item.name, item.quantity, item.status) for item in ticket.items
    ] == [
        (lines[0].id, "Burger", Decimal("1.000"), "pending"),
        (lines[1].id, "Fries", Decimal("1.000"), "pending"),
    ]


def test_each_send_is_a_round_with_the_next_number_of_the_day(clock, product):
    order = open_check("Table 4")
    add_line(order.id, product("Burger"))
    fire(order.id)
    clock.advance(minutes=3)
    add_line(order.id, product("Cake"))
    fire(order.id)
    other = open_check("Table 9")
    clock.advance(minutes=1)
    add_line(other.id, product("Soup"))
    fire(other.id)
    tickets = board().cooking
    assert [(t.number, t.round_no, t.label) for t in tickets] == [
        ("20261014-0001", 1, "Table 4"),
        ("20261014-0002", 2, "Table 4"),
        ("20261014-0003", 1, "Table 9"),
    ]
    # Saving keeps the numbers the board showed.
    save_everything()
    assert [(t.number, t.saved) for t in board().cooking] == [
        ("20261014-0001", True),
        ("20261014-0002", True),
        ("20261014-0003", True),
    ]


def test_the_number_of_the_day_is_the_business_day_in_madrid(clock, product):
    # 23:30 UTC on the 14th is 01:30 on the 15th in Madrid: the old module dated it the 14th.
    clock.now = dt.datetime(2026, 10, 14, 23, 30, tzinfo=dt.UTC)
    fired_round(product, "Burger")
    assert board().cooking[0].number == "20261015-0001"


def test_services_never_reach_the_kitchen(clock, product):
    order = open_check("Table 4")
    add_line(order.id, product("Burger"))
    add_line(
        order.id,
        product("Corkage", product_type="service", tax_category_key="service.generic"),
    )
    fire(order.id)
    [ticket] = board().cooking
    assert [item.name for item in ticket.items] == ["Burger"]


def test_what_was_fired_before_the_kitchen_existed_never_shows(clock, product):
    from apps.kitchen.models import KitchenSettings

    fired_round(product, "Burger")
    KitchenSettings.objects.update(receiving_since=clock.advance(minutes=1))
    assert board().cooking == []


def test_a_round_never_saved_of_a_check_closed_over_a_day_ago_is_no_longer_read(
    clock, product
):
    # Phase 1 reads the rounds it has not saved from Sales on every read: only the ones of checks still
    # open or closed within the last day, so a kitchen that never writes does not read a growing past.
    from apps.kitchen.models import KitchenSettings

    KitchenSettings.objects.update(works_from_screen=False, screen_changed_at=clock.now)
    clock.advance(minutes=1)
    order, _ = fired_round(product, "Burger", label="Yesterday")
    charge(order.id, key="a-day-ago")
    assert [row.label for row in run("kitchen.ticket.list", {}).rows] == ["Yesterday"]
    clock.advance(hours=25)
    assert run("kitchen.ticket.list", {}).rows == []


def test_the_rounds_of_open_checks_are_read_apart_from_the_recently_closed(clock, product):
    # The live board re-runs often: the open checks are found by their status (Sales' index), never with
    # an «open OR closed since» that reads every check ever closed.
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    fired_round(product, "Burger")
    with CaptureQueriesContext(connection) as queries:
        assert len(board().cooking) == 1
    reads = [q["sql"] for q in queries if '"fired_at" IS NOT NULL' in q["sql"]]
    assert len(reads) == 2
    assert not any('"closed_at"' in sql and " OR " in sql for sql in reads)


def test_a_dish_goes_to_its_products_station_else_its_categorys_else_none(
    clock, product, category
):
    grill, bar = make_station("Grill", color="#E03131"), make_station("Bar")
    drinks = category("Drinks")
    burger = product("Burger")
    beer = product("Beer", category_ids=[str(drinks.id)])
    route_product(burger.id, grill)
    route_category(drinks.id, bar)
    order = open_check("Table 4")
    for item in (burger, beer, product("Bread")):
        add_line(order.id, item)
    fire(order.id)
    [ticket] = board().cooking
    assert [(i.name, i.station_name, i.station_color) for i in ticket.items] == [
        ("Burger", "Grill", "#E03131"),
        ("Beer", "Bar", "#F97316"),
        ("Bread", "", ""),
    ]


def test_an_inactive_station_sends_its_dishes_to_the_category_or_none(clock, product):
    grill = make_station("Grill", is_active=False)
    burger = product("Burger")
    route_product(burger.id, grill)
    order = open_check("Table 4")
    add_line(order.id, burger)
    fire(order.id)
    assert board().cooking[0].items[0].station_id is None


# ── The board by station (KITCHEN-F10) ───────────────────────────────────────────────────────────


def test_a_station_sees_only_its_dishes_and_the_tickets_with_something_of_its_own(
    clock, product
):
    grill, bar = make_station("Grill"), make_station("Bar")
    burger, beer = product("Burger"), product("Beer")
    route_product(burger.id, grill)
    route_product(beer.id, bar)
    order = open_check("Table 1")
    add_line(order.id, burger)
    add_line(order.id, beer)
    fire(order.id)
    only_beer = open_check("Table 2")
    add_line(only_beer.id, beer)
    fire(only_beer.id)

    on_grill = board(station="grill")
    assert [t.label for t in on_grill.cooking] == ["Table 1"]
    assert [i.name for i in on_grill.cooking[0].items] == ["Burger"]
    on_bar = board(station=str(bar.id))
    assert [t.label for t in on_bar.cooking] == ["Table 1", "Table 2"]
    assert board(station="none").cooking == []
    # The chips: every station on the board, whatever the filter.
    assert [chip.name for chip in on_grill.stations] == ["Bar", "Grill"]
    with pytest.raises(NotFound):
        board(station="desserts")


def test_a_deleted_station_is_no_longer_found_nor_offered(clock, product):
    # A tablet that remembers a station deleted since is told so (the display goes back to every station)
    # instead of an empty board for ever; the station buttons no longer offer it.
    grill = make_station("Grill")
    burger = product("Burger")
    route_product(burger.id, grill)
    order = open_check("Table 1")
    add_line(order.id, burger)
    add_line(order.id, product("Soup"))
    lines = fire(order.id).order.lines
    run("kitchen.item.bump", {"ticket_id": str(lines[0].id), "station": "grill"})
    run("kitchen.routing.clear", {"product_id": str(burger.id)})
    from apps.kitchen.models import Station

    Station.objects.filter(pk=grill.id).update(is_deleted=True)
    assert [chip.name for chip in board().stations] == [""]
    for said in (str(grill.id), "grill"):
        with pytest.raises(NotFound) as refused:
            board(station=said)
        assert refused.value.code == "kitchen.station_not_found"
    with pytest.raises(NotFound):
        run("kitchen.ticket.all_day", {"station": str(grill.id)})


def test_a_station_that_finished_its_part_no_longer_sees_the_ticket_but_the_pass_does(
    clock, product
):
    grill, bar = make_station("Grill"), make_station("Bar")
    burger, beer = product("Burger"), product("Beer")
    route_product(burger.id, grill)
    route_product(beer.id, bar)
    order = open_check("Table 1")
    add_line(order.id, burger)
    add_line(order.id, beer)
    lines = fire(order.id).order.lines
    run("kitchen.item.bump", {"ticket_id": str(lines[0].id), "station": "bar"})
    assert board(station="bar").cooking == []
    assert [t.status for t in board().cooking] == ["preparing"]
    assert [t.label for t in board(station="grill").cooking] == ["Table 1"]


def test_rush_first_then_vip_then_the_oldest(clock, product):
    for label in ("Old", "Middle", "New"):
        fired_round(product, f"Dish {label}", label=label)
        clock.advance(minutes=1)
    save_everything()
    run("kitchen.ticket.set_rush", {"ticket": "New"})
    from apps.kitchen.models import Ticket

    Ticket.objects.filter(label="Middle").update(priority="vip")
    assert [t.label for t in board().cooking] == ["New", "Middle", "Old"]


def test_the_ready_tickets_wait_at_the_pass_oldest_first(clock, product):
    fired_round(product, "Burger", label="First")
    fired_round(product, "Soup", label="Second")
    run("kitchen.ticket.ready", {"ticket": "Second"})
    clock.advance(minutes=1)
    run("kitchen.ticket.ready", {"ticket": "First"})
    result = board()
    assert result.cooking == [] and [t.label for t in result.ready] == [
        "Second",
        "First",
    ]
    assert result.ready_count == 2


def test_the_cashier_role_may_read_the_board():
    with pytest.raises(PermissionDenied):
        run("kitchen.ticket.board", {}, ctx_for(permissions=set()))
    assert run("kitchen.ticket.board", {}, ctx_for("hub_employee")).cooking == []


# ── What Sales did after the round (KITCHEN-F27, F28, F29) ────────────────────────────────────────


def test_a_line_voided_in_the_till_is_struck_with_its_reason(clock, product):
    order, lines = fired_round(product, "Burger", "Fries")
    void_line(order.id, lines[1].id, "Out of stock")
    [ticket] = board().cooking
    assert [(i.name, i.status, i.void_reason) for i in ticket.items] == [
        ("Burger", "pending", ""),
        ("Fries", "voided", "Out of stock"),
    ]


def test_voiding_the_last_live_dish_cancels_the_round(clock, product):
    order, lines = fired_round(product, "Burger")
    void_line(order.id, lines[0].id)
    assert board().cooking == []
    [row] = run("kitchen.ticket.list", {}).rows
    assert (row.status, row.items_count) == ("cancelled", 0)


def test_voiding_what_was_left_to_cook_sends_the_rest_to_the_pass(clock, product):
    order, lines = fired_round(product, "Burger", "Fries")
    run(
        "kitchen.item.bump",
        {"ticket_id": str(lines[0].id), "item_ids": [str(lines[0].id)]},
    )
    void_line(order.id, lines[1].id)
    result = board()
    assert result.cooking == [] and [t.status for t in result.ready] == ["ready"]


def test_a_check_voided_in_the_till_cancels_its_rounds(clock, product):
    order, _ = fired_round(product, "Burger")
    run("sale.order.void", {"order_id": str(order.id)})
    assert board().cooking == []
    assert run("kitchen.ticket.list", {}).rows[0].status == "cancelled"


def test_charging_serves_what_was_ready_and_leaves_what_is_cooking(clock, product):
    order = open_check("Table 4")
    add_line(order.id, product("Burger"))
    first = fire(order.id).order.lines[0]
    add_line(order.id, product("Cake"))
    fire(order.id)
    run("kitchen.ticket.ready", {"ticket_id": str(first.id)})
    clock.advance(minutes=1)
    charge(order.id, key="ready-and-cooking")
    result = board()
    assert [t.round_no for t in result.cooking] == [2] and result.ready == []
    rows = {row.round_no: row.status for row in run("kitchen.ticket.list", {}).rows}
    assert rows == {1: "served", 2: "pending"}


def test_a_round_that_becomes_ready_after_the_charge_waits_at_the_pass(clock, product):
    order, lines = fired_round(product, "Burger")
    charge(order.id, key="ready-after")
    clock.advance(minutes=2)
    run("kitchen.ticket.ready", {"ticket_id": str(lines[0].id)})
    assert [t.status for t in board().ready] == ["ready"]


def test_charging_serves_a_round_that_went_only_to_paper(clock, product):
    bar = make_station("Bar", destination="printer")
    beer = product("Beer")
    route_product(beer.id, bar)
    order = open_check("Table 4")
    add_line(order.id, beer)
    fire(order.id)
    add_line(order.id, product("Burger"))
    fire(order.id)
    charge(order.id, key="paper-only")
    assert [t.round_no for t in board().cooking] == [2]


def test_a_kitchen_on_paper_serves_every_round_of_a_check_charged_since_it_went_to_paper(
    clock, product
):
    run("kitchen.settings.update", {"works_from_screen": False})
    clock.advance(minutes=1)
    order, _ = fired_round(product, "Burger")
    charge(order.id, key="paper-kitchen")
    assert board().cooking == []


def test_turning_paper_on_does_not_empty_what_was_charged_before(clock, product):
    order, _ = fired_round(product, "Burger")
    charge(order.id, key="before-paper")
    clock.advance(minutes=1)
    run("kitchen.settings.update", {"works_from_screen": False})
    assert [t.label for t in board().cooking] == ["Table 4"]


def test_turning_the_screen_back_on_keeps_served_what_paper_served(clock, product):
    # On paper, a round of a charged check is served (read so, not saved yet): switching the screen back
    # on saves that first, so the round never comes back «To prepare».
    run("kitchen.settings.update", {"works_from_screen": False})
    clock.advance(minutes=1)
    order, _ = fired_round(product, "Burger")
    charge(order.id, key="paper-then-screen")
    assert board().cooking == []
    clock.advance(minutes=1)
    run("kitchen.settings.update", {"works_from_screen": True})
    assert board().cooking == []
    assert [row.status for row in run("kitchen.ticket.list", {}).rows] == ["served"]


def test_a_partial_charge_closes_nothing(clock, product):
    order, lines = fired_round(product, "Burger", "Fries")
    run("kitchen.ticket.ready", {"ticket_id": str(lines[0].id)})
    charge(order.id, key="partial", line_ids=[lines[0].id])
    assert [t.status for t in board().ready] == ["ready"]


def test_merging_two_checks_brings_the_rounds_along(clock, product):
    first, _ = fired_round(product, "Burger", label="Table 5")
    second, _ = fired_round(product, "Soup", label="Table 6")
    save_everything()
    run(
        "sale.order.merge",
        {"from_order_id": str(first.id), "to_order_id": str(second.id)},
    )
    tickets = run("kitchen.ticket.by_order", {"order_id": str(second.id)}).tickets
    assert sorted(t.label for t in tickets) == ["Table 5", "Table 6"]
    assert [t.status for t in board().cooking] == ["pending", "pending"]
    assert run("kitchen.ticket.by_order", {"order_id": str(first.id)}).tickets == []


def test_a_round_not_saved_yet_reads_the_title_of_the_check_it_is_on_now(
    clock, product
):
    # Phase 1: Sales keeps no trace of the check a line was fired from; once saved, the label stays.
    first, _ = fired_round(product, "Burger", label="Table 5")
    clock.advance(seconds=1)
    second, _ = fired_round(product, "Soup", label="Table 6")
    run(
        "sale.order.merge",
        {"from_order_id": str(first.id), "to_order_id": str(second.id)},
    )
    labels = [
        t.label
        for t in run("kitchen.ticket.by_order", {"order_id": str(second.id)}).tickets
    ]
    assert labels == ["Table 6", "Table 6"]


# ── What is left to cook (KITCHEN-F15) ───────────────────────────────────────────────────────────


def test_all_day_adds_up_what_is_left_most_first_per_station(clock, product):
    grill = make_station("Grill")
    burger = product("Burger")
    route_product(burger.id, grill)
    order = open_check("Table 1")
    add_line(order.id, burger, "2")
    add_line(order.id, product("Soup"))
    first = fire(order.id).order.lines
    other = open_check("Table 2")
    add_line(other.id, burger)
    lines = fire(other.id).order.lines
    rows = run("kitchen.ticket.all_day", {}).rows
    assert [(r.name, r.station_name, r.quantity) for r in rows] == [
        ("Burger", "Grill", Decimal("3.000")),
        ("Soup", "", Decimal("1.000")),
    ]
    run("kitchen.item.bump", {"ticket_id": str(lines[0].id)})
    assert [
        (r.name, r.quantity)
        for r in run("kitchen.ticket.all_day", {"station": "grill"}).rows
    ] == [("Burger", Decimal("2.000"))]
    # A dish marked ready in a round that still cooks (the soup is left) leaves the count too.
    run("kitchen.item.bump", {"ticket_id": str(first[0].id), "item_ids": [str(first[0].id)]})
    assert [(r.name, r.quantity) for r in run("kitchen.ticket.all_day", {}).rows] == [
        ("Soup", Decimal("1.000"))
    ]


def test_all_day_is_empty_when_nothing_is_left():
    assert run("kitchen.ticket.all_day", {}).rows == []


# ── The tickets (KITCHEN-F21) ────────────────────────────────────────────────────────────────────


def test_the_list_is_newest_first_with_saved_and_unsaved_together(clock, product):
    fired_round(product, "Burger", label="Old")
    clock.advance(minutes=1)
    fired_round(product, "Soup", label="Served")
    save_everything()
    run("kitchen.ticket.ready", {"ticket": "Served"})
    run("kitchen.ticket.serve", {"ticket": "Served"})
    clock.advance(minutes=1)
    fired_round(product, "Cake", label="New")
    page = run("kitchen.ticket.list", {})
    assert [(r.label, r.status, r.saved) for r in page.rows] == [
        ("New", "pending", False),
        ("Served", "served", True),
        ("Old", "pending", True),
    ]
    assert page.total == 3


def test_the_list_pages_across_saved_and_unsaved(clock, product):
    for n in range(5):
        fired_round(product, f"Dish {n}", label=f"T{n}")
        clock.advance(minutes=1)
        if n in (1, 3):
            save_everything()
            run("kitchen.ticket.cancel", {"ticket": f"T{n}"})
    seen = []
    for offset in (0, 2, 4):
        page = run("kitchen.ticket.list", {"limit": 2, "offset": offset})
        assert page.total == 5
        seen += [r.label for r in page.rows]
    assert seen == ["T4", "T3", "T2", "T1", "T0"]


def test_the_list_searches_the_number_and_the_label_and_filters(clock, product):
    fired_round(product, "Burger", label="Terrace 4")
    fired_round(product, "Soup", label="Bar")
    run("kitchen.ticket.set_rush", {"ticket": "Bar"})
    assert [
        r.label for r in run("kitchen.ticket.list", {"search": "terrace"}).rows
    ] == ["Terrace 4"]
    assert [r.label for r in run("kitchen.ticket.list", {"search": "0002"}).rows] == [
        "Bar"
    ]
    assert [r.label for r in run("kitchen.ticket.list", {"priority": "rush"}).rows] == [
        "Bar"
    ]
    assert run("kitchen.ticket.list", {"status": "served"}).rows == []
    assert [r.number for r in run("kitchen.ticket.list", {"sort": "number"}).rows] == [
        "20261014-0001",
        "20261014-0002",
    ]


def test_a_ticket_is_found_by_its_number_or_its_label(clock, product):
    _, lines = fired_round(product, "Burger", label="Table 4")
    fired_round(product, "Soup", label="Table 40")
    assert run("kitchen.ticket.get", {"ticket": "#0001"}).id == lines[0].id
    assert run("kitchen.ticket.get", {"ticket": "20261014-0001"}).id == lines[0].id
    assert run("kitchen.ticket.get", {"ticket": "table 4"}).id == lines[0].id
    assert run("kitchen.ticket.get", {"ticket_id": str(lines[0].id)}).label == "Table 4"
    with pytest.raises(NotFound):
        run("kitchen.ticket.get", {"ticket": "Terrace"})
    with pytest.raises(NotFound):
        run("kitchen.ticket.get", {"ticket_id": str(uuid.uuid7())})


def test_a_round_not_saved_read_by_its_id_says_what_sales_did(clock, product):
    # The detail of a round of a check voided in the till, before the kitchen saved it, reads «Cancelled».
    order, lines = fired_round(product, "Burger")
    run("sale.order.void", {"order_id": str(order.id)})
    ticket = run("kitchen.ticket.get", {"ticket_id": str(lines[0].id)})
    assert (ticket.saved, ticket.status, ticket.items[0].status) == (False, "cancelled", "cancelled")


def test_two_tickets_with_the_same_label_ask_which_one(clock, product):
    fired_round(product, "Burger", label="Table 4")
    clock.advance(minutes=1)
    order = open_check("Table 4")
    add_line(order.id, product("Soup"))
    fire(order.id)
    with pytest.raises(Conflict) as refused:
        run("kitchen.ticket.get", {"ticket": "Table 4"})
    assert refused.value.code == "kitchen.ticket_ambiguous"
    assert "#0001" in refused.value.message and "#0002" in refused.value.message


def test_the_tickets_of_a_check_newest_round_first(clock, product):
    order = open_check("Table 4")
    add_line(order.id, product("Burger"))
    fire(order.id)
    clock.advance(minutes=1)
    add_line(order.id, product("Cake"))
    fire(order.id)
    fired_round(product, "Soup", label="Other")
    tickets = run("kitchen.ticket.by_order", {"order_id": str(order.id)}).tickets
    assert [(t.round_no, t.items[0].name) for t in tickets] == [
        (2, "Cake"),
        (1, "Burger"),
    ]


def test_a_check_reads_the_numbers_the_board_shows_before_anything_is_saved(
    clock, product
):
    # Table 9 sends at 12:00 and Table 4 at 12:01, none saved: the board says #0001 and #0002, and so does
    # the check of Table 4 (it is numbered among every round, not only its own).
    nine, _ = fired_round(product, "Soup", label="Table 9")
    clock.advance(minutes=1)
    four, _ = fired_round(product, "Burger", label="Table 4")
    on_board = {t.label: t.number for t in board().cooking}
    assert on_board == {"Table 9": "20261014-0001", "Table 4": "20261014-0002"}
    [ticket] = run("kitchen.ticket.by_order", {"order_id": str(four.id)}).tickets
    assert ticket.number == "20261014-0002"
    [ticket] = run("kitchen.ticket.by_order", {"order_id": str(nine.id)}).tickets
    assert ticket.number == "20261014-0001"


# ── Stations, routing, settings, history ─────────────────────────────────────────────────────────


def test_the_stations_say_what_they_have_in_progress_and_their_routes(
    clock, product, category
):
    grill = make_station("Grill", sort_order=1)
    make_station("Bar", sort_order=2, is_active=False)
    burger = product("Burger")
    route_product(burger.id, grill)
    route_category(category("Mains").id, grill)
    order = open_check("Table 4")
    add_line(order.id, burger, "2")
    add_line(order.id, burger)
    fire(order.id)
    page = run("kitchen.station.list", {})
    assert [(s.name, s.in_progress, s.routes, s.is_active) for s in page.rows] == [
        ("Grill", 2, 2, True),
        ("Bar", 0, 0, False),
    ]
    assert [s.name for s in run("kitchen.station.list", {"search": "gri"}).rows] == [
        "Grill"
    ]
    assert [s.name for s in run("kitchen.station.list", {"is_active": False}).rows] == [
        "Bar"
    ]


def test_the_routing_lists_products_and_categories_with_their_station(
    product, category
):
    grill = make_station("Grill")
    route_product(product("Burger").id, grill)
    route_category(category("Mains").id, grill)
    rows = run("kitchen.routing.list", {}).rows
    assert [(r.kind, r.target_name, r.station_name) for r in rows] == [
        ("category", "Mains", "Grill"),
        ("product", "Burger", "Grill"),
    ]
    assert [
        r.target_name for r in run("kitchen.routing.list", {"search": "burg"}).rows
    ] == ["Burger"]


def test_the_settings_are_the_factory_ones_with_the_business_zone():
    result = run("kitchen.settings.get", {})
    assert (
        result.warning_minutes,
        result.critical_minutes,
        result.sound_tone,
        result.timezone,
    ) == (
        15,
        30,
        "chime",
        "Europe/Madrid",
    )


def test_the_settings_are_the_factory_ones_without_a_row():
    from apps.kitchen.models import KitchenSettings

    KitchenSettings.objects.all().delete()
    assert run("kitchen.settings.get", {}).works_from_screen is True


def test_the_history_is_newest_first_with_who_and_which_dish(clock, product):
    _, lines = fired_round(product, "Burger", label="Table 4")
    clock.advance(minutes=1)
    run("kitchen.item.bump", {"ticket_id": str(lines[0].id)}, ctx_for(actor="marta"))
    page = run("kitchen.log.list", {})
    assert [(r.action, r.ticket_number, r.item_name, r.actor) for r in page.rows] == [
        ("ready", "20261014-0001", "", "marta"),
        ("item_ready", "20261014-0001", "Burger", "marta"),
        ("started", "20261014-0001", "", "marta"),
        ("received", "20261014-0001", "", ""),
    ]
    assert page.rows[-1].created_at == clock.now - dt.timedelta(minutes=1)
    assert [r.action for r in run("kitchen.log.list", {"action": "received"}).rows] == [
        "received"
    ]
    assert run("kitchen.log.list", {"search": "0001"}).total == 4
    assert run("kitchen.log.list", {"date_from": "2026-10-15"}).rows == []
    assert run("kitchen.log.list", {"date_to": "2026-10-14"}).total == 4


def test_the_history_pages_and_finds_a_reason_by_its_words(clock, product):
    """KITCHEN-F25: ``limit`` and ``offset`` page it newest first (kitchen#1); the search finds the words of a
    reason, in any case (kitchen#113)."""
    _, lines = fired_round(product, "Burger", label="Table 4")
    clock.advance(minutes=1)
    run("kitchen.ticket.cancel", {"ticket_id": str(lines[0].id), "reason": "Customer left"})
    every = [r.action for r in run("kitchen.log.list", {}).rows]
    assert every == ["cancelled", "received"]
    first = run("kitchen.log.list", {"limit": 1})
    second = run("kitchen.log.list", {"limit": 1, "offset": 1})
    assert (first.total, [r.action for r in first.rows]) == (2, ["cancelled"])
    assert (second.total, [r.action for r in second.rows]) == (2, ["received"])
    found = run("kitchen.log.list", {"search": "customer LEFT"})
    assert [(r.action, r.notes) for r in found.rows] == [("cancelled", "Customer left")]


def test_the_history_names_who_did_it_by_their_name_never_their_session_id(clock, product, django_user_model):
    """KITCHEN-F25: «Who» is the person as they read themselves (name, else e-mail), not the username of their
    session (``saas:<id>``); the system stays empty and a name the Hub does not know stays as it was saved."""
    marta = django_user_model.objects.create_user(
        "saas:77", email="marta@example.com", first_name="Marta", last_name="Ruiz"
    )
    _, lines = fired_round(product, "Burger", label="Table 4")
    run("kitchen.ticket.start", {"ticket_id": str(lines[0].id)}, ctx_for(actor="luis"))
    run("kitchen.ticket.cancel", {"ticket_id": str(lines[0].id), "reason": "Left"}, ctx_for(actor=marta))
    rows = run("kitchen.log.list", {}).rows
    assert [(r.action, r.actor) for r in rows] == [
        ("cancelled", "Marta Ruiz"),
        ("started", "luis"),
        ("received", ""),
    ]


def test_the_history_needs_its_permission():
    with pytest.raises(PermissionDenied):
        run("kitchen.log.list", {}, ctx_for(permissions={"kitchen.view_ticket"}))
