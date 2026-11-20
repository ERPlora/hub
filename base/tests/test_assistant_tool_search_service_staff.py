"""Phrases about the till, the kitchen, the reservations, the clock-ins, the services and the customer cards that the
assistant once left without the tool they asked for, or offered it far down.

Each one reaches its tool now: either among the forty tools a turn offers for the phrase's own words, or once the model
searches the person's whole catalogue for the task (``base.assistant.find_tools``) and the next step offers what it
found.
"""

import pytest
from live import assistant as shared

from base.tenancy.tests.business import HUB_DB, in_business_a
from base.tests.assistant_context import offered, owner_of_a
from base.tests.test_assistant_tool_search import (
    test_the_tool_a_phrase_left_out_is_offered_once_the_model_searches_for_it as offered_once_searched,
)
from base.tests.test_assistant_tool_search import user

__all__ = ["in_business_a"]

pytestmark = HUB_DB  # the catalogue is of the apps on in the business (base.activation)

CLOSE = "cash_register.session.close"
OPEN = "cash_register.session.open"
CUSTOMER = "customer.customer.update"
RESERVE = "reservation.reservation.create"
SEND = "kitchen.ticket.send"
CLOCK_IN = "attendance.record.clock_in"
CLOCK_OUT = "attendance.record.clock_out"
UNASSIGN = "service.assignment.remove"

#: The tools a phrase's own words already bring into the forty a turn offers.
OFFERED = [
    pytest.param("es", "no me deja cerrar la caja sin contar, ni abrirla puedo", (OPEN, CLOSE), id="live-108-open"),
    pytest.param("es", "intento cerrar la caja sin contar, ni abrirla puedo", (OPEN,), id="live-108-trying"),
    pytest.param(
        "es",
        "la impresora imprime sin logo ni cambiar el formato me deja",
        ("printing.settings.update",),
        id="live-108-printer",
    ),
    pytest.param("es", "la app se abre sin datos ni cerrar la sesión me deja", (CLOSE,), id="live-108-app"),
    pytest.param("es", "cierra la caja sin dar de baja a Ana", (CLOSE,), id="live-111"),
    pytest.param("es", "anota su correo nuevo en la ficha de Marta", (CUSTOMER,), id="live-112"),
    pytest.param("es", "anota en la ficha de Marta su correo nuevo", (CUSTOMER,), id="live-112-card-first"),
    pytest.param("es", "apunta una mesa para 4 a las 21 en el libro de reservas", (RESERVE,), id="live-113"),
    pytest.param("es", "apunta en el libro de reservas una mesa para 4 a las 21", (RESERVE,), id="live-113-book-first"),
    pytest.param("es", "mete un ticket para la mesa 3 en la cocina", (SEND,), id="live-114"),
    pytest.param("es", "mete en la cocina un ticket para la mesa 3", (SEND,), id="live-114-kitchen-first"),
    pytest.param("es", "apunta que Ana y Luis han fichado a las 9", (CLOCK_IN,), id="live-134"),
    pytest.param("es", "apunta que han fichado tarde Ana y Luis", (CLOCK_IN,), id="live-134-late"),
    pytest.param("es", "anota que han fichado la salida Ana y Luis a las 17", (CLOCK_OUT,), id="live-134-out"),
    pytest.param("es", "ficha a Ana y Luis, han entrado a las 9", (CLOCK_IN,), id="live-134-clock-them-in"),
]

#: What a phrase's own words leave out, and the task the model searches for then, in English and in Spanish.
CLOSE_THE_TILL = ("close the cash register", "cerrar la caja")
CLOCK_SOMEONE_IN = ("clock in an employee", "fichar la entrada de un empleado")
TAKE_OFF_A_SERVICE = ("remove a professional from a service", "quitar a una profesional de un servicio")
SEARCHED = [
    pytest.param(
        "es",
        "la caja muestra un descuadre sin cobrar ninguna mesa, ni cerrarla me deja",
        CLOSE_THE_TILL,
        CLOSE,
        id="live-108",
    ),
    pytest.param(
        "es", "tengo mesas sin cobrar ni cerrar la caja cuando toca puedo", CLOSE_THE_TILL, CLOSE, id="live-109"
    ),
    pytest.param(
        "es", "tengo mesas sin cobrar ni cerrar la caja si quiero puedo", CLOSE_THE_TILL, CLOSE, id="live-109-if"
    ),
    pytest.param("es", "apunta que fichan tarde Ana y Luis", CLOCK_SOMEONE_IN, CLOCK_IN, id="live-134-present"),
    pytest.param("es", "Marta ya no hace depilaciones, quítasela", TAKE_OFF_A_SERVICE, UNASSIGN, id="live-160"),
    pytest.param("es", "quita a Marta de las depilaciones", TAKE_OFF_A_SERVICE, UNASSIGN, id="live-160-from"),
]


@pytest.mark.parametrize(("language", "said", "expected"), OFFERED)
def test_the_phrase_alone_offers_the_tool_it_asks_for(make_user, language, said, expected):
    tools = offered(owner_of_a(make_user, language), user(said))
    for name in expected:
        assert shared.tool_name(name) in tools, name


@pytest.mark.parametrize(("language", "said", "tasks", "expected"), SEARCHED)
def test_the_tool_the_phrase_leaves_out_is_offered_once_the_model_searches_for_the_task(
    make_user, language, said, tasks, expected
):
    offered_once_searched(make_user, language, said, tasks, expected)  # the same check as the search's own cases
