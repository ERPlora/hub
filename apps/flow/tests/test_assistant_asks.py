"""What layer 1 of the assistant's QA says of Automations (erplora-next docs/plans/2026-10-31-asistente-conocimiento-y-qa.md):
which tools it offers, to whom, and the requests the real-model QA found unreachable (hub#1106).

Every ask of every tool of flow bringing its tool among the first ten, role by role, in English and in Spanish, out of
the catalogue of a business with every app on and ranked as a turn ranks, is ``base/tests/test_assistant_asks.py``'s
(flow is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020`` over its asks.
"""

import json
import re
import unicodedata
from pathlib import Path

import pytest
from django.conf import settings
from live import assistant as shared
from live.context import OperationContext, Scope
from live.operations import AI, Operation, registry

from base import assistant
from base.models import Membership
from base.permissions import permissions_for

A = Scope("host", "a")
#: The questions an automation asks a person (FLOW-F29): every role may be asked one, so every role holds these.
THE_QUESTIONS = {"flow.question.list", "flow.question.get", "flow.question.answer"}
#: Automations' assistant tools: its catalogue, its automations, their runs, the ready-made recipes, the assistant's
#: drafts, the secrets' names and the questions; the engine's and the platform's operations are none of them.
TOOLS = THE_QUESTIONS | {
    "flow.catalog.read",
    "flow.event.sample",
    "flow.flow.list",
    "flow.flow.detail",
    "flow.flow.status",
    "flow.flow.test",
    "flow.flow.create",
    "flow.flow.update",
    "flow.flow.set_enabled",
    "flow.flow.duplicate",
    "flow.flow.delete",
    "flow.flow.grant",
    "flow.flow.run",
    "flow.run.list",
    "flow.run.get",
    "flow.run.retry",
    "flow.recipe.list",
    "flow.recipe.enable",
    "flow.recipe.disable",
    "flow.recipe.restore",
    "flow.recipe.repair",
    "flow.draft.list",
    "flow.draft.get",
    "flow.draft.propose",
    "flow.draft.dismiss",
    "flow.secret.list",
    "flow.secret.delete",
}
#: The probes of layer 2 (``tests/e2e/qa/assistant-probes.spec.ts``) that hub#1106's QA ran on Automations.
PROBES = Path(settings.BASE_DIR) / "tests" / "e2e" / "qa" / "probes"


@pytest.fixture
def catalog_of(make_user):
    """The real catalogue of the assistant of a person with ``role`` in business ``a``, in ``language``."""

    def of(role: str, language: str) -> dict[str, Operation]:
        user = make_user(f"asker-{role}", host=A.key, role=role)
        ctx = OperationContext(scope=A, actor=user.username, permissions=permissions_for(user, A), language=language)
        return assistant.catalog(ctx)

    return of


def test_automations_offers_its_thirty_tools():
    """Automations' assistant tools (``AI``, never ``INTERNAL`` nor the engine's «System only»): a silent drop fails."""
    tools = {
        name
        for name, op in registry.items()
        if op.app_label == "flow" and isinstance(op.ai_spec(), AI) and assistant.is_tool(op)
    }
    assert tools == TOOLS


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
def test_only_who_runs_the_business_is_offered_the_automations(catalog_of):
    """An automation acts in the business's name with nobody watching (``FlowConfig.role_permissions``): the owner and
    the admin hold every tool; a manager and an employee only the questions an automation asks them."""
    for role in (Membership.Role.OWNER, Membership.Role.ADMIN):
        assert {name for name in catalog_of(role, "es") if name.startswith("flow.")} == TOOLS
    for role in (Membership.Role.MANAGER, Membership.Role.EMPLOYEE):
        assert {name for name in catalog_of(role, "es") if name.startswith("flow.")} == THE_QUESTIONS


#: The requests of hub#1106's QA as the owner said them (``tests/e2e/qa/probes/owner-es-flow-2026-11-08.json``), and
#: nothing of the tools' ``asks``: before Automations said its asks, twelve of them were not among the tools a turn
#: offers (``MAX_TOOLS``), creating one from the draft came 9th and pausing a recipe 34th, so the model answered it had
#: no tool, sent the person to the screen or reached for the till's checks. Their words stay the person's, never the asks'
#: (``test_no_ask_copies_a_qa_probe_or_names_a_qa_record``).
REPORTED = [
    (
        "flow.draft.get",
        "abre el borrador que propuse para crear un ejemplo al cobrar y dime qué pasos y dudas tiene",
    ),
    (
        "flow.flow.detail",
        "detalla la automatización Crear ejemplo QA al cobrar: disparador, pasos, permisos y última ejecución",
    ),
    ("flow.run.get", "abre la última ejecución de Crear ejemplo QA al cobrar, con cada paso y cualquier error"),
    ("flow.run.list", "enseñame el historial de ejecuciones de Crear ejemplo QA al cobrar y cuántas fallaron"),
    (
        "flow.flow.create",
        "crea desde ese borrador la automatización Crear ejemplo QA al cobrar, pausada y sin permisos todavía",
    ),
    ("flow.flow.grant", "permite a Crear ejemplo QA al cobrar leer la venta y crear elementos de Demo, nada más"),
    ("flow.flow.set_enabled", "activa Crear ejemplo QA al cobrar ya que tiene los permisos mínimos"),
    ("flow.flow.run", "ejecuta ahora Crear ejemplo QA al cobrar sin datos de entrada"),
    (
        "flow.draft.dismiss",
        "descarta el borrador que no llegué a convertir en automatización, conservando su registro",
    ),
    (
        "flow.flow.update",
        "renombra Crear ejemplo QA al cobrar como «Crear ejemplo diario QA», sin tocar pasos ni permisos",
    ),
    ("flow.recipe.disable", "pausa la primera receta activa sin borrar sus permisos ni historial"),
    # The QA blamed the data for these three (no sale to read, nothing set up yet), but no turn offered their tool
    # either: the last real event, whether one is set up, and the try without effects.
    ("flow.event.sample", "muéstrame la última venta cobrada real con los datos que una automatización recibiría"),
    (
        "flow.flow.status",
        "cuántas automatizaciones escuchan una venta cobrada y cuántas pueden crear elementos de Demo, estén activas o "
        "no",
    ),
    (
        "flow.flow.test",
        "prueba Crear ejemplo QA al cobrar sin ejecutar nada y dime qué haría paso a paso con la última venta",
    ),
]


def test_the_hub_reads_an_automation_its_runs_steps_and_questions():
    """``base.assistant.SYNONYMS``: «la automatización» (or «el flujo») is a ``flow.flow``, «la ejecución» and what
    «ejecuta» a run (``flow.run``, ``flow.flow.run``), «los pasos» its steps and «la pregunta» the one an automation
    waits on: a request in the words of the Automations screens reaches those tools without their own asks."""
    concepts = shared.asked(["ejecuta la automatización y dime sus pasos y la pregunta"], assistant.SYNONYMS).concepts
    for word in ("flow", "run", "step", "question"):
        assert any(shared.stem(word) in concept for concept in concepts), word
    bare = shared.asked(["ejecuta la automatización y dime sus pasos y la pregunta"]).concepts
    assert not any(shared.stem("run") in concept for concept in bare)  # positive control: live alone reads none


def comparable(text: str) -> str:
    """``text`` as layer 2 compares a probe with the asks: lower case, without accents, punctuation or extra spaces."""
    bare = "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^\w]+|_", " ", bare).split())


def test_the_reported_requests_are_the_owners_probes_of_layer_2():
    """Each phrase above is word for word the owner's probe of its tool: the test measures what layer 2 measures."""
    probes = {
        comparable(probe["phrase"]): probe["id"]
        for path in sorted(PROBES.glob("*-es-flow-*.json"))
        for probe in json.loads(path.read_text(encoding="utf-8"))["probes"]
    }
    assert len(probes) >= len(REPORTED)  # positive control: the probes of Automations are read
    assert [probes.get(comparable(phrase)) for _, phrase in REPORTED] == [f"owner.es.{name}" for name, _ in REPORTED]


#: The read a reported request needs offered beside its tool, as the QA found: a tool that takes only an id (the draft's,
#: the run's, the recipe's key, the saved automation's with its document) is of no use without the read that finds it
#: by what the person said, and the model asked for the id instead («pide el id del borrador», «pide su app/id»).
FINDS = {
    "flow.draft.get": "flow.draft.list",
    "flow.run.get": "flow.run.list",
    "flow.flow.create": "flow.draft.list",
    "flow.draft.dismiss": "flow.draft.list",
    "flow.recipe.disable": "flow.recipe.list",
    "flow.flow.test": "flow.flow.detail",
}


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), REPORTED)
def test_the_reported_automations_request_is_offered_its_tool_without_being_its_asks(catalog_of, name, phrase):
    tools = catalog_of(Membership.Role.OWNER, language := "es")
    assert name in tools  # positive control: the owner holds it, so the model can receive it
    assert comparable(phrase) not in {comparable(ask) for ask in shared.asks_of(tools[name]).get(language, ())}
    offered = [op.name for op in assistant.relevant(tools, [phrase], language)]
    assert name in offered, offered
    assert FINDS.get(name, name) in offered, offered


def test_each_read_that_finds_a_record_is_a_tool_that_finds_it():
    """``FINDS`` pairs reported tools with reads of Automations (positive control: the pairs are real)."""
    assert set(FINDS) <= {name for name, _ in REPORTED}
    assert set(FINDS.values()) <= TOOLS
    assert all(registry[read].kind == "query" for read in FINDS.values())
