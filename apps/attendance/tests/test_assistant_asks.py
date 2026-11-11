"""What layer 1 of the assistant's QA says of Time clock (docs plan 2026-10-31, the assistant's knowledge and QA, §3):
which tools it offers, what an employee is never offered, and that the owner's requests of the real-model QA
(hub#1099), in the owner's own words, are offered their existing operation.

Every ask of every tool of attendance bringing its tool among the first ten, role by role, in English and in Spanish,
out of the catalogue of a business with every app on and ranked as a turn ranks, is
``base/tests/test_assistant_asks.py``'s (attendance is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020``
over its asks and the guard that no ask copies a probe of layer 2.
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

#: How far down the tools a turn offers (``MAX_TOOLS``, 40) a probe of the QA may bring its tool: half of them, so the
#: tools of the apps that say their asks later may climb past it before the model loses it.
WITH_ROOM = 20
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


def test_time_clock_is_listed_so_layer_1_sweeps_every_ask_of_it():
    """Time clock is in ``LIVE_ASSISTANT_ASKS_REQUIRED``: ``base/tests/test_assistant_asks.py`` ranks each of its asks
    for every role and language, and ``live.E020`` requires them of each of its tools."""
    assert "attendance" in settings.LIVE_ASSISTANT_ASKS_REQUIRED


def test_attendance_offers_its_eighteen_tools():
    """Time clock's tools are its eighteen operations (``AI``, never ``INTERNAL``): a silent drop of a tool fails."""
    tools = {name for name, op in registry.items() if op.app_label == "attendance" and assistant.is_tool(op)}
    assert all(isinstance(registry[name].ai_spec(), AI) for name in tools)
    assert len(tools) == 18
    assert {"attendance.settings.update", "attendance.person.detail"} <= tools


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
def test_an_employee_is_never_offered_what_only_who_runs_the_team_may_do(catalog_of):
    owner = catalog_of(Membership.Role.OWNER, "es")
    employee = catalog_of(Membership.Role.EMPLOYEE, "es")
    assert NOT_THE_EMPLOYEES <= set(owner)
    assert NOT_THE_EMPLOYEES.isdisjoint(employee), sorted(NOT_THE_EMPLOYEES & set(employee))
    assert "attendance.record.clock_in" in employee  # positive control: an employee clocks their own day


def test_the_reported_requests_are_the_probes_of_layer_2():
    phrases = probe_phrases()
    assert [phrases.get(comparable(phrase)) for _, phrase in REPORTED] == [
        f"owner.es.{name}" for name, _ in REPORTED
    ]


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), REPORTED)
def test_the_reported_attendance_request_offers_its_existing_operation(catalog_of, name, phrase):
    tools = catalog_of(Membership.Role.OWNER, "es")
    place = place_of_no_ask(tools, name, phrase)
    assert place is not None and place <= WITH_ROOM, place


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize("probe", PROBES, ids=[probe["id"] for probe in PROBES])
def test_every_probe_of_the_time_clock_offers_its_tool_without_being_one_of_its_asks(catalog_of, probe):
    """The owner's eighteen phrases of layer 2, the ones the model answered right too: a tool of Time clock that a new
    ask elsewhere pushes out of the first half of the ones a turn offers fails here before the real-model QA sees it."""
    assert (probe["app"], probe["role"], probe["language"]) == ("attendance", "owner", "es")
    tools = catalog_of(Membership.Role.OWNER, probe["language"])
    name, phrase = probe["tool"], probe["phrase"]
    place = place_of_no_ask(tools, name, phrase)
    assert place is not None and place <= WITH_ROOM, place


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), OWN_WORDS)
def test_a_request_in_the_persons_own_words_reaches_its_tool_by_its_asks(catalog_of, name, phrase):
    tools = catalog_of(Membership.Role.OWNER, "es")
    assert comparable(phrase) not in probe_phrases()
    place = place_of_no_ask(tools, name, phrase)
    assert place is not None and place <= TOP, place
    before = without_its_asks(tools, name)
    assert not shared.asks_of(before[name])  # positive control: the tool is ranked without its asks
    unasked = offered_place(before, name, phrase)
    assert unasked is None or unasked > TOP, unasked


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
@pytest.mark.parametrize("role", [Membership.Role.OWNER, Membership.Role.ADMIN])
def test_who_is_clocked_in_takes_no_place_from_how_many_people_use_the_hub(catalog_of, role):
    """``base.plan.usage`` counts the people using the Hub, not who is clocked in: said as «active now», its ask was
    read as Time clock's presence too and fell to the tenth place, the last ``base/tests/test_assistant_asks.py``
    allows."""
    tools = catalog_of(role, "es")
    asks = shared.asks_of(tools["base.plan.usage"])["es"]
    places = {ask: offered_place(tools, "base.plan.usage", ask) for ask in asks}
    assert {ask: place for ask, place in places.items() if place is None or place > TOP - ROOM} == {}
