"""What layer 1 of the assistant's QA says of Online booking: its fifteen tools, and that the owner's requests of the
real-model QA (hub#1107), in the owner's own words, are offered their existing operation.

Every ask of every tool of online_booking bringing its tool among the first ten, role by role, in English and in
Spanish, out of the catalogue of a business with every app on and ranked as a turn ranks, is
``base/tests/test_assistant_asks.py``'s (online_booking is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020``
over its asks and the guards that no ask copies a probe of layer 2 and no test here ranks an ask as a person's words.
"""

import json
from pathlib import Path

import pytest
from django.conf import settings
from live import assistant as shared
from live.operations import AI, registry

from base import assistant
from base.models import Membership
from base.tests.test_assistant_asks import (
    TOP,
    assert_its_asks_bring,
    assert_offered_with_room,
    catalog_of,  # noqa: F401 (a fixture: the tests below take it by name)
    comparable,
    probe_phrases,
)

#: The requests of hub#1107's QA (``tests/e2e/qa/probes/owner-es-online_booking-2026-11-08.json``), as the owner said
#: them, and nothing of the tools' ``asks``: before Online booking said its asks, booking from the public page as the
#: customer came 12th, past the first ten the model weighs, and the services the page offers 13th (below the first ten
#: since Services said its asks, hub#1169). Deleting a booking came 5th: what kept its card from showing was the
#: description telling the model to ask in the chat first, which hub#1176 takes out of every tool of the Hub.
REPORTED = [
    (
        "online_booking.public.book",
        "como si fuera la clienta Web QA, reserva online un Corte QA para mañana a las 13:00, móvil 611 999 888, con "
        "cualquier profesional",
    ),
    ("online_booking.booking.delete", "elimina de la bandeja y de la agenda la reserva APT-20261109-0002"),
    (
        "online_booking.public.services",
        "¿qué servicios puede reservar una clienta en la web, con precio y duración?",
    ),
]
PROBES_DIR = Path(settings.BASE_DIR) / "tests" / "e2e" / "qa" / "probes"
#: Every probe of layer 2 of Online booking, the owner's real phrases of the QA: the ones above and the ones the model
#: answered right.
PROBES = [
    probe
    for path in sorted(PROBES_DIR.glob("*.json"))
    for probe in json.loads(path.read_text(encoding="utf-8"))["probes"]
    if probe["app"] == "online_booking"
]
#: What a person says in words of their own, neither an ask nor a probe of layer 2, one per tool of Online booking: each
#: reaches its tool among the first ten by its asks and not without them, so asks that stop reading as people speak fail
#: here, tool by tool. None says «reserva» beside the verb of its tool (a booking named with its verb, «anula la
#: reserva», brings the tool by its name alone), «ahora», «hoy» or «ya» (read by half the Hub's tools), nor more than two
#: content words of any one of its asks: an ask said in another order is no phrase of a person's own (hub#1179).
OWN_WORDS = [
    ("online_booking.booking.list", "¿alguna clienta ha cogido hora por internet esta semana?"),
    ("online_booking.booking.get", "Ainhoa llama por lo suyo del miércoles, ¿qué es?"),
    ("online_booking.settings.get", "¿qué tiene que dejar una clienta para reservar por internet?"),
    ("online_booking.settings.update", "que la web de reservas salude con un «Hola, guapa»"),
    ("online_booking.public.page", "¿qué color y qué logo lleva la web de reservas?"),
    ("online_booking.public.services", "¿qué tratamientos dejo coger por la web?"),
    ("online_booking.public.slots", "el martes, ¿qué horas le quedan a cualquiera en la web?"),
    ("online_booking.public.booking", "¿qué datos tiene Leire en su enlace?"),
    ("online_booking.public.book", "Maite quiere unas mechas el sábado por internet, con cualquiera"),
    ("online_booking.public.cancel", "deja libre lo de Leire usando su enlace"),
    ("online_booking.booking.confirm", "dile que sí a Nerea con lo de internet"),
    ("online_booking.booking.complete", "lo de la bandeja de Nerea, márcalo como acabado"),
    ("online_booking.booking.no_show", "ni rastro de Olga ayer, faltó sin avisar"),
    ("online_booking.booking.cancel", "a Olga le ha surgido algo, rechaza lo del jueves"),
    ("online_booking.booking.delete", "fuera de la bandeja lo repetido de Olga"),
]


def online_booking_tools() -> list[str]:
    return sorted(name for name, op in registry.items() if op.app_label == "online_booking" and assistant.is_tool(op))


def test_online_booking_is_listed_so_layer_1_sweeps_every_ask_of_it():
    """Online booking is in ``LIVE_ASSISTANT_ASKS_REQUIRED``: ``base/tests/test_assistant_asks.py`` ranks each of its
    asks for every role and language, and ``live.E020`` requires them of each of its tools."""
    assert "online_booking" in settings.LIVE_ASSISTANT_ASKS_REQUIRED


def test_online_booking_offers_its_fifteen_tools():
    """Online booking's tools are its fifteen operations (``AI``, never ``INTERNAL``): a silent drop of a tool fails.
    The platform's reaction to a customer's erasure is none."""
    tools = online_booking_tools()
    assert all(isinstance(registry[name].ai_spec(), AI) for name in tools)
    assert len(tools) == 15
    assert {name for name, _ in REPORTED} <= set(tools)
    assert "online_booking.customer.erase" not in tools


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), REPORTED)
def test_the_reported_request_offers_its_existing_operation_among_the_first_ten(catalog_of, name, phrase):
    assert probe_phrases().get(comparable(phrase)) == f"owner.es.{name}"  # the owner's own words, as the QA said them
    assert_offered_with_room(catalog_of(Membership.Role.OWNER, "es"), name, phrase, room=TOP)


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize("probe", PROBES, ids=[probe["id"] for probe in PROBES])
def test_every_probe_of_online_booking_offers_its_tool_without_being_one_of_its_asks(catalog_of, probe):
    """The owner's fifteen phrases of layer 2, the ones the model answered right too: a tool of Online booking that a
    new ask elsewhere pushes out of the first half of the ones a turn offers fails here before the real-model QA sees
    it."""
    assert (probe["role"], probe["language"]) == ("owner", "es")
    tools = catalog_of(Membership.Role.OWNER, probe["language"])
    assert_offered_with_room(tools, probe["tool"], probe["phrase"], probe["language"])


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), OWN_WORDS)
def test_a_request_in_the_persons_own_words_reaches_its_tool_by_its_asks(catalog_of, name, phrase):
    assert_its_asks_bring(catalog_of(Membership.Role.OWNER, "es"), name, phrase, "es")


#: Where booking as the customer sends the model for what it takes (hub#1107: «payload inválido» and
#: ``assistant.too_many_steps``): the services are sent by their ids, which the page's services give, and the time is
#: one of the page's free times.
POINTERS = ["online_booking.public.services", "online_booking.public.slots"]


@pytest.mark.parametrize("pointed", POINTERS)
def test_booking_as_the_customer_points_at_the_reads_that_give_what_it_takes(pointed):
    assert pointed in online_booking_tools()  # the tool it names is one the model can call
    assert pointed in shared.description(registry["online_booking.public.book"])


def test_every_tool_of_online_booking_has_a_phrase_of_its_own():
    """``OWN_WORDS`` covers every tool once: a tool whose asks no phrase of a person's own reaches would let its asks
    change unseen (the sweep of ``base`` ranks only the asks themselves)."""
    assert sorted(name for name, _ in OWN_WORDS) == online_booking_tools()
