"""What layer 1 of the assistant's QA does not say of Modifiers (docs plan 2026-10-31, the assistant's knowledge and QA,
§3): how many tools it offers, what an employee is never offered, and that the requests of the real-model QA (hub#1092),
in the person's own words, are offered their existing operation.

Every ask of every tool of Modifiers bringing its tool among the first ten, role by role, in both languages, is
``base/tests/test_assistant_asks.py``'s (Modifiers is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020`` over
the asks and the guard that no ask copies a probe of layer 2. What it cannot see is whether the asks matter at all (an ask
ranks its own words): here, one request per tool in words of its own reaches the tool by its asks and not without them.
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
OWNER, ADMIN, MANAGER, EMPLOYEE = (
    Membership.Role.OWNER,
    Membership.Role.ADMIN,
    Membership.Role.MANAGER,
    Membership.Role.EMPLOYEE,
)
#: A probe names its role as layer 2 does («owner»); a membership, with the prefix the SaaS sends («hub_owner»).
ROLE_OF_PROBE = {"owner": OWNER, "employee": EMPLOYEE}
#: The writes on the groups, their options and where they apply (``modifier.manage``): an employee reads the groups of a
#: product and has their picks valued (``modifier.view``), and is never offered these.
NOT_THE_EMPLOYEES = {
    "modifier.group.create",
    "modifier.group.update",
    "modifier.group.delete",
    "modifier.option.create",
    "modifier.option.update",
    "modifier.option.delete",
    "modifier.link.attach",
    "modifier.link.detach",
}

#: The requests of hub#1092's QA (``tests/e2e/qa/probes/*-es-modifier-2026-11-08.json``) as the person said them, with
#: the role that said each, and nothing of the tools' ``asks``: before Modifiers said its asks, none of these tools was
#: among the ones a turn offers (``MAX_TOOLS``), so the model looked in Inventory, sent the owner to the screen, chose a
#: tool of Customers or told the employee it could not value a dish with its option.
REPORTED = [
    (OWNER, "modifier.group.for_target", "¿qué extras tendré que preguntar al vender un Café, tanto los suyos como los de su familia?"),
    (OWNER, "modifier.link.get", "muéstrame la asignación concreta entre Endulzante QA y el Café"),
    (OWNER, "modifier.option.list", "lista las opciones de Endulzante QA, su precio adicional y cuál viene marcada por defecto"),
    (OWNER, "modifier.link.attach", "haz que el TPV pregunte Endulzante QA siempre que se venda un Café"),
    (OWNER, "modifier.group.delete", "elimina Endulzante QA con su opción y sus asignaciones, sin cambiar los pedidos antiguos"),
    (OWNER, "modifier.group.update", "convierte Endulzante QA en obligatorio y permite elegir hasta dos opciones"),
    (OWNER, "modifier.link.detach", "deja de solicitar Endulzante QA al vender Café, pero conserva el grupo para otros productos"),
    (OWNER, "modifier.option.update", "renombra Sin azúcar QA como «Sin azúcar ni edulcorante QA» y quítala como opción predeterminada"),
    (EMPLOYEE, "modifier.selection.resolve", "¿cuánto cuesta un Café con Sin azúcar QA y qué nota manda a cocina?"),
]
#: «sin cambiar los pedidos antiguos» is read as asking to change them (``live.assistant.asked``): every write of an order,
#: and every one taking a sort order, outranks the deletion asked for, whatever its asks say. Strict: once live reads the
#: negation the probe passes, and whoever brings that pointer removes the mark.
LIVE_60 = pytest.mark.xfail(
    strict=True, reason="ERPlora/live#60: «sin cambiar …» is read as asking to change, so the deletion is not offered"
)
BLOCKED_BY_LIVE_60 = {"qa20261108.owner.es.modifier.group.delete"}

#: How far down the tools a turn offers (``MAX_TOOLS``, 40) a request of the QA may bring its tool: half of them, so
#: twenty tools of the apps that say their asks later may climb past it before the model loses it.
WITH_ROOM = 20
#: Every probe of layer 2 of Modifiers, the owner's and the employee's real phrases: the ones above and the ones the
#: model got right, or refused right (an employee asking for a write it does not hold).
PROBES = [
    probe
    for path in sorted((Path(settings.BASE_DIR) / "tests" / "e2e" / "qa" / "probes").glob("*-es-modifier-*.json"))
    for probe in json.loads(path.read_text(encoding="utf-8"))["probes"]
]

#: What a person says in words of their own, neither an ask nor a probe of layer 2 nor an ask of its tool but for a word,
#: one per tool of Modifiers: here it is the tool's asks that bring it among the first ten, so asks that stop reading as
#: people speak, or that another change empties, fail.
OWN_WORDS = [
    ("modifier.group.list", "¿qué tengo montado para acompañar los platos?"),
    ("modifier.group.get", "¿cuál es el máximo de Punto de la carne?"),
    ("modifier.category.get", "Pizzas, ¿cuál es para colgarle suplementos?"),
    ("modifier.option.list", "¿qué opciones de salsa tengo y qué cuestan?"),
    ("modifier.option.get", "¿cuánto se suma por la opción Sin gluten?"),
    ("modifier.link.list", "dime los platos que llevan Extras"),
    ("modifier.link.get", "¿Extras está puesto en las patatas bravas?"),
    ("modifier.group.for_target", "¿qué me pregunta el TPV si marco un bocadillo de lomo?"),
    ("modifier.selection.resolve", "si le pongo doble de queso a la pizza, ¿cuánto sube?"),
    ("modifier.group.create", "monta un grupo para el punto de la carne"),
    ("modifier.group.update", "Salsas ya no es opcional, cámbialo"),
    ("modifier.group.delete", "Punto de la carne sobra, bórralo con sus opciones"),
    ("modifier.option.create", "en Extras falta el doble de bacon, añádelo a un euro"),
    ("modifier.option.update", "el extra de queso ahora cuesta un euro y medio, cámbialo"),
    ("modifier.option.delete", "el alioli ya no lo tenemos, quítalo de las salsas"),
    ("modifier.link.attach", "que con el entrecot salga siempre la pregunta del punto"),
    ("modifier.link.detach", "con la pizza ya no hace falta preguntar la salsa"),
]

#: A request with «predeterminada» that is no ask nor probe: the option a group brings chosen is its default
#: (``is_default``), as the descriptions say in English; without the Hub reading the word so, it is no tool's datum.
BY_DEFAULT = "la salsa de la casa ya no tiene que salir como predeterminada"
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


def offered_place(tools: dict[str, Operation], name: str, phrase: str, synonyms=assistant.SYNONYMS) -> int | None:
    """The place a turn in Spanish offers ``name`` at for ``phrase`` (1 is first), ``None`` when it is not offered; with
    the Hub's ``synonyms`` unless others are given."""
    ranking = {**assistant.RANKING, "synonyms": synonyms}
    offered = [op.name for op in shared.relevant(tools, [phrase], "es", **ranking)]
    return offered.index(name) + 1 if name in offered else None


def place_of_no_ask(tools: dict[str, Operation], name: str, phrase: str) -> int | None:
    """``offered_place`` of a tool the person holds for a ``phrase`` that is none of its asks in Spanish."""
    assert name in tools  # positive control: the person holds the tool, so its place is known
    assert comparable(phrase) not in {comparable(ask) for ask in shared.asks_of(tools[name]).get("es", ())}
    return offered_place(tools, name, phrase)


def without_its_asks(tools: dict[str, Operation], name: str) -> dict[str, Operation]:
    """``tools`` with ``name`` saying no asks: how a turn ranks it by its name and description alone."""
    op = tools[name]
    return {**tools, name: dataclasses.replace(op, ai={key: value for key, value in op.ai.items() if key != "asks"})}


def test_modifiers_is_listed_so_layer_1_sweeps_every_ask_of_it():
    """Modifiers is in ``LIVE_ASSISTANT_ASKS_REQUIRED``: ``base/tests/test_assistant_asks.py`` ranks each of its asks for
    every role and language, and ``live.E020`` requires them of each of its tools."""
    assert "modifier" in settings.LIVE_ASSISTANT_ASKS_REQUIRED


def test_modifier_offers_its_seventeen_tools():
    """Modifiers' tools are its seventeen operations (``AI``, never ``INTERNAL``), the two reactions to a deletion in
    Inventory aside (``SYSTEM``: no role holds them): a silent drop of a tool fails, and each has its own words."""
    tools = {name for name, op in registry.items() if op.app_label == "modifier" and assistant.is_tool(op)}
    assert all(isinstance(registry[name].ai_spec(), AI) for name in tools)
    assert len(tools) == 17
    assert sorted(name for name, _ in OWN_WORDS) == sorted(tools)


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
def test_an_employee_is_never_offered_what_only_who_runs_the_menu_may_do(catalog_of):
    owner = catalog_of(OWNER, "es")
    employee = catalog_of(EMPLOYEE, "es")
    assert NOT_THE_EMPLOYEES <= set(owner)
    assert NOT_THE_EMPLOYEES.isdisjoint(employee), sorted(NOT_THE_EMPLOYEES & set(employee))
    assert "modifier.selection.resolve" in employee  # positive control: an employee values the picks of a dish


def test_the_reported_requests_are_the_probes_of_layer_2():
    phrases = probe_phrases()
    probe_role = {role: said for said, role in ROLE_OF_PROBE.items()}
    assert [phrases.get(comparable(phrase)) for _, _, phrase in REPORTED] == [
        f"qa20261108.{probe_role[role]}.es.{name}" for role, name, _ in REPORTED
    ]


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(
    ("role", "name", "phrase"),
    [
        pytest.param(role, name, phrase, marks=LIVE_60) if f"qa20261108.owner.es.{name}" in BLOCKED_BY_LIVE_60
        else pytest.param(role, name, phrase)
        for role, name, phrase in REPORTED
    ],
    ids=[f"{role}-{name}" for role, name, _ in REPORTED],
)
def test_the_reported_modifier_request_offers_its_existing_operation(catalog_of, role, name, phrase):
    tools = catalog_of(role, "es")
    place = place_of_no_ask(tools, name, phrase)
    assert place is not None and place <= WITH_ROOM, place


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(
    "probe",
    [pytest.param(probe, marks=LIVE_60 if probe["id"] in BLOCKED_BY_LIVE_60 else ()) for probe in PROBES],
    ids=[probe["id"] for probe in PROBES],
)
def test_every_probe_of_modifiers_offers_its_tool_without_being_one_of_its_asks(catalog_of, probe):
    """The owner's and the employee's phrases of layer 2, the ones the model answered right too: a tool of Modifiers that
    a new ask elsewhere pushes out of the first half of the ones a turn offers fails here before the real-model QA sees
    it. A write an employee asks for is refused by not being theirs at all (``NOT_THE_EMPLOYEES``), never by ranking."""
    assert (probe["app"], probe["language"]) == ("modifier", "es")
    role = ROLE_OF_PROBE[probe["role"]]
    tools = catalog_of(role, probe["language"])
    name, phrase = probe["tool"], probe["phrase"]
    if role == EMPLOYEE and name in NOT_THE_EMPLOYEES:
        assert name not in tools
        return
    place = place_of_no_ask(tools, name, phrase)
    assert place is not None and place <= WITH_ROOM, place


def test_the_probes_of_modifiers_are_read():
    """Positive control of the parametrisation above: both roles' files are read, every probe of the two."""
    assert {ROLE_OF_PROBE[probe["role"]] for probe in PROBES} == {OWNER, EMPLOYEE}
    assert len(PROBES) == 23  # the owner's seventeen, one per tool, and six of the employee's
    assert BLOCKED_BY_LIVE_60 <= {probe["id"] for probe in PROBES}


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), OWN_WORDS)
def test_a_request_in_the_persons_own_words_reaches_its_tool_by_its_asks(catalog_of, name, phrase):
    tools = catalog_of(OWNER, "es")
    assert comparable(phrase) not in probe_phrases()
    place = place_of_no_ask(tools, name, phrase)
    assert place is not None and place <= TOP, place
    before = without_its_asks(tools, name)
    assert not shared.asks_of(before[name])  # positive control: the tool is ranked without its asks
    unasked = offered_place(before, name, phrase)
    assert unasked is None or unasked > TOP, unasked


def test_the_hub_reads_predeterminada_as_the_default():
    """A «predeterminada» option is the one a group brings chosen (``is_default``): the Hub reads the word as the default
    the English descriptions and the option's data say."""
    said = shared.asked(["quítala como opción predeterminada"], assistant.SYNONYMS).concepts
    assert any({shared.stem("predeterminada"), shared.stem("default")} <= concept for concept in said)


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
def test_a_request_with_predeterminada_reaches_the_change_of_an_option_by_the_hubs_synonyms(catalog_of):
    tools = catalog_of(OWNER, "es")
    assert comparable(BY_DEFAULT) not in probe_phrases()
    place = place_of_no_ask(tools, "modifier.option.update", BY_DEFAULT)
    assert place is not None and place <= TOP, place
    without = tuple(group for group in assistant.SYNONYMS if "predeterminada" not in group)
    assert len(without) == len(assistant.SYNONYMS) - 1  # positive control: one group is left out, the default's
    unread = offered_place(tools, "modifier.option.update", BY_DEFAULT, synonyms=without)
    assert unread is None or unread > TOP, unread


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
@pytest.mark.parametrize("role", [OWNER, ADMIN, MANAGER])
def test_renaming_a_category_of_inventory_takes_no_place_from_the_category_modifiers_look_up(catalog_of, role):
    """``modifier.category.get`` names a category of Inventory, so its asks say «familia» and «category»: Inventory's
    asks to change a category keep their room below the first ten (``inventory.category.update`` fell from the 7th to
    the 8th when Modifiers said its asks)."""
    tools = catalog_of(role, "es")
    asks = shared.asks_of(tools["inventory.category.update"])["es"]
    places = {ask: offered_place(tools, "inventory.category.update", ask) for ask in asks}
    assert {ask: place for ask, place in places.items() if place is None or place > TOP - ROOM} == {}
