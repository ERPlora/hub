"""What layer 1 of the assistant's QA does not say of Tasks (docs plan 2026-10-31, the assistant's knowledge and QA,
§3): how many tools it offers, what an employee is never offered, and that the owner's requests of the real-model QA
(hub#1098), in the owner's own words, are offered their existing operation.

Every ask of every tool of task bringing its tool among the first ten, role by role, in both languages, is
``base/tests/test_assistant_asks.py``'s (task is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020`` over the
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
#: Writes on what the whole team shares that only who runs it holds (``task.delete``, ``task.manage_project``), none
#: of them a manager approves: an employee's assistant is never offered them.
NOT_THE_EMPLOYEES = {
    "task.task.delete",
    "task.project.create",
    "task.project.update",
    "task.project.delete",
}

#: The requests of hub#1098's QA (``tests/e2e/qa/probes/owner-es-task-2026-11-08.json``) as the owner said them, and
#: nothing of the tools' ``asks``: before Tasks said its asks, none of these tools was among the ones a turn offers
#: (``MAX_TOOLS``), so the model answered it had no tool, sent the owner to the screen or chose a tool of Customers.
REPORTED = [
    ("task.comment.add", "comenta en Revisar almacén QA: «Pendiente de llamar al proveedor QA»"),
    ("task.project.update", "renombra Operaciones QA como «Operaciones diarias QA» y cámbialo a verde"),
    ("task.task.complete", "marca Revisar almacén QA como terminada"),
    ("task.task.set_status", "pon Revisar almacén QA en curso porque ya he empezado"),
]

#: Every probe of layer 2 of Tasks, the owner's real phrases of the QA: the four above and the ones the model got right.
PROBES = json.loads(
    (Path(settings.BASE_DIR) / "tests" / "e2e" / "qa" / "probes" / "owner-es-task-2026-11-08.json").read_text(
        encoding="utf-8"
    )
)["probes"]


@pytest.fixture
def catalog_of(make_user):
    """The real catalogue of the assistant of a person with ``role`` in business ``a``, in ``language``."""

    def of(role: str, language: str) -> dict[str, Operation]:
        user = make_user(f"asker-{role}", host=A.key, role=role)
        ctx = OperationContext(scope=A, actor=user.username, permissions=permissions_for(user, A), language=language)
        return assistant.catalog(ctx)

    return of


def test_task_offers_at_least_17_tools():
    """Tasks' tools are at least 17 (``AI``, never ``INTERNAL``): a silent drop of tools fails."""
    tools = {name for name, op in registry.items() if op.app_label == "task" and assistant.is_tool(op)}
    assert all(isinstance(registry[name].ai_spec(), AI) for name in tools)
    assert len(tools) >= 17


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
def test_an_employee_is_never_offered_what_only_who_runs_the_team_may_do(catalog_of):
    owner = catalog_of(Membership.Role.OWNER, "es")
    employee = catalog_of(Membership.Role.EMPLOYEE, "es")
    assert NOT_THE_EMPLOYEES <= set(owner)
    assert NOT_THE_EMPLOYEES.isdisjoint(employee)
    assert "task.comment.add" in employee  # positive control: an employee comments their own tasks


def test_the_reported_requests_are_the_probes_of_layer_2():
    phrases = probe_phrases()
    assert [phrases.get(comparable(phrase)) for _, phrase in REPORTED] == [
        f"owner.es.{name}" for name, _ in REPORTED
    ]


def test_the_hub_reads_a_tarea_as_a_task_a_proyecto_as_a_project_and_a_comentario_as_a_comment():
    """``base.assistant.SYNONYMS``: «la tarea», «el proyecto» and «comenta» name what Tasks' operations are of
    (``task.task``, ``task.project``, ``task.comment``), so the owner's words reach those tools by their entity and not
    only by the words of their asks; without the Hub's groups, none of them does (positive control)."""
    for phrase, wanted in (
        ("borra la tarea de colgar el cartel", "task"),
        ("¿qué proyectos tenemos?", "project"),
        ("comenta que el técnico viene el lunes", "comment"),
    ):
        concepts = shared.asked([phrase], assistant.SYNONYMS).concepts
        assert any(shared.stem(wanted) in concept for concept in concepts), phrase
        assert not any(shared.stem(wanted) in concept for concept in shared.asked([phrase]).concepts), phrase


def test_the_guests_of_a_table_are_no_comment():
    """«comentario» shares its stem «comen» with «comensales» (a table's guests) until ERPlora/live#48: the Hub names a
    comment by the phrases a person says it with, never by that stem, so a question about the guests names no
    comment and offers no tool of Tasks' comments ahead of Tables'."""
    comment = shared.stem("comment")
    assert not any(
        comment in concept
        for concept in shared.asked(["¿cuántos comensales tiene la cuenta de la mesa 4?"], assistant.SYNONYMS).concepts
    )


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), REPORTED)
def test_the_reported_task_request_offers_its_existing_operation(catalog_of, name, phrase):
    tools = catalog_of(Membership.Role.OWNER, "es")
    assert name in tools  # positive control: the owner holds the tool, so its place is known
    assert comparable(phrase) not in {comparable(ask) for ask in shared.asks_of(tools[name]).get("es", ())}
    offered = [op.name for op in assistant.relevant(tools, [phrase], "es")]
    assert name in offered, (len(offered), offered[:10])


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize("probe", PROBES, ids=[probe["id"] for probe in PROBES])
def test_every_probe_of_tasks_offers_its_tool_without_being_one_of_its_asks(catalog_of, probe):
    """The owner's seventeen phrases of layer 2, the ones the model answered right too: a tool of Tasks that a new ask
    elsewhere pushes out of the ones a turn offers fails here before the real-model QA sees it."""
    assert (probe["app"], probe["role"], probe["language"]) == ("task", "owner", "es")
    tools = catalog_of(Membership.Role.OWNER, probe["language"])
    name, phrase = probe["tool"], probe["phrase"]
    assert name in tools  # positive control: the owner holds the tool, so its place is known
    assert comparable(phrase) not in {comparable(ask) for ask in shared.asks_of(tools[name]).get("es", ())}
    offered = [op.name for op in assistant.relevant(tools, [phrase], "es")]
    assert name in offered, (offered.index(name) + 1 if name in offered else None, len(offered), offered[:10])
