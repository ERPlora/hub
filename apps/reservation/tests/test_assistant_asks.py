"""What layer 1 of the assistant's QA says of Reservations: how many tools it offers, and that the owner's requests of
the real-model QA (hub#1105), in the owner's own words, are offered their existing operation.

Every ask of every tool of reservation bringing its tool among the first ten, role by role, in both languages, is
``base/tests/test_assistant_asks.py``'s (reservation is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020``
over the asks and the guard that no ask copies a probe of layer 2.
"""

import re

import pytest
from live import assistant as shared
from live.context import OperationContext, Scope
from live.operations import AI, Operation, registry

from base import assistant
from base.models import Membership
from base.permissions import permissions_for
from base.tests.test_assistant_asks import comparable, probe_phrases

A = Scope("host", "a")

#: The requests of hub#1105's QA (``owner.es.reservation.*`` of ``tests/e2e/qa/probes/owner-es-reservation-*.json``),
#: as the owner said them: each is offered its existing operation (among the ``MAX_TOOLS`` a turn offers, so the model
#: can choose it), without being one of its asks. ``no_show`` and ``release_unconfirmed`` the QA left out by their short
#: names (the issue's comment): they are the owner's tools too, so they are measured with the rest.
REPORTED = [
    ("reservation.blocked_date.get", "abre el bloqueo Cierre QA y dime qué día y horario impide reservar y por qué"),
    ("reservation.blocked_date.delete", "quita el bloqueo Cierre QA para volver a aceptar reservas ese día"),
    ("reservation.reservation.cancel", "cancela la reserva de Ana QA de mañana porque no puede venir y libera la mesa"),
    ("reservation.reservation.delete", "borra definitivamente la reserva de Ana QA del próximo viernes y libera la mesa 2"),
    (
        "reservation.waitlist.convert",
        "convierte la entrada de Ana QA de la lista de espera en una reserva para mañana a las 22:00",
    ),
    ("reservation.waitlist.delete", "quita a Ana QA de la lista de espera porque ya no la necesita"),
    ("reservation.reservation.no_show", "marca que Ana QA no se presentó a su reserva de mañana y libera la mesa"),
    (
        "reservation.reservation.release_unconfirmed",
        "libera ahora las reservas pendientes que ya superaron el tiempo de cortesía sin confirmar",
    ),
    # Not in the issue's table, but out of the 40 before Reservations said its asks: the first by its own asks alone.
    (
        "reservation.waitlist.get",
        "abre la entrada de Ana QA en la lista de espera y dime si está contactada o convertida",
    ),
    (
        "reservation.time_slot.get",
        "detalla la franja de reservas del viernes a las 20:00 y cuántas mesas y comensales admite",
    ),
    (
        "reservation.reservation.seat",
        "sienta a Ana QA en la mesa de su reserva de mañana y abre la cuenta con dos comensales",
    ),
]


@pytest.fixture
def catalog_of(make_user):
    """The real catalogue of the assistant of a person with ``role`` in business ``a``, in ``language``."""

    def of(role: str, language: str) -> dict[str, Operation]:
        user = make_user(f"asker-{role}", host=A.key, role=role)
        ctx = OperationContext(
            scope=A, actor=user.username, permissions=permissions_for(user, A), language=language
        )
        return assistant.catalog(ctx)

    return of


def test_reservation_offers_at_least_29_tools():
    """Reservations' tools are at least 29 (``AI``, never ``INTERNAL``): a silent drop of tools fails."""
    tools = {
        name for name, op in registry.items() if op.app_label == "reservation" and isinstance(op.ai_spec(), AI)
    }
    assert len(tools) >= 29


def test_the_reported_requests_are_the_probes_of_layer_2():
    phrases = probe_phrases()
    assert [phrases.get(comparable(phrase)) for _, phrase in REPORTED] == [
        f"owner.es.{name}" for name, _ in REPORTED
    ]


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), REPORTED)
def test_the_reported_reservation_request_offers_its_existing_operation(catalog_of, name, phrase):
    tools = catalog_of(Membership.Role.OWNER, "es")
    assert name in tools  # positive control: the owner holds the tool, so its place is known
    assert comparable(phrase) not in {comparable(ask) for ask in shared.asks_of(tools[name]).get("es", ())}
    offered = [op.name for op in assistant.relevant(tools, [phrase], "es")]
    assert name in offered, (len(offered), offered[:10])


#: What a description must never tell the model: the card of a write is the person's confirmation
#: (``base.assistant.instructions``: «call its tool: the person sees a card and confirms it before it runs»), so a tool
#: that says to ask first is asked about in the chat and never shows its card (hub#1105: cancelling, deleting,
#: unblocking and taking off the waitlist were offered 4th to 10th and the model answered without the card).
ASK_FIRST = re.compile(r"\bask\b[^.]*\b(?:first|before)\b", re.IGNORECASE)


def reservation_tools() -> dict[str, Operation]:
    return {name: op for name, op in registry.items() if op.app_label == "reservation" and assistant.is_tool(op)}


def test_no_tool_of_reservation_tells_the_model_to_ask_in_the_chat_before_its_card():
    assert ASK_FIRST.search("its table is freed. Ask first.")  # positive control: the pattern catches the old text
    assert ASK_FIRST.search("the ones it had stay. Always ask the person before.")  # and its other wordings
    assert not ASK_FIRST.search("Use it to answer what they ask. Free it or move the reservation first.")
    told = {name for name, op in reservation_tools().items() if ASK_FIRST.search(shared.description(op))}
    assert told == set()


#: Where a description sends the model for what the person names (hub#1105): somebody on the waitlist is booked by
#: converting their entry, never by a second reservation; a block named by its reason («the Christmas closure») is
#: found in the list, which gives each one with its reason, instead of asking the person for its date.
POINTERS = [
    ("reservation.reservation.create", "reservation.waitlist.convert"),
    ("reservation.blocked_date.get", "reservation.blocked_date.list"),
    ("reservation.blocked_date.delete", "reservation.blocked_date.list"),
]


@pytest.mark.parametrize(("name", "pointed"), POINTERS)
def test_the_description_points_at_the_tool_of_what_the_person_names(name, pointed):
    tools = reservation_tools()
    assert pointed in tools  # the tool it names is one the model can call
    assert pointed in shared.description(tools[name])
