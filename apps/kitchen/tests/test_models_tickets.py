"""The kitchen tickets and their dishes, and the rules the database itself keeps for them (the last net under
a race)."""

import uuid
from decimal import Decimal

from .conftest import HUB_DB, make_station, make_ticket, refused

pytestmark = HUB_DB


def test_every_key_is_a_uuid7():
    from apps.kitchen.models.history import LogEntry
    from apps.kitchen.models.tickets import TicketItem

    station = make_station()
    ticket = make_ticket()
    item = TicketItem.objects.create(
        ticket=ticket, position=1, name="Burger", quantity=Decimal("1")
    )
    log = LogEntry.objects.create(ticket=ticket, action="received")
    for row in (station, ticket, item, log):
        assert isinstance(row.pk, uuid.UUID) and row.pk.version == 7


def test_a_ticket_number_is_unique_and_reads_short():
    ticket = make_ticket("20261014-0012")
    assert ticket.short_number == "0012"
    # It has not gone to paper until its sheet is queued (KITCHEN-F08): no void slip, no copy before.
    assert ticket.printed_at is None
    assert (
        ticket.status,
        ticket.priority,
        ticket.order_type,
        ticket.round_no,
        ticket.rush_count,
    ) == (
        "pending",
        "normal",
        "dine_in",
        1,
        0,
    )
    assert refused(lambda: make_ticket("20261014-0012"))


def test_a_ticket_status_priority_and_type_are_closed_lists():
    assert refused(lambda: make_ticket("20261014-0002", status="lost"))
    assert refused(lambda: make_ticket("20261014-0003", priority="urgent"))
    assert refused(lambda: make_ticket("20261014-0004", order_type="drive_in"))


def test_a_line_of_sales_is_one_dish_at_most():
    from apps.kitchen.models.tickets import TicketItem

    ticket = make_ticket()
    line = uuid.uuid7()
    TicketItem.objects.create(
        ticket=ticket, sale_line_id=line, position=1, name="Burger", quantity=1
    )
    assert refused(
        lambda: TicketItem.objects.create(
            ticket=ticket, sale_line_id=line, position=2, name="Burger", quantity=1
        )
    )


def test_a_menu_line_of_sales_is_one_dish_per_dish_of_the_menu_at_most():
    """KITCHEN-F06: a menu is one line of Sales and one dish per dish chosen (``menu_dish`` 1, 2…); saving
    the same round twice is still refused."""
    from apps.kitchen.models.tickets import TicketItem

    ticket = make_ticket()
    line = uuid.uuid7()
    for dish, name in enumerate(("Lentils", "Steak"), start=1):
        TicketItem.objects.create(
            ticket=ticket,
            sale_line_id=line,
            menu_dish=dish,
            menu_name="MENU",
            position=dish,
            name=name,
            quantity=1,
        )
    assert refused(
        lambda: TicketItem.objects.create(
            ticket=ticket, sale_line_id=line, menu_dish=2, position=3, name="Steak", quantity=1
        )
    )


def test_a_dish_status_is_a_closed_list_and_its_quantity_positive():
    from apps.kitchen.models.tickets import TicketItem

    ticket = make_ticket()
    assert refused(
        lambda: TicketItem.objects.create(
            ticket=ticket, position=1, name="X", quantity=1, status="lost"
        )
    )
    assert refused(
        lambda: TicketItem.objects.create(
            ticket=ticket, position=1, name="X", quantity=0
        )
    )


def test_a_dish_keeps_its_station_name_when_the_station_goes():
    from apps.kitchen.models.tickets import TicketItem

    station = make_station("Grill")
    item = TicketItem.objects.create(
        ticket=make_ticket(),
        position=1,
        name="Burger",
        quantity=1,
        station=station,
        station_name="Grill",
    )
    station.delete()
    item.refresh_from_db()
    assert item.station_id is None and item.station_name == "Grill"


def test_a_ticket_keeps_no_customer_so_merging_two_customers_has_nothing_to_move():
    """The till sends a label, never a customer: no ticket nor dish keeps one, and the kitchen hears nothing of
    Customers (``customer.merged`` has no reaction here)."""
    from apps.kitchen import events
    from apps.kitchen.models.tickets import Ticket, TicketItem

    for model in (Ticket, TicketItem):
        assert not [field.name for field in model._meta.get_fields() if "customer" in field.name]
    assert not [name for name in events.REACTIONS if name.startswith("customer.")]
