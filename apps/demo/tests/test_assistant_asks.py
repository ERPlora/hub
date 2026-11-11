"""What layer 1 of the assistant's QA does not say of Demo (docs plan 2026-10-31, the assistant's knowledge and QA, §3):
how many tools it offers, what an employee is never offered, and that the requests of the real-model QA (hub#1095), in
the words each role said them, are offered their existing operation, and with it the read that finds the item by its
name.

Every ask of every tool of demo bringing its tool among the first ten, role by role, in both languages, is
``base/tests/test_assistant_asks.py``'s (demo is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020`` over the
asks and the guard that no ask copies a probe of layer 2.
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
from base.tests.test_assistant_asks import comparable, probe_phrases

A = Scope("host", "a")
OWNER, EMPLOYEE = Membership.Role.OWNER, Membership.Role.EMPLOYEE
#: The role of a probe as its file says it (``"role": "owner"``).
PROBE_ROLE = {"owner": OWNER, "employee": EMPLOYEE}
#: What only who manages the items may do (``demo.manage``): an employee, who only views, is never offered it. Adding a
#: line is theirs too, with a manager's approval (``DemoConfig.approvals``).
NOT_THE_EMPLOYEES = {"demo.item.create", "demo.item.update", "demo.item.delete", "demo.item.stats"}

#: The requests of hub#1095's QA (``tests/e2e/qa/probes/*-es-demo-2026-11-08.json``), as each role said them, and
#: nothing of the tools' ``asks``: before Demo said its asks, the first four and the employee's count were offered no
#: tool of Demo (the model answered it could not read the item, chose a list of Sales or confused the Home's steps with
#: the app), and the three writes were offered without the read that finds «Ejemplo QA» by its name (the model asked
#: for its UUID).
REPORTED = [
    (OWNER, "demo.item.detail", "enséñame el elemento «Ejemplo QA» con su nota, su estado y todas sus líneas en orden"),
    (OWNER, "demo.item.list", "lista los elementos de ejemplo que contengan QA y sigan abiertos"),
    (OWNER, "demo.item.open_count", "¿cuántos elementos de demostración quedan sin cerrar?"),
    (OWNER, "demo.item.stats", "dame el recuento total de ejemplos, abiertos, terminados y líneas"),
    (
        OWNER,
        "demo.item.update",
        "cambia Ejemplo QA a «Ejemplo terminado QA», márcalo como hecho y actualiza su nota a «cerrado en QA»",
    ),
    (OWNER, "demo.item.delete", "elimina Ejemplo QA junto con todas sus líneas; entiendo que no se puede deshacer"),
    (
        OWNER,
        "demo.item.add_line",
        "añade al final de Ejemplo QA una línea «primera prueba» con cantidad 2 y referencia "
        "01a1c000-0000-7000-8000-000000000001",
    ),
    (EMPLOYEE, "demo.item.open_count", "¿cuántos ejemplos siguen abiertos ahora?"),
]
#: The read that finds an item by its name (``search``): every tool but the list and the counts takes the item's id, so
#: a request that names the item is offered the list beside its tool, never left to ask the person for the id.
BY_NAME = "demo.item.list"
NAMES_AN_ITEM = {"demo.item.detail", "demo.item.update", "demo.item.delete", "demo.item.add_line"}
#: A request that names its item by the item's own name alone («elimina Ejemplo QA…»), with no word that says it is
#: an item, is offered its tool but not the list: nothing in its words is Demo's, so only a write that takes the item by
#: its name too (as the Hub's catalogues do: a group, a tag, a drawer, a menu) acts on it from the chat (hub#1162).
BY_ITS_NAME_ALONE = pytest.mark.xfail(
    strict=True, reason="ERPlora/hub#1162: an item said by its own name alone names nothing of Demo's"
)

#: How far down the tools a turn offers (``MAX_TOOLS``, 40) a probe of the QA may bring its tool: half of them, so
#: twenty tools of the apps that say their asks later may climb past it before the model loses it.
WITH_ROOM = 20
#: How far down the tools a turn offers an ask brings its own tool in layer 1 (``base/tests/test_assistant_asks.py``).
TOP = 10
#: Every probe of layer 2 of Demo, both roles: the reported ones and the ones the model got right.
PROBES = [
    probe
    for path in sorted((Path(settings.BASE_DIR) / "tests" / "e2e" / "qa" / "probes").glob("*-es-demo-*.json"))
    for probe in json.loads(path.read_text(encoding="utf-8"))["probes"]
]
#: The probes a role is offered its tool for; the others (``"expect": "refused"``) ask for what the role may not do.
OFFERED_PROBES = [probe for probe in PROBES if probe["expect"] != "refused"]


@pytest.fixture
def catalog_of(make_user):
    """The real catalogue of the assistant of a person with ``role`` in business ``a``, in ``language``."""

    def of(role: str, language: str) -> dict[str, Operation]:
        user = make_user(f"asker-{role}", host=A.key, role=role)
        ctx = OperationContext(scope=A, actor=user.username, permissions=permissions_for(user, A), language=language)
        return assistant.catalog(ctx)

    return of


def offered_to(tools: dict[str, Operation], phrase: str) -> list[str]:
    return [op.name for op in assistant.relevant(tools, [phrase], "es")]


def place_in(tools: dict[str, Operation], name: str, phrase: str) -> int | None:
    """The place a turn offers ``name`` at for ``phrase`` (1 is first), ``None`` when it is not offered at all."""
    offered = offered_to(tools, phrase)
    return offered.index(name) + 1 if name in offered else None


def is_own_words(tools: dict[str, Operation], phrase: str) -> bool:
    """Whether ``phrase`` is neither an ask in Spanish of any tool of ``tools`` nor a probe of layer 2."""
    asks = {comparable(ask) for op in tools.values() for ask in shared.asks_of(op).get("es", ())}
    return comparable(phrase) not in asks | set(probe_phrases())


def without_its_asks(tools: dict[str, Operation], name: str) -> dict[str, Operation]:
    """``tools`` with ``name`` saying no asks: how a turn ranks it by its name and description alone."""
    op = tools[name]
    return {**tools, name: dataclasses.replace(op, ai={key: value for key, value in op.ai.items() if key != "asks"})}


def test_demo_offers_at_least_8_tools():
    """Demo's tools are at least 8 (``AI``, never ``INTERNAL``): a silent drop of tools fails."""
    tools = {name for name, op in registry.items() if op.app_label == "demo" and assistant.is_tool(op)}
    assert all(isinstance(registry[name].ai_spec(), AI) for name in tools)
    assert len(tools) >= 8


def test_the_reported_requests_are_the_probes_of_layer_2():
    phrases = probe_phrases()
    roles = {role: name for name, role in PROBE_ROLE.items()}
    assert [phrases.get(comparable(phrase)) for _, _, phrase in REPORTED] == [
        f"qa20261108.{roles[role]}.es.{name}" for role, name, _ in REPORTED
    ]


def test_the_probes_of_demo_are_read():
    """Positive control of the sweep below: both roles' files are read, and each probe is of Demo."""
    assert {probe["role"] for probe in PROBES} == set(PROBE_ROLE)
    assert len(OFFERED_PROBES) >= 11
    assert all(probe["app"] == "demo" and probe["language"] == "es" for probe in PROBES)


def test_the_hub_reads_an_elemento_as_an_item():
    """``base.assistant.SYNONYMS``: «el elemento», as Demo's screens name one, is the item its operations are of
    (``demo.item``), so the person's words reach those tools by their entity and not only by the words of their asks;
    without the Hub's group, it does not (positive control)."""
    item = shared.stem("item")
    for phrase in ("borra el elemento Ensayo 7", "¿qué elementos están hechos?"):
        assert any(item in concept for concept in shared.asked([phrase], assistant.SYNONYMS).concepts), phrase
        assert not any(item in concept for concept in shared.asked([phrase]).concepts), phrase


#: Phrases that are neither asks nor probes, each with the tool of Demo it asks for: the Hub's «elemento» brings it
#: among the first ten offered (``TOP`` of layer 1), and the write brings the read that finds its item by its name.
ELEMENTO = [
    ("demo.item.list", "¿qué elementos están hechos?"),
    ("demo.item.delete", "borra el elemento Ensayo 7"),
]


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), ELEMENTO)
def test_a_phrase_that_names_an_elemento_is_offered_its_tool_and_the_read_that_finds_it(catalog_of, name, phrase):
    tools = catalog_of(OWNER, "es")
    assert is_own_words(tools, phrase)
    offered = offered_to(tools, phrase)
    assert name in offered[:TOP], (offered.index(name) + 1 if name in offered else None, offered[:TOP])
    assert BY_NAME in offered[:TOP], (offered.index(BY_NAME) + 1 if BY_NAME in offered else None, offered[:TOP])


#: What a person says in words of their own, neither an ask nor a probe of layer 2, for the five tools whose probes a
#: turn offers by their verb and the «elemento» alone (the pattern of hub#1165): here it is their asks that bring the
#: tool among the first ten, so asks that stop reading as people speak fail.
OWN_WORDS = [
    ("demo.item.list", "busca los que lleven «otoño» en el nombre"),
    ("demo.item.create", "hazme «Ensayo de primavera» con la nota «llamar al técnico»"),
    ("demo.item.update", "el Ensayo de otoño ya está hecho"),
    ("demo.item.delete", "el Ensayo de otoño ya no sirve: que desaparezca para siempre"),
    ("demo.item.add_line", "al Ensayo de otoño le faltan cables nuevos, cuatro"),
]
@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), OWN_WORDS)
def test_a_request_in_the_persons_own_words_reaches_its_tool_by_its_asks(catalog_of, name, phrase):
    tools = catalog_of(OWNER, "es")
    assert name in tools  # positive control: the owner holds the tool, so its place is known
    assert is_own_words(tools, phrase)
    place = place_in(tools, name, phrase)
    assert place is not None and place <= TOP, place
    before = without_its_asks(tools, name)
    assert not shared.asks_of(before[name])  # positive control: the tool is ranked without its asks
    unasked = place_in(before, name, phrase)
    assert unasked is None or unasked > TOP, unasked


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
def test_an_employee_is_never_offered_what_only_who_manages_the_items_may_do(catalog_of):
    owner = catalog_of(OWNER, "es")
    employee = catalog_of(EMPLOYEE, "es")
    assert NOT_THE_EMPLOYEES <= set(owner)
    assert NOT_THE_EMPLOYEES.isdisjoint(employee)
    assert {"demo.item.list", "demo.item.detail", "demo.item.add_line"} <= set(employee)  # positive control
    # What the QA asked the employee for and expected refused is, every bit of it, what their catalogue lacks.
    refused = {probe["tool"] for probe in PROBES if probe["expect"] == "refused"}
    assert refused and refused <= NOT_THE_EMPLOYEES


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
@pytest.mark.parametrize(("role", "name", "phrase"), REPORTED)
def test_the_reported_demo_request_offers_its_existing_operation(catalog_of, role, name, phrase):
    tools = catalog_of(role, "es")
    assert name in tools  # positive control: the role holds the tool, so its place is known
    assert comparable(phrase) not in {comparable(ask) for ask in shared.asks_of(tools[name]).get("es", ())}
    offered = offered_to(tools, phrase)
    assert name in offered, (len(offered), offered[:10])


#: Every probe of layer 2 whose tool takes the item's id, as its role said it: the ones that say «elemento» are offered
#: the list that finds the item; the ones that name it by its own name alone wait for hub#1162.
NAMING_PROBES = [
    pytest.param(
        PROBE_ROLE[probe["role"]],
        probe["phrase"],
        id=probe["id"],
        marks=() if probe["id"] == "qa20261108.owner.es.demo.item.detail" else BY_ITS_NAME_ALONE,
    )
    for probe in OFFERED_PROBES
    if probe["tool"] in NAMES_AN_ITEM
]


def test_the_probes_that_name_an_item_are_the_four_tools_by_its_id_of_both_roles():
    """Positive control of the parametrization below: the owner's four and the employee's two (detail, a line)."""
    assert len(NAMING_PROBES) == 6
    assert sum(not case.marks for case in NAMING_PROBES) == 1


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
@pytest.mark.parametrize(("role", "phrase"), NAMING_PROBES)
def test_a_probe_that_names_an_item_is_offered_the_read_that_finds_it(catalog_of, role, phrase):
    tools = catalog_of(role, "es")
    assert BY_NAME in tools  # positive control: the role holds the list
    offered = offered_to(tools, phrase)
    assert BY_NAME in offered, (len(offered), offered[:10])


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
@pytest.mark.parametrize("probe", OFFERED_PROBES, ids=[probe["id"] for probe in OFFERED_PROBES])
def test_every_probe_of_demo_offers_its_tool_without_being_one_of_its_asks(catalog_of, probe):
    """Both roles' phrases of layer 2, the ones the model answered right too: a tool of Demo that a new ask elsewhere
    pushes out of the first half of the ones a turn offers fails here before the real-model QA sees it."""
    tools = catalog_of(PROBE_ROLE[probe["role"]], probe["language"])
    name, phrase = probe["tool"], probe["phrase"]
    assert name in tools  # positive control: the role holds the tool, so its place is known
    assert comparable(phrase) not in {comparable(ask) for ask in shared.asks_of(tools[name]).get("es", ())}
    offered = offered_to(tools, phrase)
    assert name in offered[:WITH_ROOM], (offered.index(name) + 1 if name in offered else None, offered[:10])
