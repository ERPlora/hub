"""What layer 1 of the assistant's QA says of Time clock: which tools it offers, what an employee is never offered,
and that the owner's requests of the real-model QA (hub#1099), in the owner's own words, are offered their existing
operation.

Every ask of every tool of attendance bringing its tool among the first ten, role by role, in English and in Spanish,
out of the catalogue of a business with every app on and ranked as a turn ranks, is
``base/tests/test_assistant_asks.py``'s (attendance is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020``
over its asks and the guard that no ask copies a probe of layer 2.
"""

import json
from pathlib import Path

import pytest
from django.apps import apps
from django.conf import settings
from live import assistant as shared
from live.operations import AI, registry

from base import assistant
from base.models import Membership
from base.tests.roles import WORKING_ROLES
from base.tests.test_assistant_asks import OWNER, TOP
from base.tests.test_assistant_asks import assert_its_words_name, assert_offered_with_room, by_group_test
from base.tests.test_assistant_asks import assert_reported_are_owner_probes, offered_place
from base.tests.test_assistant_asks import comparable, offered_to, probe_phrases
from base.tests.test_assistant_asks import english_coverage_test, english_words_test, own_words_test, probes_test
from base.tests.test_assistant_asks import reported_test

from .conftest import HUB_DB, in_hubs

#: What only who sees, corrects or sets up the team's time clock holds (``attendance.view_all``,
#: ``attendance.correct``, ``attendance.manage_settings``): an employee clocks and reads their own days, never these.
NOT_THE_EMPLOYEES = {
    "attendance.settings.update",
    "attendance.record.correct",
    "attendance.record.review_stale",
    "attendance.record.close_for_terminated",
    "attendance.presence.list",
    "attendance.presence.count",
    "attendance.person.list",
}

#: The requests of hub#1099's QA (``tests/e2e/qa/probes/owner-es-attendance-2026-11-08.json``) as the owner said them,
#: and nothing of the tools' ``asks``: before Time clock said its asks, asking to require the location with a radius
#: offered no ``attendance.settings.update`` (the model explained the screen instead of showing its card), and opening a
#: person's record of the time clock fell out of the tools a turn offers (``MAX_TOOLS``) once Cash register's tools,
#: whose asks say «abre», were listed (hub#1139).
REPORTED = [
    (
        "attendance.settings.update",
        "exige ubicación al fichar desde un móvil personal, con un radio de 250 metros alrededor del local",
    ),
    (
        "attendance.person.detail",
        "abre la ficha de personal de Fichaje QA en el control horario y dime si sigue activa",
    ),
]

#: Every probe of layer 2 of Time clock, the owner's real phrases of the QA: the two above and the ones the model got
#: right (or answered with an equivalent list).
PROBES = json.loads(
    (Path(settings.BASE_DIR) / "tests" / "e2e" / "qa" / "probes" / "owner-es-attendance-2026-11-08.json").read_text(
        encoding="utf-8"
    )
)["probes"]

#: What a person says in words of their own, neither an ask nor a probe of layer 2, for the nine tools whose probe a
#: turn already offered by their name and description before Time clock said its asks: here it is their asks that
#: bring the tool among the first ten, so asks that stop reading as people speak fail.
OWN_WORDS = [
    ("attendance.presence.count", "¿cuánta gente tengo fichada a esta hora?"),
    ("attendance.record.list", "¿qué días fichó Javier esta semana?"),
    ("attendance.correction.list", "¿por qué se cambió la jornada de ayer?"),
    ("attendance.person.list", "¿qué gente sale en el filtro de persona?"),
    ("attendance.record.export", "necesito las jornadas del mes para la inspección de trabajo"),
    ("attendance.record.clock_in", "Javier acaba de llegar"),
    ("attendance.record.clock_out", "Elena ya se ha ido a casa"),
    ("attendance.break.start", "salgo a comer"),
    ("attendance.record.close_for_terminated", "acabo de despedir a Elena y su fichaje sigue abierto"),
]
#: The places an ask of another app keeps free below the first ten: the asks of the next app to say its own take them.
ROOM = 2


def test_time_clock_is_listed_so_layer_1_sweeps_every_ask_of_it():
    """Time clock is in ``LIVE_ASSISTANT_ASKS_REQUIRED``: ``base/tests/test_assistant_asks.py`` ranks each of its asks
    for every role and language, and ``live.E020`` requires them of each of its tools."""
    assert "attendance" in settings.LIVE_ASSISTANT_ASKS_REQUIRED


def test_attendance_offers_its_eighteen_tools():
    """Time clock's tools are its eighteen operations (``AI``, never ``INTERNAL``): a silent drop of a tool fails."""
    tools = {name for name, op in registry.items() if op.app_label == "attendance" and assistant.tools.is_tool(op)}
    assert all(isinstance(registry[name].ai_spec(), AI) for name in tools)
    assert len(tools) == 18
    assert {"attendance.settings.update", "attendance.person.detail"} <= tools


@HUB_DB  # the catalogue is of the apps on in the business (base.activation) and of the person's role
def test_an_employee_is_never_offered_what_only_who_runs_the_team_may_do(catalog_of):
    owner = catalog_of(Membership.Role.OWNER, "es")
    employee = catalog_of(Membership.Role.EMPLOYEE, "es")
    assert NOT_THE_EMPLOYEES <= set(owner)
    assert NOT_THE_EMPLOYEES.isdisjoint(employee), sorted(NOT_THE_EMPLOYEES & set(employee))
    assert "attendance.record.clock_in" in employee  # positive control: an employee clocks their own day


def test_the_reported_requests_are_the_probes_of_layer_2():
    assert_reported_are_owner_probes(REPORTED)


test_the_reported_attendance_request_offers_its_existing_operation = in_hubs(reported_test(REPORTED))


#: The owner's eighteen phrases of layer 2, the ones the model answered right too: a tool of Time clock that a new ask
#: elsewhere pushes out of the first half of the ones a turn offers fails here before the real-model QA sees it.
test_every_probe_of_the_time_clock_offers_its_tool_without_being_one_of_its_asks = in_hubs(
    probes_test(PROBES, "attendance")
)


test_a_request_in_the_persons_own_words_reaches_its_tool_by_its_asks = in_hubs(own_words_test(OWN_WORDS, "es"))


#: What the owner says in English in words of their own for each tool of Time clock that needs one, neither
#: an ask nor a probe of layer 2: its English asks lift it among the first ten (``assert_its_asks_lift``).
OWN_WORDS_EN = [
    ("attendance.break.end", "I'm back from lunch"),
    ("attendance.break.start", "put me on lunch"),
    ("attendance.correction.list", "who changed Marisa's day and why?"),
    ("attendance.person.detail", "has Marisa left the business?"),
    ("attendance.person.list", "whose days can I see?"),
    ("attendance.presence.count", "how many have I got clocked in at this hour?"),
    ("attendance.presence.list", "who's still working, and since when?"),
    ("attendance.record.clock_in", "Javier has just arrived"),
    ("attendance.record.clock_out", "I'm leaving now, end my day"),
    ("attendance.record.close_for_terminated", "I just let Marisa go and her day is still open"),
    ("attendance.record.correct", "Marisa left at 6 on Monday, fix her day"),
    ("attendance.record.current", "my day so far: how long have I worked?"),
    ("attendance.record.detail", "show me Marisa's Monday with its breaks"),
    ("attendance.record.export", "the labour people want October's days"),
    ("attendance.record.list", "which days did Javier clock in during October?"),
    ("attendance.record.review_stale", "look for days left open too long and flag them"),
    ("attendance.settings.get", "how big is the radius we allow for clocking in?"),
    ("attendance.settings.update", "ask for the location when people use their own phone"),
]
test_a_request_in_english_is_lifted_by_its_english_asks = in_hubs(english_words_test(OWN_WORDS_EN))
test_each_tool_has_its_own_english_words = english_coverage_test("attendance", OWN_WORDS_EN)


@HUB_DB  # the catalogue is of the apps on in the business (base.activation) and of the person's role
@pytest.mark.parametrize("role", [Membership.Role.OWNER, Membership.Role.ADMIN])
def test_who_is_clocked_in_takes_no_place_from_how_many_people_use_the_hub(catalog_of, role):
    """``base.plan.usage`` counts the people using the Hub, not who is clocked in: said as «active now», its ask was
    read as Time clock's presence too and fell to the tenth place, the last ``base/tests/test_assistant_asks.py``
    allows."""
    tools = catalog_of(role, "es")
    asks = shared.asks_of(tools["base.plan.usage"])["es"]
    places = {ask: offered_place(tools, "base.plan.usage", ask) for ask in asks}
    assert {ask: place for ask, place in places.items() if place is None or place > TOP - ROOM} == {}


#: Clocking out or in said as a person says it, «registra» or «apunta» «mi salida» or «mi entrada». The tools' asks say
#: «fíchame», so without Time clock's group of words none of these is among the first ten: creating an appointment, a
#: cash movement or a WhatsApp note came first.
CLOCKING_SAID = [
    ("attendance.record.clock_out", "registra mi salida", "mi salida"),
    ("attendance.record.clock_out", "apunta mi salida", "mi salida"),
    ("attendance.record.clock_out", "quiero registrar mi salida", "mi salida"),
    ("attendance.record.clock_in", "registra mi entrada", "mi entrada"),
    ("attendance.record.clock_in", "apunta mi entrada", "mi entrada"),
]

test_clocking_said_as_a_person_says_it_brings_its_tool_by_time_clocks_group = in_hubs(by_group_test(CLOCKING_SAID))


@HUB_DB  # the catalogue is of the apps on in the business (base.activation) and of the person's role
@pytest.mark.parametrize("role", WORKING_ROLES)
@pytest.mark.parametrize(("name", "phrase", "word"), CLOCKING_SAID)
def test_whoever_clocks_is_offered_the_clock_by_mi_salida_or_mi_entrada(catalog_of, role, name, phrase, word):
    assert_offered_with_room(catalog_of(role, "es"), name, phrase, room=TOP)


#: The same said in English: «my departure», «my exit» or «my arrival» after «record» or «log».
CLOCKING_SAID_EN = [
    ("attendance.record.clock_out", "record my departure", "my departure"),
    ("attendance.record.clock_out", "log my exit", "my exit"),
    ("attendance.record.clock_in", "record my arrival", "my arrival"),
]


@HUB_DB  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase", "word"), CLOCKING_SAID_EN)
def test_clocking_said_in_english_brings_its_tool_by_time_clocks_group(catalog_of, name, phrase, word):
    tools = catalog_of(OWNER, "en")
    assert comparable(phrase) not in probe_phrases()
    assert_offered_with_room(tools, name, phrase, "en", room=TOP)
    counted = assistant.relevance.ranking(tools)["synonyms"]
    without = tuple(group for group in counted if word not in group)
    assert len(without) == len(counted) - 1  # positive control: exactly its group is left out
    assert name not in offered_to(tools, phrase, "en", synonyms=without)[:TOP]


#: «Entrada» and «salida» said of anything but a person's own clocking: goods received, the drawer's money, a place in
#: the waiting list, what left the kitchen's pass. «La salida de», «su entrada» and «una salida» say those too, and so
#: do «arrival», «departure» and «exit» in English without «my».
OTHER_EXITS = [
    "registra la entrada de mercancía del albarán de hoy",
    "registra su entrada de mercancía",
    "apúntame una entrada de 50 € en el turno",
    "registra la salida de 20 € de la caja",
    "registra una salida de 15 € para hielo en el turno",
    "abre su entrada en la lista de espera",
    "abre la entrada de Ana en la lista de espera",
    "la comanda y su salida del pase",
    "la 12 ya ha salido del pase",
    "the bank transfer has arrived",
    "the departure of table 12's order from the pass",
    "log the exit of 20 € from the drawer",
]


def test_the_hub_reads_mi_salida_or_mi_entrada_as_clocking_and_no_other_exit():
    """Time clock's own words (its ``assistant_synonyms``): «mi salida», «mi entrada» and their English are clocking
    (``attendance.record.clock_*``), and without the Hub's groups none is (positive control); the other senses of
    «entrada» and «salida» name no clocking."""
    clock = shared.stem("clock")
    assert_its_words_name(
        "attendance",
        [
            ("registra mi salida", clock),
            ("apunta mi entrada", clock),
            ("record my departure", clock),
            ("log my exit", clock),
            ("log my arrival", clock),
        ],
    )
    own = apps.get_app_config("attendance").assistant_synonyms
    named = [said for said in OTHER_EXITS if any(clock in one for one in shared.asked([said], own).concepts)]
    assert named == []
