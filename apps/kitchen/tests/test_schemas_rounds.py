"""The input schemas of the rounds of a check of Sales: the one the till sends and the reactions to Sales' events,
which read only what they need and never drop a round."""

import uuid

import pytest

from apps.kitchen.schemas.rounds import TicketReceiveIn, TicketSendIn, TicketSyncIn

from .test_schemas_fields import refuses


def test_the_kitchen_sends_normal_or_rush():
    data = TicketSendIn.model_validate({"order_id": str(uuid.uuid7())})
    assert (data.label, data.channel, data.priority) == ("", "dine_in", "normal")
    assert refuses(TicketSendIn, order_id=str(uuid.uuid7()), priority="urgent")
    assert refuses(TicketSendIn, order_id=str(uuid.uuid7()), channel="drive_in")


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
    data = TicketReceiveIn.model_validate(
        {
            "order_id": str(uuid.uuid7()),
            "round_no": 2,
            "priority": said,
            "channel": "on the moon",
            "anything": 1,
        }
    )
    assert (data.priority, data.channel, data.round_no) == (priority, "dine_in", 2)


def test_a_received_round_that_says_no_priority_nor_channel_is_normal_and_dine_in():
    """The assistant may ask for a round by its check alone (hub#671): what it does not say is the default the ticket
    knows, never an empty priority the reading before would have made «normal»."""
    data = TicketReceiveIn.model_validate({"order_id": str(uuid.uuid7()), "round_no": 1})
    assert (data.priority, data.channel) == ("normal", "dine_in")


def test_the_reaction_to_sales_reads_the_check_and_ignores_the_rest():
    order = str(uuid.uuid7())
    assert TicketSyncIn.model_validate(
        {"order_id": order, "line_id": "x"}
    ).order_id == uuid.UUID(order)
    merged = TicketSyncIn.model_validate(
        {"from_order_id": order, "to_order_id": order}
    )
    assert merged.order_id is None and merged.to_order_id == uuid.UUID(order)
