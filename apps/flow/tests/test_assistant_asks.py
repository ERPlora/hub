"""What layer 1 of the assistant's QA does not say of Automations: which tools it offers and to whom, the words of the
Hub that name its records, and that the owner's requests of the real-model QA (hub#1106), in the owner's own words,
are offered their existing operation.

Every ask of every tool of flow bringing its tool among the first ten, role by role, in both languages, is
``base/tests/test_assistant_asks.py``'s (flow is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020`` over the
asks and the guard that no ask copies a probe of layer 2.
"""

import dataclasses
import json
from pathlib import Path

import pytest
from django.conf import settings
from live import assistant as shared
from live.operations import AI, Operation, registry

from base import assistant
from base.models import Membership
from base.tests.test_assistant_asks import TOP, assert_offered_with_room, comparable, offered_to, place_of_no_ask
from base.tests.test_assistant_asks import probe_phrases
from base.tests.test_assistant_asks import catalog_of  # noqa: F401 (a fixture: the tests below take it by name)

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
#: What a person says in words of their own, neither an ask nor a probe of layer 2, for each tool whose asks no request
#: above catches: its probe already came among the tools a turn offers by its name, its description and the Hub's words.
#: Here it is the tool's asks that bring it among the first ten, so asks that stop reading as people speak fail.
OWN_WORDS = [
    ("flow.catalog.read", "¿a qué eventos puede responder una automatización?"),
    ("flow.flow.list", "enséñame todo lo que tengo montado y si está encendido"),
    ("flow.flow.status", "¿alguna automatización escucha ya las reservas canceladas?"),
    ("flow.flow.create", "monta otra automatización para los lunes por la mañana"),
    ("flow.flow.set_enabled", "deja en pausa la automatización de reseñas"),
    ("flow.flow.duplicate", "haz otra igual que la automatización de reseñas"),
    ("flow.flow.delete", "la automatización de reseñas sobra, ya no la uso"),
    ("flow.run.list", "¿cuántas veces ha fallado la automatización de reseñas?"),
    ("flow.run.get", "¿qué falló esta mañana en la de reseñas y en qué paso?"),
    ("flow.run.retry", "lánzala otra vez desde donde falló, ya está el permiso"),
    ("flow.recipe.list", "¿qué automatizaciones listas para usar hay para las reservas?"),
    ("flow.recipe.enable", "quiero que me avise cuando alguien cancele, pon esa receta"),
    ("flow.recipe.disable", "no quiero más el recordatorio de citas de la receta"),
    ("flow.recipe.restore", "quiero la versión original de la de cumpleaños"),
    ("flow.recipe.repair", "pon al día la receta de reseñas"),
    ("flow.draft.list", "¿tengo algo pendiente de revisar que me dejara el asistente?"),
    ("flow.draft.get", "¿qué dudas le quedan a lo que me propusiste ayer?"),
    ("flow.draft.propose", "que cada vez que se cobre una venta grande se cree una tarea, automatízalo"),
    ("flow.draft.dismiss", "no me sirve lo que me propusiste, descártalo"),
    ("flow.secret.list", "¿qué nombres guardados pueden usar mis automatizaciones?"),
    ("flow.secret.delete", "quita el token de la tienda, ya no vale"),
    ("flow.question.list", "¿tengo preguntas pendientes de alguna automatización?"),
    ("flow.question.get", "¿qué me está preguntando la de reseñas?"),
]
#: The tools whose asks a request above already catches: without them, a reported request, a probe, a group's request
#: or one that waits for live falls past where it must be.
CAUGHT_ABOVE = {
    "flow.event.sample",
    "flow.flow.test",
    "flow.flow.run",
    "flow.flow.detail",
    "flow.flow.update",
    "flow.flow.grant",
    "flow.question.answer",
}


def offered_without_its_asks(tools: dict[str, Operation], name: str, phrase: str) -> list[str]:
    """``offered`` with ``name`` saying no asks: how a turn ranked it by its name, its description and the Hub's words."""
    op = tools[name]
    bare = {**tools, name: dataclasses.replace(op, ai={key: value for key, value in op.ai.items() if key != "asks"})}
    assert not shared.asks_of(bare[name])  # positive control: the tool is ranked without its asks
    return offered_to(bare, phrase)


def is_own_words(tools: dict[str, Operation], phrase: str) -> bool:
    """Whether ``phrase`` is neither an ask of any tool in Spanish nor a probe of layer 2: words of the person's own."""
    asks = {comparable(ask) for op in tools.values() for ask in shared.asks_of(op).get("es", ())}
    return comparable(phrase) not in asks and comparable(phrase) not in probe_phrases()


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
    assert place_of_no_ask(tools, name, phrase) is not None
    assert FINDS.get(name, name) in offered_to(tools, phrase)


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
    assert place_of_no_ask(catalog_of(Membership.Role.OWNER, "es"), probe["tool"], probe["phrase"]) is not None


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
    assert is_own_words(tools, phrase)
    group = [group for group in assistant.SYNONYMS if member in group]
    assert len(group) == 1, member  # positive control: the group is the Hub's, and only one
    without = tuple(other for other in assistant.SYNONYMS if other is not group[0])
    assert name in offered_to(tools, phrase)[:TOP]
    assert name not in offered_to(tools, phrase, synonyms=without)[:TOP]


#: Three asked naming «la automatización» and not only its own name: the thing they act on is named, so they come
#: among the first ten.
NAMED = [
    ("flow.flow.set_enabled", "activa la automatización de reseñas"),
    ("flow.flow.update", "renombra la automatización de reseñas como Opiniones"),
    ("flow.flow.grant", "permite a la automatización de reseñas mandar correos"),
]


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), NAMED)
def test_what_waits_for_live_is_offered_when_the_request_names_the_automation(catalog_of, name, phrase):
    tools = catalog_of(Membership.Role.OWNER, "es")
    assert is_own_words(tools, phrase)
    assert {name for name, _ in NAMED} == AWAITS_LIVE  # positive control: the same three the probes wait for
    assert name in offered_to(tools, phrase)[:TOP]


def test_the_asks_of_every_tool_are_caught_by_a_request():
    """Each tool's asks bring some request of this file where it must be: a tool without its own words here, nor a
    request above that falls without its asks, would let any asks pass (positive control: all thirty, once)."""
    own = {name for name, _ in OWN_WORDS}
    assert own.isdisjoint(CAUGHT_ABOVE)
    assert own | CAUGHT_ABOVE == TOOLS
    assert len(OWN_WORDS) == len(own)


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), OWN_WORDS)
def test_a_request_in_the_persons_own_words_reaches_its_tool_by_its_asks(catalog_of, name, phrase):
    tools = catalog_of(Membership.Role.OWNER, "es")
    assert is_own_words(tools, phrase)
    assert_offered_with_room(tools, name, phrase, room=TOP)

    unasked = offered_without_its_asks(tools, name, phrase)
    assert name not in unasked[:TOP], unasked.index(name) + 1
