"""What layer 1 of the assistant's QA does not say of Automations (docs plan 2026-10-31, the assistant's knowledge and QA,
§3): which tools it offers and to whom, the words of the Hub that name its records, and that the owner's requests of the
real-model QA (hub#1106), in the owner's own words, are offered their existing operation.

Every ask of every tool of flow bringing its tool among the first ten, role by role, in both languages, is
``base/tests/test_assistant_asks.py``'s (flow is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020`` over the
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
#: The questions an automation asks a person (FLOW-F29): every role may be asked one, so every role holds these.
THE_QUESTIONS = {"flow.question.list", "flow.question.get", "flow.question.answer"}
#: Automations' assistant tools: its catalogue, its automations, their runs, the ready-made ones its apps bring, the
#: assistant's drafts, the secrets' names and the questions; the engine's and the platform's operations are none of them.
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
#: live weighs the action asked only when the tool's name spells it, and knows no verb of granting: «activa» is
#: ``enable``, never the ``enabled`` of ``set_enabled``; «renombra» is ``rename``, never an ``update`` that takes the
#: name; «permite a…» asks for nothing. Named by its own name and not as «la automatización», none of the three comes
#: among the tools a turn offers, whatever its asks say short of copying the probe.
LIVE_53 = pytest.mark.xfail(strict=True, reason="ERPlora/live#53: no enable/rename/grant weight for set_enabled/update/grant")
AWAITS_LIVE = {"flow.flow.set_enabled", "flow.flow.update", "flow.flow.grant"}

#: The requests of hub#1106's QA as the owner said them (``tests/e2e/qa/probes/owner-es-flow-2026-11-08.json``), and
#: nothing of the tools' ``asks``: before Automations said its asks, none of these tools was among the ones a turn offers
#: (``MAX_TOOLS``) but creating one from the draft (9th) and pausing a recipe (34th), so the model answered it had no
#: tool, sent the person to the screen or reached for the till's checks.
REPORTED = [
    ("flow.draft.get", "abre el borrador que propuse para crear un ejemplo al cobrar y dime qué pasos y dudas tiene"),
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
    pytest.param(
        "flow.flow.grant",
        "permite a Crear ejemplo QA al cobrar leer la venta y crear elementos de Demo, nada más",
        marks=LIVE_53,
    ),
    pytest.param(
        "flow.flow.set_enabled", "activa Crear ejemplo QA al cobrar ya que tiene los permisos mínimos", marks=LIVE_53
    ),
    ("flow.flow.run", "ejecuta ahora Crear ejemplo QA al cobrar sin datos de entrada"),
    ("flow.draft.dismiss", "descarta el borrador que no llegué a convertir en automatización, conservando su registro"),
    pytest.param(
        "flow.flow.update",
        "renombra Crear ejemplo QA al cobrar como «Crear ejemplo diario QA», sin tocar pasos ni permisos",
        marks=LIVE_53,
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
#: The read a reported request needs offered beside its tool, as the QA found: a tool that takes only an id (the draft's,
#: the run's, the recipe's key, the saved automation's) is of no use without the read that finds it by what the person
#: said, and the model asked for the id instead («pide el id del borrador», «pide su app/id»).
FINDS = {
    "flow.draft.get": "flow.draft.list",
    "flow.run.get": "flow.run.list",
    "flow.flow.create": "flow.draft.list",
    "flow.draft.dismiss": "flow.draft.list",
    "flow.recipe.disable": "flow.recipe.list",
    "flow.flow.test": "flow.flow.detail",
}
#: Every probe of layer 2 of Automations, the owner's real phrases of the QA: the reported ones and the ones the model
#: got right.
PROBES = json.loads(
    (Path(settings.BASE_DIR) / "tests" / "e2e" / "qa" / "probes" / "owner-es-flow-2026-11-08.json").read_text(
        encoding="utf-8"
    )
)["probes"]
#: The Hub's groups of words of Automations (``base.assistant.SYNONYMS``), each by a word of its own, and a request that
#: is neither an ask nor a probe whose tool only the group brings among the first ten: what it is for. A recipe's is
#: also the read that finds the recipe the person names (``FINDS``), as pausing one asks.
GROUPS = [
    ("la automatizacion", "flow.flow.detail", "¿cuándo arranca la automatización de reseñas?"),
    ("ejecucion", "flow.run.get", "¿cómo acabó la última ejecución de la de reseñas?"),
    ("los pasos", "flow.flow.update", "borra el último paso de la de reseñas"),
    ("la pregunta", "flow.question.answer", "contesta que sí a la pregunta de la de reseñas"),
    ("borrador", "flow.draft.dismiss", "olvida el borrador de reseñas, no lo voy a usar"),
    ("receta", "flow.recipe.list", "¿qué recetas hay para las reservas?"),
    ("receta", "flow.recipe.list", "¿hay automatizaciones prefabricadas para las citas?"),
]
TOP = 10


@pytest.fixture
def catalog_of(make_user):
    """The real catalogue of the assistant of a person with ``role`` in business ``a``, in ``language``."""

    def of(role: str, language: str) -> dict[str, Operation]:
        user = make_user(f"asker-{role}", host=A.key, role=role)
        ctx = OperationContext(scope=A, actor=user.username, permissions=permissions_for(user, A), language=language)
        return assistant.catalog(ctx)

    return of


def offered(tools: dict[str, Operation], phrase: str, synonyms=None) -> list[str]:
    """The tools a turn offers for ``phrase`` in Spanish, as the Hub ranks them (``base.assistant.RANKING``), or with
    ``synonyms`` instead of the Hub's."""
    ranking = dict(assistant.RANKING) if synonyms is None else {**assistant.RANKING, "synonyms": synonyms}
    return [op.name for op in shared.relevant(tools, [phrase], "es", **ranking)]


def test_automations_offers_its_thirty_tools():
    """Automations' assistant tools (``AI``, never ``INTERNAL`` nor the engine's «System only»): a silent drop fails."""
    tools = {name for name, op in registry.items() if op.app_label == "flow" and assistant.is_tool(op)}
    assert all(isinstance(registry[name].ai_spec(), AI) for name in tools)
    assert tools == TOOLS


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
def test_only_who_runs_the_business_is_offered_the_automations(catalog_of):
    """An automation acts in the business's name with nobody watching (``FlowConfig.role_permissions``): the owner and
    the admin hold every tool; a manager and an employee only the questions an automation asks them."""
    for role in (Membership.Role.OWNER, Membership.Role.ADMIN):
        assert {name for name in catalog_of(role, "es") if name.startswith("flow.")} == TOOLS
    for role in (Membership.Role.MANAGER, Membership.Role.EMPLOYEE):
        assert {name for name in catalog_of(role, "es") if name.startswith("flow.")} == THE_QUESTIONS


def test_the_reported_requests_are_the_owners_probes_of_layer_2():
    """Each phrase above is word for word the owner's probe of its tool: the test measures what layer 2 measures."""
    phrases = probe_phrases()
    reported = [(param.values if hasattr(param, "values") else param) for param in REPORTED]
    assert [phrases.get(comparable(phrase)) for _, phrase in reported] == [f"owner.es.{name}" for name, _ in reported]
    assert {probe["tool"] for probe in PROBES} == TOOLS  # positive control: one probe per tool, all read


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), REPORTED)
def test_the_reported_request_is_offered_its_tool_and_the_read_that_finds_it(catalog_of, name, phrase):
    tools = catalog_of(Membership.Role.OWNER, "es")
    assert name in tools  # positive control: the owner holds the tool, so its place is known
    assert comparable(phrase) not in {comparable(ask) for ask in shared.asks_of(tools[name]).get("es", ())}
    names = offered(tools, phrase)
    assert name in names, names[:10]
    assert FINDS.get(name, name) in names, names[:10]


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(
    "probe",
    [
        pytest.param(probe, marks=LIVE_53) if probe["tool"] in AWAITS_LIVE else probe
        for probe in PROBES
    ],
    ids=[probe["id"] for probe in PROBES],
)
def test_every_probe_of_automations_offers_its_tool_without_being_one_of_its_asks(catalog_of, probe):
    """The owner's thirty phrases of layer 2, the ones the model answered right too: a tool of Automations that a new ask
    elsewhere pushes out of the ones a turn offers fails here before the real-model QA sees it."""
    assert (probe["app"], probe["role"], probe["language"]) == ("flow", "owner", "es")
    tools = catalog_of(Membership.Role.OWNER, "es")
    name, phrase = probe["tool"], probe["phrase"]
    assert name in tools  # positive control: the owner holds the tool, so its place is known
    assert comparable(phrase) not in {comparable(ask) for ask in shared.asks_of(tools[name]).get("es", ())}
    names = offered(tools, phrase)
    assert name in names, (len(names), names[:10])


def test_the_hub_names_an_automation_its_runs_steps_questions_drafts_and_recipes():
    """``base.assistant.SYNONYMS``: «la automatización» is a ``flow.flow``, «la ejecución» a run (``flow.run``), «los
    pasos» its steps, «la pregunta» the one it waits on, «el borrador» the assistant's draft and «la receta» a ready-made
    one, so a request in the words of the Automations screens names what their tools are of; live alone names none
    (positive control)."""
    phrase = "abre la automatización y dime la ejecución, los pasos, la pregunta, el borrador y la receta"
    named = shared.asked([phrase], assistant.SYNONYMS).concepts
    bare = shared.asked([phrase]).concepts
    for word in ("flow", "run", "step", "question", "draft", "recipe"):
        assert any(shared.stem(word) in concept for concept in named), word
        assert not any(shared.stem(word) in concept for concept in bare), word


@pytest.mark.parametrize(
    ("phrase", "word"),
    [
        ("marca la conversación porque la respuesta automática no la entendió", "flow"),
        ("¿qué descuentos automáticos tengo?", "flow"),
        ("¿qué pasó con la venta de ayer?", "step"),
        ("marca como caducadas las cestas cuya fecha ya pasó", "step"),
        ("de paso, cobra la mesa 4", "step"),
        ("¿a qué productos se les pregunta algún extra?", "question"),
        ("borra el cliente Ana", "draft"),
        ("bórralo, ya no lo quiero", "draft"),
    ],
)
def test_a_word_that_only_shares_their_stem_names_no_automation_step_question_or_draft(phrase, word):
    """«automática» shares its stem with «automatización», «pasó» is «paso» without its accent and «pregunta» is a verb
    too: the Hub names those by their phrases, so a request about something else does not climb to Automations. «borra»
    and «bórralo» stem apart from «borrador» (``borr``, ``borra``): deleting names no draft."""
    assert not any(shared.stem(word) in concept for concept in shared.asked([phrase], assistant.SYNONYMS).concepts)


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("member", "name", "phrase"), GROUPS)
def test_each_group_brings_its_tool_among_the_first_ten(catalog_of, member, name, phrase):
    """What a group of ``SYNONYMS`` is for, measured on what a turn offers and not on how a word reads: without it, the
    request's tool falls past the first ten."""
    tools = catalog_of(Membership.Role.OWNER, "es")
    asks = {comparable(ask) for op in tools.values() for ask in shared.asks_of(op).get("es", ())}
    assert comparable(phrase) not in asks
    assert comparable(phrase) not in probe_phrases()
    group = [group for group in assistant.SYNONYMS if member in group]
    assert len(group) == 1, member  # positive control: the group is the Hub's, and only one
    without = tuple(other for other in assistant.SYNONYMS if other is not group[0])
    assert name in offered(tools, phrase)[:TOP]
    assert name not in offered(tools, phrase, without)[:TOP]
