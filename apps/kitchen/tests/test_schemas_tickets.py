"""The input schemas of the tickets: one made by hand and what a person does with the dishes of one."""

from decimal import Decimal

from apps.kitchen.schemas.tickets import ItemBumpIn, TicketCreateIn

from .test_schemas_fields import refuses


def test_a_hand_made_ticket_has_one_dish_at_least_each_named():
    item = {"name": "Staff meal", "quantity": "2"}
    data = TicketCreateIn.model_validate({"items": [item]})
    assert data.order_type is None and data.items[0].quantity == Decimal("2")
    assert refuses(TicketCreateIn, items=[])
    assert refuses(TicketCreateIn, items=[{"quantity": "1"}])
    assert refuses(TicketCreateIn, items=[{"name": "Soup", "quantity": "0"}])


def test_bumping_names_its_ticket_and_maybe_its_dishes_and_station():
    data = ItemBumpIn.model_validate({"ticket": "12", "station": "grill"})
    assert (data.item_ids, data.station) == ([], "grill")
