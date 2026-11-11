"""What layer 1 of the assistant's QA says of Schedules (docs plan 2026-10-31, the assistant's knowledge and QA, §3):
which tools it offers, what an employee is never offered, and that the owner's requests of the real-model QA (hub#1096),
in the owner's own words, are offered their existing operation before Appointments' blocks.

Every ask of every tool of schedule bringing its tool among the first ten, role by role, in English and in Spanish, out
of the catalogue of a business with every app on and ranked as a turn ranks, is ``base/tests/test_assistant_asks.py``'s
(schedule is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020`` over its asks and the guard that no ask
copies a probe of layer 2.
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
#: What changes the business's opening hours (``schedule.add``, ``schedule.change``, ``schedule.delete``,
#: ``schedule.manage_settings``): an employee reads the hours (``schedule.view``), never these.
NOT_THE_EMPLOYEES = {
    "schedule.week.set_day",
    "schedule.week.confirm",
    "schedule.special_day.create",
    "schedule.special_day.bulk_create",
    "schedule.special_day.update",
    "schedule.special_day.delete",
    "schedule.override.create",
    "schedule.override.update",
    "schedule.override.delete",
    "schedule.settings.update",
}

#: The requests of hub#1096's QA (``tests/e2e/qa/probes/owner-es-schedule-2026-11-08.json``) as the owner said them,
#: and nothing of the tools' ``asks``: before Schedules said its asks, none of these tools was among the ones a turn
#: offers (``MAX_TOOLS``), so the model closed the business with a block of Appointments, said it had no tool to load
#: two holidays or to change one, and offered to delete a temporary change and make it again to correct its end; the
#: hours of each day of a week were answered with the usual week, which says nothing of where each day's hours come
#: from.
REPORTED = [
    (
        "schedule.override.create",
        "cierra el negocio del 23 al 24 de noviembre por obras y llama al cambio Cambio QA 2",
    ),
    (
        "schedule.special_day.bulk_create",
        "añade de una vez Constitución QA el 7 de enero de 2027 y Laborable QA el 8 de enero de 2027, ambos cerrados",
    ),
    (
        "schedule.override.update",
        "corrige Cambio QA para que termine el 21 de noviembre y siga cerrado por obras",
    ),
    (
        "schedule.special_day.update",
        "cambia Festivo QA para abrir de 09:00 a 13:00 en vez de cerrar",
    ),
    (
        "schedule.hours.for_range",
        "dime los horarios de apertura de cada día de esta semana y de dónde sale cada uno",
    ),
]
#: The reported writes the model answered with a block of Appointments (``appointment.blocked_time.*``), which closes
#: the agenda of the professionals, never the business.
TAKEN_FOR_A_BLOCK = [(name, phrase) for name, phrase in REPORTED if name != "schedule.hours.for_range"]

#: How far down the tools a turn offers (``MAX_TOOLS``, 40) a probe of the QA may bring its tool: half of them, so the
#: tools of the apps that say their asks later may climb past it before the model loses it.
WITH_ROOM = 20
#: Every probe of layer 2 of Schedules, the owner's real phrases of the QA: the five above and the ones the model got
#: right.
PROBES = json.loads(
    (Path(settings.BASE_DIR) / "tests" / "e2e" / "qa" / "probes" / "owner-es-schedule-2026-11-08.json").read_text(
        encoding="utf-8"
    )
)["probes"]

#: What a person says in words of their own, neither an ask nor a probe of layer 2, one per tool of Schedules: each
#: reaches its tool among the first ten by the tool's asks, and without them it does not, so asks that stop reading
#: as people speak fail here.
OWN_WORDS = [
    ("schedule.week.get", "¿qué días cerramos normalmente y a qué hora solemos abrir?"),
    ("schedule.special_day.list", "¿qué fiestas tengo apuntadas en el calendario?"),
    ("schedule.override.list", "¿tengo programadas vacaciones o reformas con otras horas?"),
    ("schedule.settings.get", "¿el calendario me lo enseña empezando en lunes o en domingo?"),
    ("schedule.business.is_open", "¿a estas horas tenemos el local abierto?"),
    ("schedule.hours.for_range", "¿a qué horas atendemos cada día de la primera quincena de diciembre?"),
    ("schedule.week.set_day", "los sábados a partir de ahora cerramos a mediodía"),
    ("schedule.week.confirm", "lo que me propusiste para cada día está bien, dalo por bueno"),
    ("schedule.special_day.create", "el 15 de agosto no abrimos, es fiesta del pueblo"),
    ("schedule.special_day.bulk_create", "apunta las fiestas nacionales de 2027 todas juntas"),
    ("schedule.special_day.update", "el día de Reyes al final abrimos por la mañana"),
    ("schedule.special_day.delete", "quita la fiesta del pueblo, ese día trabajamos"),
    ("schedule.override.create", "del 1 al 15 de agosto cerramos por vacaciones"),
    ("schedule.override.update", "las vacaciones de agosto al final acaban el día 20"),
    ("schedule.override.delete", "borra el cierre por vacaciones de agosto, este año no paramos"),
    ("schedule.settings.update", "quiero que el calendario arranque en domingo"),
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


def test_schedules_is_listed_so_layer_1_sweeps_every_ask_of_it():
    """Schedules is in ``LIVE_ASSISTANT_ASKS_REQUIRED``: ``base/tests/test_assistant_asks.py`` ranks each of its asks
    for every role and language, and ``live.E020`` requires them of each of its tools."""
    assert "schedule" in settings.LIVE_ASSISTANT_ASKS_REQUIRED


def test_schedule_offers_its_sixteen_tools():
    """Schedules' tools are its sixteen operations (``AI``, never ``INTERNAL``; the two reads of the card of a write
    are not tools): a silent drop of a tool fails."""
    tools = {name for name, op in registry.items() if op.app_label == "schedule" and assistant.is_tool(op)}
    assert all(isinstance(registry[name].ai_spec(), AI) for name in tools)
    assert tools == {name for name, _ in OWN_WORDS}
    assert len(tools) == 16


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
def test_an_employee_is_never_offered_a_change_of_the_opening_hours(catalog_of):
    owner = catalog_of(Membership.Role.OWNER, "es")
    employee = catalog_of(Membership.Role.EMPLOYEE, "es")
    assert NOT_THE_EMPLOYEES <= set(owner)
    assert NOT_THE_EMPLOYEES.isdisjoint(employee), sorted(NOT_THE_EMPLOYEES & set(employee))
    assert "schedule.business.is_open" in employee  # positive control: an employee reads whether the business is open


def test_the_reported_requests_are_the_probes_of_layer_2():
    phrases = probe_phrases()
    assert [phrases.get(comparable(phrase)) for _, phrase in REPORTED] == [f"owner.es.{name}" for name, _ in REPORTED]


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), REPORTED)
def test_the_reported_schedule_request_offers_its_existing_operation(catalog_of, name, phrase):
    tools = catalog_of(Membership.Role.OWNER, "es")
    place = place_of_no_ask(tools, name, phrase)
    assert place is not None and place <= WITH_ROOM, place


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), TAKEN_FOR_A_BLOCK)
def test_a_reported_change_of_the_hours_is_offered_before_any_block_of_appointments(catalog_of, name, phrase):
    """What the model chose instead (hub#1096): each block of Appointments a turn offers comes after the tool of
    Schedules, so a new ask of Appointments that puts a block first fails here before the real-model QA sees it."""
    tools = catalog_of(Membership.Role.OWNER, "es")
    blocks = sorted(other for other in tools if other.startswith("appointment.blocked_time."))
    assert blocks  # positive control: the owner holds Appointments' blocks, so they compete for the phrase
    place = place_of_no_ask(tools, name, phrase)
    assert place is not None
    ahead = {block: offered_place(tools, block, phrase) for block in blocks}
    assert {block: at for block, at in ahead.items() if at is not None and at < place} == {}, place


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize("probe", PROBES, ids=[probe["id"] for probe in PROBES])
def test_every_probe_of_schedules_offers_its_tool_without_being_one_of_its_asks(catalog_of, probe):
    """The owner's sixteen phrases of layer 2, the ones the model answered right too: a tool of Schedules that a new
    ask elsewhere pushes out of the first half of the ones a turn offers fails here before the real-model QA sees it."""
    assert (probe["app"], probe["role"], probe["language"]) == ("schedule", "owner", "es")
    tools = catalog_of(Membership.Role.OWNER, probe["language"])
    place = place_of_no_ask(tools, probe["tool"], probe["phrase"])
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
