"""The models of the kitchen app and the rules the database itself keeps (the last net under a race)."""

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from .conftest import make_station

pytestmark = pytest.mark.django_db


def refused(build) -> bool:
    try:
        with transaction.atomic():
            build()
    except IntegrityError:
        return True
    return False


def make_ticket(number: str = "20261014-0001", **fields):
    from apps.kitchen.models import Ticket

    fields.setdefault("day", dt.date(2026, 10, 14))
    fields.setdefault("sequence", int(number[-4:]))
    fields.setdefault("received_at", timezone.now())
    return Ticket.objects.create(number=number, **fields)


def test_every_key_is_a_uuid7():
    from apps.kitchen.models import LogEntry, TicketItem

    station = make_station()
    ticket = make_ticket()
    item = TicketItem.objects.create(
        ticket=ticket, position=1, name="Burger", quantity=Decimal("1")
    )
    log = LogEntry.objects.create(ticket=ticket, action="received")
    for row in (station, ticket, item, log):
        assert isinstance(row.pk, uuid.UUID) and row.pk.version == 7


def test_a_new_station_goes_to_screen_and_paper_by_the_kitchen_printer():
    station = make_station("Grill")
    assert (
        station.color,
        station.destination,
        station.printer_usage,
        station.printer_name,
        station.is_active,
        station.is_deleted,
        station.sort_order,
    ) == ("#F97316", "both", "kitchen", "", True, False, 0)
    assert str(station) == "Grill"


def test_two_live_stations_never_share_a_name_whatever_the_case():
    make_station("Grill")
    assert refused(lambda: make_station("grill"))


def test_a_deleted_station_frees_its_name():
    old = make_station("Grill")
    old.is_deleted = True
    old.save()
    assert not refused(lambda: make_station("Grill"))


def test_a_station_destination_and_printer_usage_are_closed_lists():
    assert refused(lambda: make_station("A", destination="fax"))
    assert refused(lambda: make_station("B", printer_usage="receipt"))
    assert refused(lambda: make_station("C", color="orange"))


def test_a_product_and_a_category_go_to_one_station_at_most(product, category):
    from apps.kitchen.models import CategoryRoute, ProductRoute

    grill, bar = make_station("Grill"), make_station("Bar")
    burger, mains = product("Burger"), category("Mains")
    ProductRoute.objects.create(product_id=burger.id, station=grill)
    CategoryRoute.objects.create(category_id=mains.id, station=grill)
    assert refused(
        lambda: ProductRoute.objects.create(product_id=burger.id, station=bar)
    )
    assert refused(
        lambda: CategoryRoute.objects.create(category_id=mains.id, station=bar)
    )


def test_the_settings_are_one_row_with_the_factory_values():
    from apps.kitchen.models import KitchenSettings

    settings = KitchenSettings.objects.get()
    assert (
        settings.show_timer,
        settings.warning_minutes,
        settings.critical_minutes,
        settings.color_coding,
        settings.sound_enabled,
        settings.sound_volume,
        settings.sound_tone,
        settings.print_pass,
        settings.works_from_screen,
        settings.default_order_type,
    ) == (True, 15, 30, True, True, 70, "chime", False, True, "dine_in")
    assert refused(lambda: KitchenSettings.objects.create())


def test_the_settings_keep_their_ranges():
    from apps.kitchen.models import KitchenSettings

    def save(**fields):
        def build():
            KitchenSettings.objects.update(**fields)

        return build

    assert refused(save(warning_minutes=0))
    assert refused(save(critical_minutes=121))
    assert refused(save(warning_minutes=30, critical_minutes=30))
    assert refused(save(sound_volume=101))
    assert refused(save(sound_tone="siren"))
    assert refused(save(default_order_type="drive_in"))


def test_one_counter_a_day():
    from apps.kitchen.models import DayCounter

    DayCounter.objects.create(day=dt.date(2026, 10, 14), last_number=3)
    assert refused(lambda: DayCounter.objects.create(day=dt.date(2026, 10, 14)))


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
    from apps.kitchen.models import TicketItem

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
    from apps.kitchen.models import TicketItem

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
    from apps.kitchen.models import TicketItem

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
    from apps.kitchen.models import TicketItem

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


def test_a_log_entry_belongs_to_its_ticket():
    from apps.kitchen.models import LogEntry

    ticket = make_ticket()
    entry = LogEntry.objects.create(
        ticket=ticket, action="received", actor="ana", notes=""
    )
    assert entry.created_at is not None and str(entry) == "received 20261014-0001"
    assert refused(lambda: LogEntry.objects.create(ticket=ticket, action="sang"))


def test_a_ticket_keeps_no_customer_so_merging_two_customers_has_nothing_to_move():
    """KITCHEN-F30 (descartado): the till sends a label, never a customer; no ticket nor dish keeps one, and the
    kitchen hears nothing of Customers (``customer.merged`` has no reaction here)."""
    from apps.kitchen import events
    from apps.kitchen.models import Ticket, TicketItem

    for model in (Ticket, TicketItem):
        assert not [field.name for field in model._meta.get_fields() if "customer" in field.name]
    assert not [name for name in events.REACTIONS if name.startswith("customer.")]
