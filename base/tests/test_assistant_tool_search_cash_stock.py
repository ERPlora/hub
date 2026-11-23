"""Phrases about the till, the stock and the devices that the assistant once left without the tool they asked for.

Each one reaches its tool now: either among the twenty tools a turn offers for the phrase's own words, or once the model
searches the person's whole catalogue for the task (``base.assistant.find_tools``) and the next step offers what it
found.
"""

import pytest
from live import assistant as shared

from base.tenancy.tests.business import HUB_DB, in_business_a
from base.tests.assistant_context import owner_of_a
from base.tests.test_assistant_tool_search import names, turn, user
from base.tests.test_assistant_tool_search import (
    test_the_tool_a_phrase_left_out_is_offered_once_the_model_searches_for_it as offered_once_searched,
)

__all__ = ["in_business_a"]

pytestmark = HUB_DB  # the catalogue is of the apps on in the business (base.activation)

MOVEMENT = "cash_register.movement.add"
RECEIVE = "inventory.stock.receive"
DEVICE = "printing.device.register"

#: The tools a phrase's own words already bring into the twenty a turn offers.
OFFERED = [
    pytest.param("es", "retira 50 € de la caja para el banco", (MOVEMENT,), id="live-128-es"),
    pytest.param(
        "es", "saca 2 € de la caja para el pan y saca 2 copias del tique", (MOVEMENT, "sale.sale.print"), id="live-131"
    ),
    pytest.param(
        "es",
        "registra que el pago del pedido de QA-WEB-1 falló porque el banco lo rechazó",
        ("cart_checkout.order.fail",),
        id="live-120-failed-payment",
    ),
    pytest.param(
        "es",
        "registra que Luis no se presentó a su reserva",
        ("online_booking.booking.no_show", "reservation.reservation.no_show"),
        id="live-120-no-show",
    ),
    pytest.param(
        "es", "apunta que han llegado los de la reserva de Luis", ("reservation.reservation.seat",), id="live-120-seat"
    ),
]

#: What a phrase's own words leave out, and the task the model searches for then, in English and in Spanish.
CASH_IN = ("record a cash movement", "apuntar un movimiento de caja")
GOODS_IN = ("receive goods", "recibir mercancía")
NEW_DEVICE = ("register a device", "registrar un dispositivo")
OPEN_THE_TILL = ("open the cash register", "abrir la caja")
SEARCHED = [
    pytest.param("en", "open the register on this tablet", OPEN_THE_TILL, "cash_register.session.open", id="live-129-open"),
    pytest.param("en", "log two entries of 20 € in the shift", CASH_IN, MOVEMENT, id="live-170"),
    pytest.param("en", "rename it then register this device as Bar 2", NEW_DEVICE, DEVICE, id="live-127-then"),
    pytest.param(
        "es",
        "apunta que han llegado dos más a la mesa 7",
        ("change the guests of a table", "cambiar los comensales de una mesa"),
        "table.session.set_guests",
        id="live-120-guests",
    ),
    pytest.param(
        "es",
        "apunta que han llegado Pedro y Ana",
        ("clock in an employee", "fichar la entrada de un empleado"),
        "attendance.record.clock_in",
        id="live-120-clock-in",
    ),
    pytest.param(
        "es",
        "apunta que han llegado las dos clientas de la cita de las 10",
        ("start an appointment", "registrar la llegada a una cita"),
        "appointment.appointment.start",
        id="live-120-appointment",
    ),
    pytest.param("es", "pon una entrada de 50 € de cambio", CASH_IN, MOVEMENT, id="live-162"),
    pytest.param("en", "record that 100 € came in during the shift", CASH_IN, MOVEMENT, id="live-135"),
    pytest.param(
        "en",
        "withdraw 50 € from the register for the bank",
        ("take money out of the cash register", "sacar dinero de la caja"),
        MOVEMENT,
        id="live-128-en",
    ),
    pytest.param(
        "en",
        "put 20 € in the register from this tablet",
        ("put money in the cash register", "meter dinero en la caja"),
        MOVEMENT,
        id="live-129-put",
    ),
    pytest.param(
        "en",
        "how much is in the register on this tablet?",
        ("see how much money is in the cash register", "ver cuánto dinero hay en la caja"),
        "cash_register.session.current",
        id="live-129-current",
    ),
    pytest.param("es", "apunta que entran 50 € de género del proveedor", GOODS_IN, RECEIVE, id="live-137"),
    pytest.param("es", "apunta que ha entrado una caja de leche", GOODS_IN, RECEIVE, id="live-132"),
    pytest.param("en", "I want to register this tablet as Bar", NEW_DEVICE, DEVICE, id="live-125"),
    pytest.param("es", "registra este móvil como Móvil de Ana", NEW_DEVICE, DEVICE, id="live-126"),
    pytest.param("en", "rename it and also register this device as Bar 2", NEW_DEVICE, DEVICE, id="live-127-also"),
]


@pytest.mark.parametrize(("language", "said", "expected"), OFFERED)
def test_the_phrase_alone_offers_the_tool_it_asks_for(make_user, language, said, expected):
    offered = names(turn(owner_of_a(make_user, language), user(said))["tools"])
    for name in expected:
        assert shared.tool_name(name) in offered, name


@pytest.mark.parametrize(("language", "said", "tasks", "expected"), SEARCHED)
def test_the_tool_the_phrase_leaves_out_is_offered_once_the_model_searches_for_the_task(
    make_user, language, said, tasks, expected
):
    offered_once_searched(make_user, language, said, tasks, expected)  # the same check as the search's own cases
