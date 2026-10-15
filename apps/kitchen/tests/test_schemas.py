"""The input schemas of the kitchen app: what they accept, what they refuse (422 per field) and how a
person names a record (assistant, voice)."""

import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from apps.kitchen import schemas


def refuses(schema, **data) -> bool:
    try:
        schema.model_validate(data)
    except ValidationError:
        return True
    return False


def test_every_input_refuses_a_field_it_does_not_declare():
    assert refuses(schemas.TicketListIn, colour="red")
    assert refuses(schemas.StationIn, name="Grill", fire=True)


def test_a_page_is_one_to_a_hundred_rows():
    assert schemas.TicketListIn.model_validate({}).limit == 50
    assert refuses(schemas.TicketListIn, limit=101)
    assert refuses(schemas.TicketListIn, limit=0)
    assert refuses(schemas.LogListIn, offset=-1)


def test_a_ticket_is_named_by_its_id_or_as_a_person_says_it():
    by_id = schemas.TicketRefIn.model_validate({"ticket_id": str(uuid.uuid7())})
    said = schemas.TicketRefIn.model_validate({"ticket": "  Table 4 "})
    assert by_id.ticket_id and said.ticket == "Table 4"
    assert refuses(schemas.TicketRefIn)


def test_the_kitchen_sends_normal_or_rush():
    data = schemas.TicketSendIn.model_validate({"order_id": str(uuid.uuid7())})
    assert (data.label, data.channel, data.priority) == ("", "dine_in", "normal")
    assert refuses(schemas.TicketSendIn, order_id=str(uuid.uuid7()), priority="urgent")
    assert refuses(schemas.TicketSendIn, order_id=str(uuid.uuid7()), channel="drive_in")


@pytest.mark.parametrize(
    ("said", "priority"),
    [
        ("urgent", "rush"),
        ("URGENT", "rush"),
        ("rush", "rush"),
        ("vip", "vip"),
        ("", "normal"),
        ("whenever", "normal"),
    ],
)
def test_a_received_round_never_drops_a_word_it_does_not_know(said, priority):
    # «Una prioridad o un canal desconocidos caen a normal y a En sala: nunca se pierde una ronda.»
    data = schemas.TicketReceiveIn.model_validate(
        {
            "order_id": str(uuid.uuid7()),
            "round_no": 2,
            "priority": said,
            "channel": "on the moon",
            "anything": 1,
        }
    )
    assert (data.priority, data.channel, data.round_no) == (priority, "dine_in", 2)


def test_a_hand_made_ticket_has_one_dish_at_least_each_named():
    item = {"name": "Staff meal", "quantity": "2"}
    data = schemas.TicketCreateIn.model_validate({"items": [item]})
    assert data.order_type is None and data.items[0].quantity == Decimal("2")
    assert refuses(schemas.TicketCreateIn, items=[])
    assert refuses(schemas.TicketCreateIn, items=[{"quantity": "1"}])
    assert refuses(schemas.TicketCreateIn, items=[{"name": "Soup", "quantity": "0"}])


def test_bumping_names_its_ticket_and_maybe_its_dishes_and_station():
    data = schemas.ItemBumpIn.model_validate({"ticket": "12", "station": "grill"})
    assert (data.item_ids, data.station) == ([], "grill")


def test_a_station_has_a_name_a_hex_colour_and_closed_lists():
    data = schemas.StationIn.model_validate({"name": " Grill "})
    assert (
        data.name,
        data.color,
        data.destination,
        data.printer_usage,
        data.is_active,
    ) == (
        "Grill",
        "#F97316",
        "both",
        "kitchen",
        True,
    )
    assert refuses(schemas.StationIn, name="")
    assert refuses(schemas.StationIn, name="Bar", color="orange")
    assert refuses(schemas.StationIn, name="Bar", destination="fax")
    assert refuses(schemas.StationPatchIn, station="Bar", printer_usage="receipt")


def test_a_route_goes_to_one_station_from_one_product_or_one_category():
    product = str(uuid.uuid7())
    data = schemas.RoutingSetIn.model_validate(
        {"station": "Grill", "product_id": product}
    )
    assert data.product_id and data.category_id is None
    assert refuses(schemas.RoutingSetIn, station="Grill")
    assert refuses(
        schemas.RoutingSetIn, station="Grill", product_id=product, category="Mains"
    )
    assert refuses(schemas.RoutingSetIn, product_id=product)
    assert refuses(schemas.RoutingClearIn)


def test_the_settings_keep_their_ranges_and_lists():
    data = schemas.SettingsPatchIn.model_validate({"warning_minutes": 10})
    assert data.model_dump(exclude_unset=True) == {"warning_minutes": 10}
    assert refuses(schemas.SettingsPatchIn, warning_minutes=0)
    assert refuses(schemas.SettingsPatchIn, critical_minutes=121)
    assert refuses(schemas.SettingsPatchIn, sound_volume=101)
    assert refuses(schemas.SettingsPatchIn, sound_tone="siren")
    assert refuses(schemas.SettingsPatchIn, default_order_type="drive_in")


def test_the_reaction_to_sales_reads_the_check_and_ignores_the_rest():
    order = str(uuid.uuid7())
    assert schemas.TicketSyncIn.model_validate(
        {"order_id": order, "line_id": "x"}
    ).order_id == uuid.UUID(order)
    merged = schemas.TicketSyncIn.model_validate(
        {"from_order_id": order, "to_order_id": order}
    )
    assert merged.order_id is None and merged.to_order_id == uuid.UUID(order)
