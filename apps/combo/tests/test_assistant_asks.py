"""What layer 1 of the assistant's QA says of Menus and combos: which tools it offers, what an employee is never
offered, and that the requests of the real-model QA (hub#1091), in the owner's and the employee's own words, are
offered their existing operation.

Every ask of every tool of combo bringing its tool among the first ten, role by role, in English and in Spanish, out of
the catalogue of a business with every app on and ranked as a turn ranks, is ``base/tests/test_assistant_asks.py``'s
(combo is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020`` over its asks and the guard that no ask copies a
probe of layer 2.
"""

import json
from pathlib import Path

import pytest
from django.conf import settings
from live import assistant as shared
from live.operations import AI, registry

from base import assistant
from base.models import Membership
from base.tests.test_assistant_asks import TOP, assert_its_asks_bring, assert_offered_with_room, comparable
from base.tests.test_assistant_asks import offered_place, offered_to, place_of_no_ask, probe_phrases
from base.tests.test_assistant_asks import catalog_of  # noqa: F401 (a fixture: the tests below take it by name)

#: The writes of Menus and combos: they need ``combo.manage``, which an employee does not hold, and none of them is one a
#: manager approves, so an employee's assistant is never offered them (the QA's employee probes of them are refusals).
WRITES = {
    "combo.combo.create",
    "combo.combo.update",
    "combo.combo.delete",
    "combo.combo.set_image",
    "combo.group.create",
    "combo.group.update",
    "combo.group.delete",
    "combo.group.reorder",
    "combo.option.create",
    "combo.option.bulk_create",
    "combo.option.update",
    "combo.option.delete",
    "combo.option.reorder",
}
#: The request of hub#1091's QA as the owner said it, and nothing of the tools' ``asks``: before Menus and combos said
#: its asks, «opciones» named no choice of a menu and «ordena» named a device too (the stem of «ordenador»), so the turn
#: offered the changes of a menu, of a choice and of a printer ahead of putting the choices in order, and the model
#: chose to delete the choices and create them again.
REPORTED = (
    "combo.option.reorder",
    "ordena las opciones de Platos QA del Menú QA así: flan, merluza, lentejas y café, incluyendo todas",
)
PROBES_DIR = Path(settings.BASE_DIR) / "tests" / "e2e" / "qa" / "probes"
#: Every probe of layer 2 of Menus and combos, the owner's and the employee's real phrases from QA, and
#: the owner's of the day a restaurant gets ready to sell.
PROBES = [
    probe
    for path in sorted(PROBES_DIR.glob("*.json"))
    for probe in json.loads(path.read_text(encoding="utf-8"))["probes"]
    if probe["app"] == "combo"
]
#: What a person says in words of their own, neither an ask nor a probe of layer 2, one per tool of Menus and combos:
#: each reaches its tool among the first ten by its asks and not without them, so asks that stop reading as people speak
#: fail here, tool by tool.
OWN_WORDS = [
    ("combo.combo.list", "repásame los que tenemos montados y lo que cuesta cada uno"),
    ("combo.combo.get", "¿qué trae el infantil?"),
    ("combo.combo.for_sale", "¿qué se puede pedir ya de mostrador?"),
    ("combo.combo.suggest_image", "¿qué dibujos le pegan al de verano?"),
    ("combo.combo.resolve", "¿a cuánto se queda el degustación con entrecot?"),
    ("combo.combo.create", "monta un vegano nuevo a 14"),
    ("combo.combo.update", "rebájame el infantil a 8,50"),
    ("combo.combo.delete", "el de Navidad no vuelve, quítalo del todo"),
    ("combo.combo.set_image", "para el de invierno quiero el dibujo del cocido"),
    ("combo.group.create", "al infantil le hace falta un plato más: el postre"),
    ("combo.group.update", "deja que elijan dos entrantes"),
    ("combo.group.delete", "el vegano se queda sin postre"),
    ("combo.group.reorder", "quiero que los postres salgan antes que los segundos"),
    ("combo.option.create", "añade merluza a los segundos"),
    ("combo.option.bulk_create", "mete de golpe tres postres en el infantil"),
    ("combo.option.update", "nos hemos quedado sin natillas en el infantil"),
    ("combo.option.delete", "ya no damos gazpacho de entrante"),
    ("combo.option.reorder", "que el helado salga el primero de los postres"),
]
#: The Hub's group of the choices of a course (``base.assistant.SYNONYMS``): «opción» and «elección» name what
#: ``combo.option`` (and ``modifier.option``) is of, as «option» and «choice» do.
CHOICES = ("opcion", "opciones", "eleccion", "elecciones", "option", "options", "choice", "choices")
#: The places an ask of another app keeps free below the first ten: the asks of the next app to say its own take them.
ROOM = 2


def test_menus_and_combos_is_listed_so_layer_1_sweeps_every_ask_of_it():
    """Menus and combos is in ``LIVE_ASSISTANT_ASKS_REQUIRED``: ``base/tests/test_assistant_asks.py`` ranks each of its
    asks for every role and language, and ``live.E020`` requires them of each of its tools."""
    assert "combo" in settings.LIVE_ASSISTANT_ASKS_REQUIRED


def test_combo_offers_its_eighteen_tools():
    """Menus and combos' tools are its eighteen operations (``AI``, never ``INTERNAL``): a silent drop of a tool fails.
    The upload of a photo of its own (the form's file) and the reaction to Inventory's deletion are none."""
    tools = {name for name, op in registry.items() if op.app_label == "combo" and assistant.is_tool(op)}
    assert all(isinstance(registry[name].ai_spec(), AI) for name in tools)
    assert len(tools) == 18
    assert WRITES < tools
    assert not {"combo.combo.upload_image", "combo.option.drop_product"} & tools


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
def test_an_employee_is_never_offered_a_change_of_the_menus(catalog_of):
    owner = catalog_of(Membership.Role.OWNER, "es")
    employee = catalog_of(Membership.Role.EMPLOYEE, "es")
    assert WRITES <= set(owner)
    assert WRITES.isdisjoint(employee), sorted(WRITES & set(employee))
    assert "combo.combo.for_sale" in employee  # positive control: an employee reads what the till may sell


def test_the_reported_request_is_a_probe_of_layer_2():
    name, phrase = REPORTED
    assert probe_phrases().get(comparable(phrase)) == f"qa20261108.owner.es.{name}"


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
def test_putting_the_choices_in_order_is_offered_ahead_of_deleting_and_creating_them_again(catalog_of):
    """hub#1091: the owner's request offers the reorder of the choices among the first ten and ahead of every other
    change of Menus and combos, deleting and creating a choice included."""
    tools = catalog_of(Membership.Role.OWNER, "es")
    name, phrase = REPORTED
    place = place_of_no_ask(tools, name, phrase)
    assert place is not None and place <= TOP, place
    ranked = offered_to(tools, phrase)
    ahead = [tool for tool in ranked[: place - 1] if tool in WRITES]
    assert ahead == [], ahead


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
@pytest.mark.parametrize("probe", PROBES, ids=[probe["id"] for probe in PROBES])
def test_every_probe_of_menus_offers_its_tool_to_whoever_may_run_it(catalog_of, probe):
    """The phrases of layer 2 of Menus and combos, the ones the model answered right too: a tool of Menus that a new ask
    elsewhere pushes out of the first half of the ones a turn offers fails here before the real-model QA sees it. What
    the employee asks of a change of the menus is a refusal: the tool is not theirs to be offered."""
    role = {"owner": Membership.Role.OWNER, "employee": Membership.Role.EMPLOYEE}[probe["role"]]
    tools = catalog_of(role, probe["language"])
    if probe["expect"] == "refused":
        assert (probe["role"], probe["tool"] in WRITES) == ("employee", True)
        assert probe["tool"] not in tools
        return
    assert_offered_with_room(tools, probe["tool"], probe["phrase"], probe["language"])


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), OWN_WORDS)
def test_a_request_in_the_persons_own_words_reaches_its_tool_by_its_asks(catalog_of, name, phrase):
    assert_its_asks_bring(catalog_of(Membership.Role.OWNER, "es"), name, phrase, "es")


def test_every_tool_of_menus_has_a_phrase_of_its_own():
    """``OWN_WORDS`` covers every tool once: a tool whose asks no phrase of a person's own reaches would let its asks
    change unseen (the sweep of ``base`` ranks only the asks themselves)."""
    tools = sorted(name for name, op in registry.items() if op.app_label == "combo" and assistant.is_tool(op))
    assert sorted(name for name, _ in OWN_WORDS) == tools


def test_the_hub_reads_an_opcion_and_an_eleccion_as_a_choice_of_a_course():
    """``base.assistant.SYNONYMS``: «las opciones» and «las elecciones» name what ``combo.option`` is of, as «options»
    and «choices» do; without the Hub's group, neither does (positive control)."""
    assert CHOICES in assistant.SYNONYMS
    option = shared.stem("option")
    for phrase in ("ordena las opciones del segundo plato", "¿qué elecciones tiene el postre?"):
        assert any(option in concept for concept in shared.asked([phrase], assistant.SYNONYMS).concepts), phrase
        assert not any(option in concept for concept in shared.asked([phrase]).concepts), phrase


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
def test_the_choices_named_as_elecciones_bring_their_reorder_only_with_the_hubs_group(catalog_of):
    """A phrase that is no ask and no probe: with the Hub's group of the choices, the reorder of the choices is among the
    first ten; without it, «elecciones» names nothing and the reorder falls out of them."""
    tools = catalog_of(Membership.Role.OWNER, "es")
    phrase = "ordena las elecciones del segundo plato: pollo, merluza y tortilla"
    assert comparable(phrase) not in probe_phrases()
    assert "combo.option.reorder" in offered_to(tools, phrase)[:TOP]
    without = tuple(group for group in assistant.SYNONYMS if group != CHOICES)
    assert "combo.option.reorder" not in offered_to(tools, phrase, synonyms=without)[:TOP]


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
@pytest.mark.parametrize("role", [Membership.Role.OWNER, Membership.Role.ADMIN])
@pytest.mark.parametrize("language", ["en", "es"])
def test_a_value_of_a_customers_field_takes_no_place_from_the_choices_of_a_menu(catalog_of, role, language):
    """``customer.field.update`` adds a value to a customer's field («XL» to the size field): said as «la opción XL» /
    «an XL option», its ask was read as a choice of a menu once the Hub's group of the choices existed and fell past
    the tenth place, the last ``base/tests/test_assistant_asks.py`` allows."""
    tools = catalog_of(role, language)
    name = "customer.field.update"
    places = {ask: offered_place(tools, name, ask, language) for ask in shared.asks_of(tools[name])[language]}

    assert {ask: place for ask, place in places.items() if place is None or place > TOP - ROOM} == {}
