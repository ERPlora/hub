"""What layer 1 of the assistant's QA does not say of Demo (docs plan 2026-10-31, the assistant's knowledge and QA, §3):
how many tools it offers, what an employee is never offered, and that the requests of the real-model QA (hub#1095), in
the words each role said them, are offered their existing operation, and with it the read that finds the item by its
name.

Every ask of every tool of demo bringing its tool among the first ten, role by role, in both languages, is
``base/tests/test_assistant_asks.py``'s (demo is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020`` over the
asks and the guard that no ask copies a probe of layer 2.
"""

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
#: The read that finds an item by its name (``search``): every tool but the list and the counts takes the item's id, so a
#: request that names the item is offered the list beside its tool, never left to ask the person for the id.
BY_NAME = "demo.item.list"
NAMES_AN_ITEM = {"demo.item.detail", "demo.item.update", "demo.item.delete", "demo.item.add_line"}

#: How far down the tools a turn offers (``MAX_TOOLS``, 40) a probe of the QA may bring its tool: half of them, so twenty
#: tools of the apps that say their asks later may climb past it before the model loses it.
WITH_ROOM = 20
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


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
@pytest.mark.parametrize(("role", "name", "phrase"), [case for case in REPORTED if case[1] in NAMES_AN_ITEM])
def test_the_reported_request_that_names_an_item_is_offered_the_read_that_finds_it(catalog_of, role, name, phrase):
    tools = catalog_of(role, "es")
    assert BY_NAME in tools  # positive control: the role holds the list
    offered = offered_to(tools, phrase)
    assert BY_NAME in offered, (len(offered), offered[:10])


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
@pytest.mark.parametrize("probe", OFFERED_PROBES, ids=[probe["id"] for probe in OFFERED_PROBES])
def test_every_probe_of_demo_offers_its_tool_without_being_one_of_its_asks(catalog_of, probe):
    """Both roles' phrases of layer 2, the ones the model answered right too: a tool of Demo that a new ask elsewhere
    pushes out of the first half of the ones a turn offers fails here before the real-model QA sees it; a probe that
    names an item («Ejemplo QA») is offered the list that finds it too."""
    tools = catalog_of(PROBE_ROLE[probe["role"]], probe["language"])
    name, phrase = probe["tool"], probe["phrase"]
    assert name in tools  # positive control: the role holds the tool, so its place is known
    assert comparable(phrase) not in {comparable(ask) for ask in shared.asks_of(tools[name]).get("es", ())}
    offered = offered_to(tools, phrase)
    assert name in offered[:WITH_ROOM], (offered.index(name) + 1 if name in offered else None, offered[:10])
    if name in NAMES_AN_ITEM:
        assert BY_NAME in offered, (len(offered), offered[:10])
