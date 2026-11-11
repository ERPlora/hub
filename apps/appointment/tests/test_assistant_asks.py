"""What layer 1 of the assistant's QA says of Appointments (erplora-next docs/plans/2026-10-31-asistente-conocimiento-y-qa.md,
§3): how many tools it offers, and that the owner's requests of the real-model QA (hub#1097), in the owner's own words,
are offered their existing operation, ahead of Online booking's twin when both could do it.

Every ask of every tool of appointment bringing its tool among the first ten, role by role, in both languages, is
``base/tests/test_assistant_asks.py``'s (appointment is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020``
over the asks and the guard that no ask copies a probe of layer 2.
"""

import dataclasses
import json
from pathlib import Path

import pytest
from django.conf import settings
from live import assistant as shared
from live.context import OperationContext, Scope
from live.operations import AI, Operation, registry

from base import assistant
from base.models import Membership
from base.permissions import permissions_for
from base.tests.test_assistant_asks import TOP, comparable, probe_phrases

A = Scope("host", "a")

#: The requests of hub#1097's QA (``tests/e2e/qa/probes/owner-es-appointment-2026-11-08.json``), as the owner said them,
#: and nothing of the tools' ``asks``: before Appointments said its asks, the blocks of the agenda and generating the
#: dates of a series were not offered at all, and checking whether a time can be booked neither (not in the issue's
#: table, measured with it); deleting a series came 11th.
REPORTED = [
    ("appointment.blocked_time.list", "¿qué bloqueos de agenda afectan a esta semana, incluido Bloqueo QA?"),
    ("appointment.blocked_time.delete", "quita Bloqueo QA para volver a permitir reservas ese día"),
    (
        "appointment.appointment.bulk_delete",
        "borra a la vez las dos citas de Ana QA del 11 de noviembre a las 10:00 y a las 11:00",
    ),
    ("appointment.appointment.confirm", "confirma la cita pendiente de Ana QA de mañana para dejarla reservada"),
    ("appointment.recurring.delete", "elimina la serie semanal de Ana QA pero conserva las citas sueltas que ya generó"),
    (
        "appointment.recurring.materialize",
        "genera ahora las citas de la serie semanal de Ana QA que falten dentro de la ventana de reservas",
    ),
    (
        "appointment.settings.update",
        "exige al menos dos horas de antelación para reservar y no confirmes automáticamente las citas de la web",
    ),
    (
        "appointment.availability.check",
        "comprueba si Camarera Ventas QA puede atender un Corte QA mañana a las 13:00 y, si no puede, dime el motivo",
    ),
]
#: How far down the tools a turn offers (``MAX_TOOLS``, 40) a request of the QA may bring its tool: the first ten for
#: the ones the issue reports, half of them for every other probe, so the tools of the apps that say their asks later
#: may climb past them before the model loses them.
REPORTED_TOP = TOP
WITH_ROOM = 20
#: Every probe of layer 2 of Appointments, the owner's real phrases of the QA: the ones above and the ones the model got
#: right.
PROBES = json.loads(
    (Path(settings.BASE_DIR) / "tests" / "e2e" / "qa" / "probes" / "owner-es-appointment-2026-11-08.json").read_text(
        encoding="utf-8"
    )
)["probes"]
#: The reported requests the model answered with Online booking's twin (``online_booking.booking.confirm``,
#: ``online_booking.settings.update``): an appointment the customer booked online is still an appointment of the
#: agenda, and the booking rules are the agenda's, so Appointments' own tool is offered before.
TWINS = [
    ("appointment.appointment.confirm", "online_booking.booking.confirm"),
    ("appointment.settings.update", "online_booking.settings.update"),
]


@pytest.fixture
def catalog_of(make_user):
    """The real catalogue of the assistant of a person with ``role`` in business ``a``, in ``language``."""

    def of(role: str, language: str) -> dict[str, Operation]:
        user = make_user(f"asker-{role}", host=A.key, role=role)
        ctx = OperationContext(scope=A, actor=user.username, permissions=permissions_for(user, A), language=language)
        return assistant.catalog(ctx)

    return of


def offered_place(tools: dict[str, Operation], name: str, phrase: str) -> int | None:
    """The place a turn offers ``name`` at for ``phrase`` (1 is first), ``None`` when it is not offered at all."""
    offered = [op.name for op in assistant.relevant(tools, [phrase], "es")]
    return offered.index(name) + 1 if name in offered else None


def place_of_no_ask(tools: dict[str, Operation], name: str, phrase: str) -> int | None:
    """``offered_place`` of a tool the person holds for a ``phrase`` that is none of its asks in Spanish."""
    assert name in tools  # positive control: the owner holds the tool, so its place is known
    assert comparable(phrase) not in {comparable(ask) for ask in shared.asks_of(tools[name]).get("es", ())}
    return offered_place(tools, name, phrase)


def without_its_asks(tools: dict[str, Operation], name: str) -> dict[str, Operation]:
    """``tools`` with ``name`` saying no asks: how a turn ranked it by its name and description alone."""
    op = tools[name]
    return {**tools, name: dataclasses.replace(op, ai={key: value for key, value in op.ai.items() if key != "asks"})}


def appointment_tools() -> dict[str, Operation]:
    return {name: op for name, op in registry.items() if op.app_label == "appointment" and assistant.is_tool(op)}


def test_appointments_is_listed_so_layer_1_sweeps_every_ask_of_it():
    """Appointments is in ``LIVE_ASSISTANT_ASKS_REQUIRED``: ``base/tests/test_assistant_asks.py`` ranks each of its asks
    for every role and language, and ``live.E020`` requires them of each of its tools."""
    assert "appointment" in settings.LIVE_ASSISTANT_ASKS_REQUIRED


def test_appointment_offers_its_thirty_five_tools():
    """Appointments' tools are its thirty-five operations (``AI``, never ``INTERNAL``): a silent drop of a tool fails."""
    tools = appointment_tools()
    assert all(isinstance(op.ai_spec(), AI) for op in tools.values())
    assert len(tools) == 35
    assert {name for name, _ in REPORTED} <= set(tools)


def test_the_reported_requests_are_the_probes_of_layer_2():
    phrases = probe_phrases()
    assert [phrases.get(comparable(phrase)) for _, phrase in REPORTED] == [
        f"owner.es.{name}" for name, _ in REPORTED
    ]


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), REPORTED)
def test_the_reported_appointment_request_offers_its_existing_operation(catalog_of, name, phrase):
    tools = catalog_of(Membership.Role.OWNER, "es")
    place = place_of_no_ask(tools, name, phrase)
    assert place is not None and place <= REPORTED_TOP, place


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize("probe", PROBES, ids=[probe["id"] for probe in PROBES])
def test_every_probe_of_appointments_offers_its_tool_without_being_one_of_its_asks(catalog_of, probe):
    """The owner's thirty-five phrases of layer 2, the ones the model answered right too: a tool of Appointments that a
    new ask elsewhere pushes out of the first half of the ones a turn offers fails here before the real-model QA sees
    it."""
    assert (probe["app"], probe["role"], probe["language"]) == ("appointment", "owner", "es")
    tools = catalog_of(Membership.Role.OWNER, probe["language"])
    place = place_of_no_ask(tools, probe["tool"], probe["phrase"])
    assert place is not None and place <= WITH_ROOM, place


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "twin"), TWINS)
def test_the_reported_request_offers_appointments_tool_before_online_bookings_twin(catalog_of, name, twin):
    tools = catalog_of(Membership.Role.OWNER, "es")
    assert twin in tools  # positive control: Online booking is on in business a, so its twin competes
    phrase = dict(REPORTED)[name]
    place, twins = place_of_no_ask(tools, name, phrase), offered_place(tools, twin, phrase)
    assert place is not None and (twins is None or place < twins), (place, twins)


def test_removing_a_block_named_by_its_title_points_at_the_list_that_finds_it():
    """A block is removed by its id, and a person names it by its title («quita el bloqueo de la formación»): the
    description sends the model to ``appointment.blocked_time.list`` from today on, instead of asking the person for its
    date (hub#1097: «Pide la fecha, sin tarjeta»)."""
    tools = appointment_tools()
    assert "appointment.blocked_time.list" in tools  # the tool it names is one the model can call
    assert "appointment.blocked_time.list" in shared.description(tools["appointment.blocked_time.delete"])
