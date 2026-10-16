"""The writes of the kitchen app: saving the rounds, sending from the till, the tickets' journey, the
dishes, the stations, the routing and the settings, each with its History, its event and its paper.

Sales, Inventory and Printing are the real apps (Printing by the name of its operation, as the kitchen
calls it).
"""

import datetime as dt
import uuid

import pytest
from live.context import system_context
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent

from apps.kitchen.models import KitchenSettings, LogEntry, Station, Ticket, TicketItem

from .conftest import (
    A,
    add_line,
    charge,
    ctx_for,
    fire,
    fired_round,
    make_station,
    open_check,
    route_product,
    run,
)

pytestmark = pytest.mark.django_db

EMPLOYEE = "hub_employee"


def names(prefix: str = "kitchen.") -> list[str]:
    return list(
        OutboxEvent.objects.filter(name__startswith=prefix)
        .order_by("created_at", "id")
        .values_list("name", flat=True)
    )


def payloads(name: str) -> list[dict]:
    return list(
        OutboxEvent.objects.filter(name=name)
        .order_by("created_at", "id")
        .values_list("payload", flat=True)
    )


def log(ticket_id) -> list[tuple[str, str]]:
    return list(
        LogEntry.objects.filter(ticket_id=ticket_id)
        .order_by("created_at", "id")
        .values_list("action", "notes")
    )


def jobs():
    from apps.printing.models import PrintJob

    return list(PrintJob.objects.order_by("created_at", "id"))


def sync():
    return run("kitchen.ticket.sync", {}, system_context(A))


# ── Saving the rounds Sales fired (KITCHEN-F05) ──────────────────────────────────────────────────


def test_a_write_saves_the_rounds_with_the_numbers_and_ids_the_board_showed(
    clock, product
):
    order, lines = fired_round(product, "Burger", "Fries", label="Table 4")
    clock.advance(minutes=4)
    result = sync()
    assert (result.received, result.changed) == (1, 0)
    ticket = Ticket.objects.get()
    assert (ticket.id, ticket.number, ticket.day, ticket.sequence) == (
        lines[0].id,
        "20261014-0001",
        dt.date(2026, 10, 14),
        1,
    )
    assert (
        ticket.order_id,
        ticket.round_no,
        ticket.label,
        ticket.status,
        ticket.waiter,
    ) == (
        order.id,
        1,
        "Table 4",
        "pending",
        "waiter",
    )
    assert ticket.received_at == clock.now - dt.timedelta(minutes=4)
    assert [(i.id, i.sale_line_id, i.name) for i in ticket.items.all()] == [
        (lines[0].id, lines[0].id, "Burger"),
        (lines[1].id, lines[1].id, "Fries"),
    ]
    # «Recibida» at the moment it was sent, not when it was saved.
    entry = LogEntry.objects.get()
    assert (entry.action, entry.created_at) == ("received", ticket.received_at)
    assert payloads("kitchen.ticket.received") == [
        {
            "ticket_id": str(ticket.id),
            "number": ticket.number,
            "order_id": str(order.id),
            "round_no": 1,
        }
    ]
    assert sync().received == 0


def test_the_dishes_keep_the_station_they_went_to(clock, product):
    grill = make_station(
        "Grill", destination="printer", printer_usage="bar", printer_name="Bar printer"
    )
    burger = product("Burger")
    route_product(burger.id, grill)
    order = open_check("Table 4")
    add_line(order.id, burger)
    fire(order.id)
    sync()
    grill.destination = "display"
    grill.save()
    item = TicketItem.objects.get()
    assert (
        item.station_id,
        item.station_name,
        item.destination,
        item.printer_usage,
        item.printer_name,
    ) == (
        grill.id,
        "Grill",
        "printer",
        "bar",
        "Bar printer",
    )


# ── Sending from the till (KITCHEN-F18, F08) ─────────────────────────────────────────────────────


def test_sending_fires_the_check_and_opens_an_urgent_ticket_on_paper(clock, product):
    bar = make_station("Bar", printer_usage="bar")
    screen = make_station("Pastry", destination="display")
    beer, cake = product("Beer"), product("Cake")
    route_product(beer.id, bar)
    route_product(cake.id, screen)
    order = open_check("Table 4")
    for item in (beer, cake, product("Burger")):
        add_line(order.id, item)
    ticket = run(
        "kitchen.ticket.send",
        {"order_id": str(order.id), "channel": "takeaway", "priority": "rush"},
        ctx_for(actor="luis"),
    )
    assert (
        ticket.saved,
        ticket.priority,
        ticket.order_type,
        ticket.waiter,
        ticket.label,
    ) == (
        True,
        "rush",
        "takeaway",
        "luis",
        "Table 4",
    )
    assert ticket.print_error is None
    assert "sale.order.fired" in names("sale.")
    printed = jobs()
    assert sorted((job.usage, job.document_type) for job in printed) == [
        ("bar", "kitchen_order"),
        ("kitchen", "kitchen_order"),
    ]
    sheets = {job.usage: job.document for job in printed}
    assert [item["name"] for item in sheets["bar"]["items"]] == ["Beer"]
    assert [item["name"] for item in sheets["kitchen"]["items"]] == ["Burger"]
    assert sheets["kitchen"]["priority"] == "!! URGENT !!"
    assert (
        sheets["kitchen"]["order_number"],
        sheets["kitchen"]["table"],
        sheets["kitchen"]["waiter"],
    ) == (
        "20261014-0001",
        "Table 4",
        "luis",
    )


def test_sending_with_nothing_pending_is_refused_by_sales(clock, product):
    order, _ = fired_round(product, "Burger")
    with pytest.raises(Conflict) as refused:
        run("kitchen.ticket.send", {"order_id": str(order.id)})
    assert refused.value.code == "sale.nothing_to_fire"


def test_sending_only_services_is_refused_and_sends_nothing(clock, product):
    from apps.sale.models import OrderLine

    order = open_check("Table 4")
    add_line(
        order.id,
        product("Corkage", product_type="service", tax_category_key="service.generic"),
    )
    with pytest.raises(Conflict) as refused:
        run("kitchen.ticket.send", {"order_id": str(order.id)})
    assert refused.value.code == "kitchen.nothing_to_cook"
    assert (
        str(refused.value.message)
        == "Nothing on this check is cooked: services do not go to the kitchen."
    )
    assert not OrderLine.objects.filter(
        order_id=order.id, fired_at__isnull=False
    ).exists()


def test_receiving_the_fire_event_opens_the_ticket_once_with_what_only_the_send_knows(
    clock, product
):
    order = open_check("Table 4")
    add_line(order.id, product("Burger"))
    fired = fire(order.id, priority="urgent", channel="delivery")
    [payload] = payloads("sale.order.fired")
    first = run("kitchen.ticket.receive", payload, system_context(A)).ticket
    again = run("kitchen.ticket.receive", payload, system_context(A)).ticket
    assert first.id == again.id == fired.order.lines[0].id
    assert (first.priority, first.order_type, first.waiter) == (
        "rush",
        "delivery",
        "waiter",
    )
    assert Ticket.objects.count() == 1 and len(jobs()) == 1


def test_receiving_a_round_the_kitchen_already_saved_gives_it_what_the_send_said(
    clock, product
):
    order = open_check("")
    add_line(order.id, product("Burger"))
    fire(order.id, priority="urgent", channel="takeaway", label="Pickup Ana")
    sync()
    assert Ticket.objects.get().priority == "normal"
    [payload] = payloads("sale.order.fired")
    ticket = run("kitchen.ticket.receive", payload, system_context(A)).ticket
    assert (ticket.priority, ticket.order_type, ticket.label) == (
        "rush",
        "takeaway",
        "Pickup Ana",
    )


def test_a_round_of_services_only_opens_nothing(clock, product):
    order = open_check("Table 4")
    add_line(
        order.id,
        product("Corkage", product_type="service", tax_category_key="service.generic"),
    )
    fire(order.id)
    [payload] = payloads("sale.order.fired")
    assert run("kitchen.ticket.receive", payload, system_context(A)).ticket is None
    assert not Ticket.objects.exists()


def test_without_printing_permission_the_ticket_opens_and_says_why_no_paper(
    clock, product
):
    order = open_check("Table 4")
    add_line(order.id, product("Burger"))
    permissions = {"kitchen.add_ticket", "sale.add_sale", "sale.view_sale"}
    ticket = run(
        "kitchen.ticket.send",
        {"order_id": str(order.id)},
        ctx_for(permissions=permissions),
    )
    assert ticket.saved and "printing.print" in ticket.print_error
    assert jobs() == []


# ── A ticket by hand (KITCHEN-F23) ───────────────────────────────────────────────────────────────


def test_a_ticket_by_hand_takes_the_next_number_and_routes_its_dishes(clock, product):
    grill = make_station("Grill")
    burger = product("Burger")
    route_product(burger.id, grill)
    fired_round(product, "Soup")
    ticket = run(
        "kitchen.ticket.create",
        {
            "label": "Staff",
            "notes": "Before service",
            "items": [
                {"product": "burger", "quantity": "2", "notes": "Well done"},
                {"name": "Salad"},
            ],
        },
    )
    assert (
        ticket.number,
        ticket.order_type,
        ticket.label,
        ticket.order_id,
        ticket.round_no,
    ) == (
        "20261014-0002",
        "dine_in",
        "Staff",
        None,
        1,
    )
    assert [
        (i.name, str(i.quantity), i.notes, i.station_name) for i in ticket.items
    ] == [
        ("Burger", "2.000", "Well done", "Grill"),
        ("Salad", "1.000", "", ""),
    ]
    assert log(ticket.id) == [("created", "")]
    assert "kitchen.ticket.created" in names()
    assert len(jobs()) == 1


def test_a_ticket_by_hand_starts_with_the_settings_type():
    KitchenSettings.objects.update(default_order_type="takeaway")
    ticket = run("kitchen.ticket.create", {"items": [{"name": "Salad"}]})
    assert ticket.order_type == "takeaway"


def test_a_ticket_by_hand_with_an_unknown_product_is_refused():
    with pytest.raises(NotFound) as refused:
        run("kitchen.ticket.create", {"items": [{"product": "Unicorn steak"}]})
    assert refused.value.code == "kitchen.product_not_found"


# ── The journey of a ticket (KITCHEN-F11 to F13, F21) ───────────────────────────────────────────


def test_firing_ready_serving(clock, product):
    _, lines = fired_round(product, "Burger", "Fries")
    ref = {"ticket": "0001"}
    started = run("kitchen.ticket.start", ref)
    assert (started.status, [i.status for i in started.items]) == (
        "preparing",
        ["preparing", "preparing"],
    )
    ready = run("kitchen.ticket.ready", ref)
    assert (ready.status, [i.status for i in ready.items]) == (
        "ready",
        ["ready", "ready"],
    )
    served = run("kitchen.ticket.serve", ref)
    assert (served.status, [i.status for i in served.items]) == (
        "served",
        ["served", "served"],
    )
    assert [action for action, _ in log(lines[0].id)] == [
        "received",
        "started",
        "ready",
        "served",
    ]
    assert names() == [
        "kitchen.ticket.received",
        "kitchen.ticket.started",
        "kitchen.ticket.ready",
        "kitchen.ticket.served",
    ]


def test_ready_from_the_list_strikes_every_dish(clock, product):
    _, lines = fired_round(product, "Burger")
    run("kitchen.ticket.ready", {"ticket_id": str(lines[0].id)})
    item = TicketItem.objects.get()
    assert (item.status, item.ready_at) == ("ready", clock.now)


def test_recalling_a_ready_ticket_brings_its_dishes_back(clock, product):
    _, lines = fired_round(product, "Burger")
    run("kitchen.ticket.ready", {"ticket_id": str(lines[0].id)})
    recalled = run("kitchen.ticket.recall", {"ticket_id": str(lines[0].id)})
    assert (recalled.status, recalled.ready_at, recalled.items[0].status) == (
        "preparing",
        None,
        "preparing",
    )
    assert "kitchen.ticket.recalled" in names()


@pytest.mark.parametrize(
    ("action", "status"),
    [
        ("kitchen.ticket.start", "preparing"),
        ("kitchen.ticket.serve", "pending"),
        ("kitchen.ticket.recall", "pending"),
    ],
)
def test_a_step_off_the_path_is_refused_without_writing(clock, product, action, status):
    _, lines = fired_round(product, "Burger")
    sync()
    if status == "preparing":
        run("kitchen.ticket.start", {"ticket_id": str(lines[0].id)})
    before = names()
    with pytest.raises(Conflict) as refused:
        run(action, {"ticket_id": str(lines[0].id)})
    assert refused.value.code == "kitchen.invalid_transition"
    assert Ticket.objects.get().status == status and names() == before


def test_the_pass_prints_when_a_ticket_is_ready_if_asked(clock, product):
    KitchenSettings.objects.update(print_pass=True)
    _, lines = fired_round(product, "Burger")
    run("kitchen.ticket.ready", {"ticket_id": str(lines[0].id)})
    run("kitchen.ticket.recall", {"ticket_id": str(lines[0].id)})
    clock.advance(minutes=1)
    run("kitchen.ticket.ready", {"ticket_id": str(lines[0].id)})
    assert len(jobs()) == 2 and all(
        job.document_type == "kitchen_order" for job in jobs()
    )


def test_the_pass_prints_when_a_void_leaves_the_ticket_ready(clock, product):
    # F17 «every time a ticket turns ready»: also when the till voids the last dish still to cook.
    KitchenSettings.objects.update(print_pass=True)
    order = open_check("Table 4")
    add_line(order.id, product("Burger"))
    add_line(order.id, product("Fries"))
    ticket = run("kitchen.ticket.send", {"order_id": str(order.id)})
    burger, fries = (item.id for item in ticket.items)
    run("kitchen.item.bump", {"ticket_id": str(ticket.id), "item_ids": [str(burger)]})
    clock.advance(minutes=1)
    run("sale.order.void_line", {"order_id": str(order.id), "line_id": str(fries), "reason": "Cold"})
    sync()
    assert Ticket.objects.get().status == "ready"
    passes = [job for job in jobs() if "-pass-" in job.job_key]
    assert [[i["name"] for i in job.document["items"]] for job in passes] == [["Burger"]]


# ── The dishes (KITCHEN-F11, F12) ────────────────────────────────────────────────────────────────


def test_the_first_dish_starts_the_ticket_and_the_last_sends_it_to_the_pass(
    clock, product
):
    _, lines = fired_round(product, "Burger", "Fries")
    ref = {"ticket_id": str(lines[0].id)}
    first = run(
        "kitchen.item.bump",
        {**ref, "item_ids": [str(lines[0].id)]},
        ctx_for(actor="marta"),
    )
    assert (first.status, [i.status for i in first.items]) == (
        "preparing",
        ["ready", "pending"],
    )
    last = run("kitchen.item.bump", ref)
    assert (last.status, [i.status for i in last.items]) == (
        "ready",
        ["ready", "ready"],
    )
    assert [action for action, _ in log(lines[0].id)] == [
        "received",
        "started",
        "item_ready",
        "item_ready",
        "ready",
    ]
    assert payloads("kitchen.item.bumped")[0] == {
        "ticket_id": str(lines[0].id),
        "item_ids": [str(lines[0].id)],
    }


def test_a_station_bumps_only_its_own_dishes(clock, product):
    grill = make_station("Grill")
    burger = product("Burger")
    route_product(burger.id, grill)
    order = open_check("Table 4")
    add_line(order.id, burger)
    add_line(order.id, product("Soup"))
    lines = fire(order.id).order.lines
    ticket = run(
        "kitchen.item.bump", {"ticket_id": str(lines[0].id), "station": "grill"}
    )
    assert [i.status for i in ticket.items] == ["ready", "pending"]
    ticket = run(
        "kitchen.item.bump", {"ticket_id": str(lines[0].id), "station": "none"}
    )
    assert ticket.status == "ready"


def test_bumping_a_dish_already_ready_changes_nothing(clock, product):
    _, lines = fired_round(product, "Burger", "Fries")
    ref = {"ticket_id": str(lines[0].id), "item_ids": [str(lines[0].id)]}
    run("kitchen.item.bump", ref)
    before = (names(), LogEntry.objects.count())
    again = run("kitchen.item.bump", ref)
    assert [i.status for i in again.items] == ["ready", "pending"]
    assert (names(), LogEntry.objects.count()) == before


def test_recalling_a_dish_and_recalling_it_again(clock, product):
    _, lines = fired_round(product, "Burger")
    ref = {"ticket_id": str(lines[0].id)}
    run("kitchen.item.bump", ref)
    back = run("kitchen.item.recall", ref)
    assert (back.status, back.items[0].status, back.items[0].ready_at) == (
        "preparing",
        "preparing",
        None,
    )
    before = (names(), LogEntry.objects.count())
    assert run("kitchen.item.recall", ref).items[0].status == "preparing"
    assert (names(), LogEntry.objects.count()) == before
    assert [action for action, _ in log(lines[0].id)][-2:] == [
        "recalled",
        "item_recalled",
    ]


def test_a_dish_of_another_ticket_is_refused(clock, product):
    _, lines = fired_round(product, "Burger", label="T1")
    _, others = fired_round(product, "Soup", label="T2")
    with pytest.raises(Conflict) as refused:
        run(
            "kitchen.item.bump",
            {"ticket_id": str(lines[0].id), "item_ids": [str(others[0].id)]},
        )
    assert refused.value.code == "kitchen.item_not_in_ticket"


def test_the_dishes_of_a_served_ticket_do_not_move(clock, product):
    _, lines = fired_round(product, "Burger")
    run("kitchen.ticket.ready", {"ticket_id": str(lines[0].id)})
    run("kitchen.ticket.serve", {"ticket_id": str(lines[0].id)})
    for action in ("kitchen.item.bump", "kitchen.item.recall"):
        with pytest.raises(Conflict) as refused:
            run(action, {"ticket_id": str(lines[0].id)})
        assert refused.value.code == "kitchen.invalid_transition"


# ── Rush, reprint, cancel, delete (KITCHEN-F09, F14, F22, F24) ───────────────────────────────────


def test_rushing_prints_a_short_notice_where_dishes_are_still_to_do(clock, product):
    grill, bar = make_station("Grill"), make_station("Bar", printer_usage="bar")
    burger, beer = product("Burger"), product("Beer")
    route_product(burger.id, grill)
    route_product(beer.id, bar)
    order = open_check("Table 4")
    add_line(order.id, burger)
    add_line(order.id, beer)
    lines = fire(order.id).order.lines
    run("kitchen.item.bump", {"ticket_id": str(lines[0].id), "station": "bar"})
    rushed = run("kitchen.ticket.set_rush", {"ticket": "table 4"})
    assert (rushed.priority, rushed.rush_count) == ("rush", 1)
    [notice] = jobs()
    assert (notice.usage, notice.document["items"], notice.document["priority"]) == (
        "kitchen",
        [],
        "!! URGENT !!",
    )
    calm = run("kitchen.ticket.set_rush", {"ticket": "table 4", "rush": False})
    assert (calm.priority, len(jobs())) == ("normal", 1)
    run("kitchen.ticket.set_rush", {"ticket": "table 4"})
    assert len(jobs()) == 2
    assert [action for action, _ in log(lines[0].id) if "rush" in action] == [
        "rushed",
        "unrushed",
        "rushed",
    ]
    assert names().count("kitchen.ticket.updated") == 3


def test_a_vip_ticket_is_never_rushed_nor_made_normal(clock, product):
    _, lines = fired_round(product, "Burger")
    sync()
    Ticket.objects.filter(pk=lines[0].id).update(priority="vip")
    for rush in (True, False):
        with pytest.raises(Conflict) as refused:
            run("kitchen.ticket.set_rush", {"ticket_id": str(lines[0].id), "rush": rush})
        assert refused.value.code == "kitchen.ticket_vip"
    assert Ticket.objects.get().priority == "vip" and jobs() == []


def test_a_ticket_that_is_not_cooking_is_not_rushed(clock, product):
    _, lines = fired_round(product, "Burger")
    run("kitchen.ticket.ready", {"ticket_id": str(lines[0].id)})
    with pytest.raises(Conflict) as refused:
        run("kitchen.ticket.set_rush", {"ticket_id": str(lines[0].id)})
    assert refused.value.code == "kitchen.ticket_not_cooking"


def test_reprinting_a_ticket_that_went_to_paper_prints_a_copy_every_time(clock, product):
    order = open_check("Table 4")
    add_line(order.id, product("Burger"))
    ticket = run("kitchen.ticket.send", {"order_id": str(order.id)})
    for _ in range(2):
        run("kitchen.ticket.reprint", {"ticket_id": str(ticket.id)})
    first, *copies = jobs()
    assert first.document["duplicate"] is False
    assert len(copies) == 2 and all(job.document["duplicate"] is True for job in copies)
    assert [action for action, _ in log(ticket.id)][-2:] == ["reprinted", "reprinted"]


def test_printing_a_ticket_that_never_went_to_paper_prints_it_as_the_first_sheet(clock, product):
    # F09: a round fired by Sales alone (phase 1) never printed: «Reprint» prints it, not as a copy.
    _, lines = fired_round(product, "Burger")
    run("kitchen.ticket.reprint", {"ticket_id": str(lines[0].id)})
    run("kitchen.ticket.reprint", {"ticket_id": str(lines[0].id)})
    assert [job.document["duplicate"] for job in jobs()] == [False, True]
    assert Ticket.objects.get().printed_at == clock.now


def test_reprinting_a_ticket_with_nothing_on_paper_says_so(clock, product):
    screen = make_station("Pastry", destination="display")
    cake = product("Cake")
    route_product(cake.id, screen)
    order = open_check("Table 4")
    add_line(order.id, cake)
    lines = fire(order.id).order.lines
    with pytest.raises(Conflict) as refused:
        run("kitchen.ticket.reprint", {"ticket_id": str(lines[0].id)})
    assert refused.value.code == "kitchen.nothing_on_paper"


def test_cancelling_keeps_a_voided_dish_voided_and_prints_the_void_slip(clock, product):
    order = open_check("Table 4")
    add_line(order.id, product("Burger"))
    add_line(order.id, product("Fries"))
    ticket = run("kitchen.ticket.send", {"order_id": str(order.id)})
    burger, fries = (item.id for item in ticket.items)
    run(
        "sale.order.void_line",
        {"order_id": str(order.id), "line_id": str(fries), "reason": "Wrong"},
    )
    cancelled = run(
        "kitchen.ticket.cancel", {"ticket_id": str(ticket.id), "reason": "Guest left"}
    )
    assert (cancelled.status, [i.status for i in cancelled.items]) == (
        "cancelled",
        ["cancelled", "voided"],
    )
    assert log(ticket.id)[-1] == ("cancelled", "Guest left")
    assert payloads("kitchen.ticket.cancelled")[-1]["reason"] == "Guest left"
    # The ticket went to paper: the dish voided in the till has its own slip (F29); the cancel's slip
    # has what was left (F22).
    sheet, dish, slip = jobs()
    assert [i["name"] for i in sheet.document["items"]] == ["Burger", "Fries"]
    assert [(i["name"], i["quantity"]) for i in dish.document["items"]] == [("Fries", -1.0)]
    assert [(i["name"], i["quantity"]) for i in slip.document["items"]] == [("Burger", -1.0)]
    assert slip.document["label"] == "CANCELLED · Table 4"
    assert burger


def test_a_ticket_that_never_went_to_paper_gets_no_void_slip(clock, product):
    order, lines = fired_round(product, "Burger", "Fries")
    run(
        "sale.order.void_line",
        {"order_id": str(order.id), "line_id": str(lines[1].id), "reason": "Wrong"},
    )
    run("kitchen.ticket.cancel", {"ticket_id": str(lines[0].id)})
    assert jobs() == []


def test_an_employee_neither_cancels_nor_deletes(clock, product):
    _, lines = fired_round(product, "Burger")
    for action in ("kitchen.ticket.cancel", "kitchen.ticket.delete"):
        with pytest.raises(PermissionDenied):
            run(action, {"ticket_id": str(lines[0].id)}, ctx_for(EMPLOYEE))
    assert (
        run(
            "kitchen.item.bump", {"ticket_id": str(lines[0].id)}, ctx_for(EMPLOYEE)
        ).status
        == "ready"
    )
    assert (
        run(
            "kitchen.ticket.serve", {"ticket_id": str(lines[0].id)}, ctx_for(EMPLOYEE)
        ).status
        == "served"
    )


def test_only_a_ticket_by_hand_to_prepare_or_cancelled_is_deleted(clock, product):
    _, lines = fired_round(product, "Burger")
    with pytest.raises(Conflict) as refused:
        run("kitchen.ticket.delete", {"ticket_id": str(lines[0].id)})
    assert refused.value.code == "kitchen.ticket_not_deletable"
    by_hand = run("kitchen.ticket.create", {"items": [{"name": "Salad"}]})
    assert run("kitchen.ticket.delete", {"ticket_id": str(by_hand.id)}).id == by_hand.id
    assert Ticket.objects.get(pk=by_hand.id).is_deleted
    assert log(by_hand.id)[-1][0] == "deleted"
    with pytest.raises(NotFound):
        run("kitchen.ticket.get", {"ticket_id": str(by_hand.id)})


def test_deleting_twice_deletes_once(clock):
    by_hand = run("kitchen.ticket.create", {"items": [{"name": "Salad"}]})
    run("kitchen.ticket.delete", {"ticket_id": str(by_hand.id)})
    before = (names(), LogEntry.objects.count())
    assert run("kitchen.ticket.delete", {"ticket_id": str(by_hand.id)}).id == by_hand.id
    assert (names(), LogEntry.objects.count()) == before


# ── What Sales did, saved (KITCHEN-F27 to F29) ───────────────────────────────────────────────────


def test_saving_a_voided_line_writes_its_history_at_the_moment_it_happened(
    clock, product
):
    order, lines = fired_round(product, "Burger", "Fries")
    sync()
    clock.advance(minutes=2)
    run(
        "sale.order.void_line",
        {
            "order_id": str(order.id),
            "line_id": str(lines[1].id),
            "reason": "Out of stock",
        },
    )
    voided_at = clock.now
    clock.advance(minutes=5)
    assert sync().changed == 1
    item = TicketItem.objects.get(pk=lines[1].id)
    assert (item.status, item.void_reason) == ("voided", "Out of stock")
    entry = LogEntry.objects.get(action="item_voided")
    assert (entry.notes, entry.created_at, entry.item_id) == (
        "Out of stock",
        voided_at,
        item.id,
    )
    assert payloads("kitchen.item.voided") == [
        {
            "ticket_id": str(lines[0].id),
            "item_ids": [str(item.id)],
            "reason": "Out of stock",
        }
    ]
    assert sync().changed == 0


def test_saving_a_charge_serves_the_ready_round(clock, product):
    order, lines = fired_round(product, "Burger")
    run("kitchen.ticket.ready", {"ticket_id": str(lines[0].id)})
    clock.advance(minutes=1)
    charge(order.id, key="serve-on-charge")
    sync()
    ticket = Ticket.objects.get()
    assert (ticket.status, ticket.served_at) == ("served", clock.now)
    assert log(ticket.id)[-1][0] == "served"


def test_saving_a_voided_check_cancels_its_rounds(clock, product):
    order, lines = fired_round(product, "Burger")
    run("sale.order.void", {"order_id": str(order.id)})
    sync()
    assert Ticket.objects.get().status == "cancelled"
    assert [action for action, _ in log(lines[0].id)] == ["received", "cancelled"]


def test_every_write_saves_first(clock, product):
    _, lines = fired_round(product, "Burger")
    make = run("kitchen.station.create", {"name": "Grill"})
    assert make.name == "Grill" and not Ticket.objects.exists()
    run("kitchen.item.bump", {"ticket_id": str(lines[0].id)})
    assert Ticket.objects.get().status == "ready"


# ── Stations and routing (KITCHEN-F01 to F04) ────────────────────────────────────────────────────


def test_creating_editing_and_deleting_a_station():
    station = run(
        "kitchen.station.create",
        {
            "name": "Bar",
            "color": "#228BE6",
            "destination": "printer",
            "printer_usage": "bar",
            "printer_name": "Bar",
        },
    )
    assert (station.name, station.destination, station.in_progress, station.routes) == (
        "Bar",
        "printer",
        0,
        0,
    )
    edited = run(
        "kitchen.station.update",
        {"station": "bar", "name": "Cocktails", "is_active": False},
    )
    assert (edited.name, edited.is_active, edited.color) == (
        "Cocktails",
        False,
        "#228BE6",
    )
    assert (
        run("kitchen.station.delete", {"station_id": str(station.id)}).id == station.id
    )
    assert Station.objects.get().is_deleted
    assert names() == [
        "kitchen.station.created",
        "kitchen.station.updated",
        "kitchen.station.deleted",
    ]
    with pytest.raises(NotFound):
        run("kitchen.station.delete", {"station_id": str(station.id)})


def test_a_station_name_is_unique_among_the_live_ones():
    run("kitchen.station.create", {"name": "Grill"})
    with pytest.raises(Conflict) as refused:
        run("kitchen.station.create", {"name": "grill"})
    assert refused.value.code == "kitchen.station_name_taken"
    other = run("kitchen.station.create", {"name": "Bar"})
    with pytest.raises(Conflict):
        run("kitchen.station.update", {"station_id": str(other.id), "name": "GRILL"})


def test_a_station_with_routes_or_dishes_to_do_is_not_deleted(clock, product):
    grill = make_station("Grill")
    burger = product("Burger")
    route_product(burger.id, grill)
    with pytest.raises(Conflict) as refused:
        run("kitchen.station.delete", {"station": "Grill"})
    assert refused.value.code == "kitchen.station_in_use"
    order = open_check("Table 4")
    add_line(order.id, burger)
    fire(order.id)
    run("kitchen.routing.clear", {"product_id": str(burger.id)})
    with pytest.raises(Conflict):
        run("kitchen.station.delete", {"station": "Grill"})


def test_an_employee_does_not_run_the_stations():
    with pytest.raises(PermissionDenied):
        run("kitchen.station.create", {"name": "Grill"}, ctx_for(EMPLOYEE))
    assert (
        run("kitchen.station.create", {"name": "Grill"}, ctx_for("hub_manager")).name
        == "Grill"
    )


def test_routing_a_product_or_a_category_by_name_and_taking_it_away(product, category):
    grill, bar = make_station("Grill"), make_station("Bar")
    burger = product("Burger")
    category("Drinks")
    run("kitchen.routing.set", {"station": "grill", "product": "burger"})
    run(
        "kitchen.routing.set", {"station_id": str(bar.id), "product_id": str(burger.id)}
    )
    run("kitchen.routing.set", {"station": "bar", "category": "drinks"})
    rows = run("kitchen.routing.list", {}).rows
    assert [(r.kind, r.target_name, r.station_name) for r in rows] == [
        ("category", "Drinks", "Bar"),
        ("product", "Burger", "Bar"),
    ]
    run("kitchen.routing.clear", {"category": "Drinks"})
    assert [r.kind for r in run("kitchen.routing.list", {}).rows] == ["product"]
    assert payloads("kitchen.routing.changed")[0] == {
        "station_id": str(grill.id),
        "product_id": str(burger.id),
        "category_id": None,
    }


def test_routing_to_an_inactive_station_or_to_nothing_known_is_refused(product):
    make_station("Grill", is_active=False)
    product("Burger")
    with pytest.raises(Conflict) as refused:
        run("kitchen.routing.set", {"station": "grill", "product": "burger"})
    assert refused.value.code == "kitchen.station_inactive"
    make_station("Bar")
    with pytest.raises(NotFound) as unknown:
        run("kitchen.routing.set", {"station": "bar", "product": "unicorn"})
    assert unknown.value.code == "kitchen.product_not_found"
    with pytest.raises(NotFound) as gone:
        run("kitchen.routing.clear", {"product": "burger"})
    assert gone.value.code == "kitchen.route_not_found"


# ── Settings (KITCHEN-F26) ───────────────────────────────────────────────────────────────────────


def test_saving_the_settings_changes_only_what_is_sent(clock):
    saved = run(
        "kitchen.settings.update",
        {"warning_minutes": 10, "sound_tone": "buzzer"},
        ctx_for(actor="eva"),
    )
    assert (saved.warning_minutes, saved.critical_minutes, saved.sound_tone) == (
        10,
        30,
        "buzzer",
    )
    row = KitchenSettings.objects.get()
    assert (row.updated_by, row.screen_changed_at) == ("eva", None)
    assert payloads("kitchen.settings.updated") == [
        {"fields": ["sound_tone", "warning_minutes"]}
    ]
    run("kitchen.settings.update", {"works_from_screen": False})
    assert KitchenSettings.objects.get().screen_changed_at == clock.now


def test_the_amber_comes_before_the_red():
    with pytest.raises(InvalidPayload) as refused:
        run("kitchen.settings.update", {"warning_minutes": 40})
    assert set(refused.value.fields) == {"warning_minutes"}


def test_an_employee_does_not_save_the_settings():
    with pytest.raises(PermissionDenied):
        run("kitchen.settings.update", {"print_pass": True}, ctx_for(EMPLOYEE))


def test_the_settings_row_is_made_again_if_it_was_lost():
    KitchenSettings.objects.all().delete()
    assert run("kitchen.settings.update", {"print_pass": True}).print_pass is True
    assert KitchenSettings.objects.count() == 1


def test_the_reaction_is_the_systems_own():
    with pytest.raises(PermissionDenied):
        run("kitchen.ticket.sync", {"order_id": str(uuid.uuid7())}, ctx_for())


# ── Notifications: after the COMMIT, on the channel of the command's scope only ──────────────────


@pytest.fixture
def listen(db_dsn):
    import psycopg

    sessions = []

    def open_session(scope):
        from live.outbox import channel_for

        session = psycopg.connect(db_dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def received(session, timeout=1.0, stop_after=None):
    import json

    return [
        (note.channel, json.loads(note.payload))
        for note in session.notifies(timeout=timeout, stop_after=stop_after)
    ]


@pytest.mark.django_db(transaction=True)
def test_a_ticket_made_in_b_wakes_b_only(listen):
    from live.outbox import channel_for

    from .conftest import B

    on_a, on_b = listen(A), listen(B)
    run("kitchen.ticket.create", {"items": [{"name": "Staff meal"}]}, ctx_for(scope=B))
    # The ticket and its sheet (Printing's own operation, nested) wake B, each after the COMMIT.
    on_b_events = received(on_b, stop_after=2)
    assert {channel for channel, _ in on_b_events} == {channel_for(B)}
    assert sorted(name for _, note in on_b_events for name in note["events"]) == [
        "kitchen.ticket.created",
        "printing.job.queued",
    ]
    assert received(on_a, timeout=0.3) == []
