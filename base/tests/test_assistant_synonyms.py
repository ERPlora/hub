"""What a word means in the Hub: the platform says its own words (``base.assistant.relevance.SYNONYMS``) and each app says its own
in its ``LiveAppConfig`` (``base.assistant.relevance.SYNONYMS_ATTRIBUTE``); ``base.assistant.relevance.synonyms`` gathers them, and a turn
ranks with the ones that count for the tools it may offer (``base.assistant.relevance.ranking``). A malformed declaration is said
at start (``base.E018``) and never read."""

import unicodedata

import pytest
from django.apps import apps
from django.core import checks
from live import assistant as shared
from live.meta import all_live_app_configs
from live.operations import registry

from base import assistant
from base.models import Membership
from base.tenancy.tests.business import HUB_DB, in_business_a
from base.tests.test_assistant_asks import (
    TOP,
    comparable,
    members,
    offered_place,
    offered_to,
    place_of_no_ask,
    probe_phrases,
)

__all__ = ["in_business_a"]

#: The words of an item («elemento»), a word only Demo says (``demo.item``), in requests of other apps' tools that name
#: no product otherwise (Inventory reads «la carta» as its products).
ELEMENT_REQUESTS = [
    ("inventory.product.delete", "borra el elemento «Tarta de queso» del inventario"),
    ("inventory.product.create", "añade un elemento nuevo: tarta de queso a 5 euros"),
]


def stems_of(*words: str) -> frozenset[str]:
    return frozenset(shared.stem(word) for word in words)


def concepts(phrase: str, groups) -> frozenset[frozenset[str]]:
    return shared.asked([phrase], groups).concepts


def said_by(config) -> tuple[tuple[str, ...], ...]:
    return tuple(tuple(group) for group in getattr(config, assistant.relevance.SYNONYMS_ATTRIBUTE, ()))


def tools_of(*labels: str) -> dict:
    """The assistant's tools of the apps ``labels``, as a catalogue holds them (by name)."""
    return {name: op for name, op in sorted(registry.items()) if op.app_label in labels and assistant.tools.is_tool(op)}


@pytest.fixture
def table():
    return apps.get_app_config("table")


@pytest.fixture
def printing():
    return apps.get_app_config("printing")


@pytest.fixture
def demo():
    return apps.get_app_config("demo")


def test_a_group_an_app_declares_names_its_concept(table, monkeypatch):
    phrase = "enséñame la zarpa del gato"
    assert stems_of("zarpa", "claw") not in concepts(phrase, assistant.relevance.synonyms())  # positive control: nobody says it
    monkeypatch.setattr(table, assistant.relevance.SYNONYMS_ATTRIBUTE, (("zarpa", "claw"),), raising=False)
    gathered = assistant.relevance.synonyms()
    assert ("zarpa", "claw") in gathered
    assert stems_of("zarpa", "claw") in concepts(phrase, gathered)


def test_the_hubs_words_are_the_platforms_and_then_every_installed_apps():
    gathered = assistant.relevance.synonyms()
    assert gathered[: len(assistant.relevance.SYNONYMS)] == assistant.relevance.SYNONYMS
    apps_words = tuple(group for config in all_live_app_configs() for group in said_by(config))
    assert apps_words  # positive control: some app says its own words
    assert gathered[len(assistant.relevance.SYNONYMS) :] == apps_words


def test_two_apps_that_declare_the_same_word_join_their_groups_whichever_comes_first(table, printing, monkeypatch):
    """The word both say names both groups (``live.assistant`` joins the groups of a stem), and each other word only its
    own group and that word: as if both groups were one list, in any order of the apps."""
    monkeypatch.setattr(table, assistant.relevance.SYNONYMS_ATTRIBUTE, (("zarpa", "claw"),), raising=False)
    monkeypatch.setattr(printing, assistant.relevance.SYNONYMS_ATTRIBUTE, (("zarpa", "paw"),), raising=False)
    gathered = assistant.relevance.synonyms()
    assert ("zarpa", "claw") in gathered and ("zarpa", "paw") in gathered
    assert stems_of("zarpa", "claw", "paw") in concepts("enséñame la zarpa", gathered)
    assert stems_of("zarpa", "claw") in concepts("show me the claw", gathered)
    assert stems_of("zarpa", "paw") in concepts("show me the paw", gathered)
    reversed_order = (*assistant.relevance.SYNONYMS, *reversed(gathered[len(assistant.relevance.SYNONYMS) :]))
    for phrase in ("enséñame la zarpa", "show me the claw", "show me the paw"):
        assert concepts(phrase, reversed_order) == concepts(phrase, gathered), phrase


def plain(word: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", word) if not unicodedata.combining(c)).lower()


def base_words() -> frozenset[str]:
    """The words base's own operations are named with (``base.person.badge_remove``: person, badge, remove)."""
    own = [name.split(".")[1:] for name in registry if name.startswith("base.")]
    return frozenset(word for parts in own for part in parts for word in part.split("_"))


def test_the_platforms_groups_name_only_what_base_does():
    """``SYNONYMS`` is the platform's: each of its groups names something base's own operations do («placa» is the badge
    of ``base.person.badge_*``). A group of an app's words goes to its app's ``LiveAppConfig``."""
    words = base_words()
    assert "badge" in words and "task" not in words  # positive and negative controls
    assert [group for group in assistant.relevance.SYNONYMS if words.isdisjoint(plain(word) for word in group)] == []


def test_an_app_out_of_the_store_says_its_words_only_where_its_tools_are_offered(demo):
    """Demo never reaches a customer (``listed = False``): where its tools are not offered, its «elemento» would only
    bring other apps' items, a cart's or a price list's, in front of what the person asks for."""
    assert not demo.listed and said_by(demo)  # positive controls: out of the store, and it says words of its own
    item = shared.stem("item")
    phrase = ELEMENT_REQUESTS[0][1]
    others = tools_of("inventory", "cart_checkout", "pricing")
    assert not any(item in concept for concept in concepts(phrase, assistant.relevance.ranking(others)["synonyms"]))
    with_demo = {**others, **tools_of("demo")}
    assert any(item in concept for concept in concepts(phrase, assistant.relevance.ranking(with_demo)["synonyms"]))


def test_the_words_of_an_app_in_the_store_count_in_every_turn(demo):
    """A listed app's words also name what other apps share: Appointments' «bloqueo» is a reservation's blocked date
    too, so a turn without any of its tools still reads them."""
    reservations = tools_of("reservation")
    assert reservations and not any(op.app_label == "appointment" for op in reservations.values())
    counted = assistant.relevance.ranking(reservations)["synonyms"]
    assert set(counted) == set(assistant.relevance.synonyms()) - set(said_by(demo))
    assert any(stems_of("blocked") <= concept for concept in concepts("¿qué bloqueos hay en Navidad?", counted))


def test_a_turn_ranks_with_the_words_that_count_for_its_tools():
    tools = tools_of("inventory", "cart_checkout", "pricing")
    name, phrase = ELEMENT_REQUESTS[0]
    turn = [op.name for op in assistant.relevance.relevant(tools, [phrase], "es")]
    assert turn == [op.name for op in shared.relevant(tools, [phrase], "es", **assistant.relevance.ranking(tools))]
    every = {**assistant.relevance.ranking(tools), "synonyms": assistant.relevance.synonyms()}
    assert turn != [op.name for op in shared.relevant(tools, [phrase], "es", **every)]  # positive control


@pytest.fixture
def owner_tools(make_user):
    """The owner's catalogue in business A (every app on), in Spanish, without Demo's tools: a customer's."""
    tools = assistant.tools.catalog(members(make_user, "words")(Membership.Role.OWNER, "es"))
    assert any(op.app_label == "demo" for op in tools.values())  # positive control: there were some to leave out
    return {name: op for name, op in tools.items() if op.app_label != "demo"}


@HUB_DB  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), ELEMENT_REQUESTS)
def test_an_element_in_a_customers_words_brings_their_tool_and_not_demos_items(owner_tools, name, phrase):
    """With Demo's words, these came 30th and 18th: «elemento» brought a cart's items and a price list's first."""
    every = assistant.relevance.synonyms()
    assert offered_place(owner_tools, name, phrase) <= 10
    assert offered_place(owner_tools, name, phrase, synonyms=every) > 10


def synonym_errors() -> list:
    return [error for error in checks.run_checks(tags=["base"]) if error.id == "base.E018"]


def test_the_words_every_app_declares_are_sound():
    assert synonym_errors() == []


@pytest.mark.parametrize(
    ("declared", "why"),
    [
        (("zarpa", "claw"), "not a list of groups"),  # one group written bare would read as its letters
        ("zarpa claw", "not a list of groups"),
        ((("zarpa",),), "two words or more"),
        ((("zarpa", 7),), "two words or more"),
        ((("zarpa", " "),), "two words or more"),
        ((("zarpa", "claw"), ["pata", "paw"]), None),
    ],
)
def test_what_an_app_declares_is_checked_at_start_and_never_read_when_malformed(table, monkeypatch, declared, why):
    monkeypatch.setattr(table, assistant.relevance.SYNONYMS_ATTRIBUTE, declared, raising=False)
    errors = synonym_errors()
    if why is None:
        assert errors == []
        assert {("zarpa", "claw"), ("pata", "paw")} <= set(assistant.relevance.synonyms())
        return
    [error] = errors
    assert "table" in error.msg and why in error.msg and error.obj is table
    # What the check refuses is never read; every other app's words are, as before.
    others = tuple(
        tuple(group)
        for config in all_live_app_configs()
        if config is not table
        for group in getattr(config, assistant.relevance.SYNONYMS_ATTRIBUTE, ())
    )
    assert assistant.relevance.synonyms() == (*assistant.relevance.SYNONYMS, *others)


# ── An app said with the menu it leaves or is in: base's own words (its ``assistant_synonyms``) ─────────────────────

#: How a person who does not know that a module is called an app asks to turn it off or on: by its name, with the menu
#: it leaves or is in. Without base's words none of them is among the first ten, and most are not offered at all: the
#: tools of the app named and, by «menú», those of Menus and combos come first.
APP_IN_THE_MENU = [
    ("es", "base.app.disable", "no quiero ver Reservas en el menú"),
    ("es", "base.app.disable", "quita Tareas del menú, no la usamos"),
    ("es", "base.app.disable", "saca Inventario del menú"),
    ("es", "base.app.disable", "oculta Mesas del menú"),
    ("es", "base.app.disable", "quita del menú Control horario, no lo usamos"),
    ("es", "base.app.enable", "no encuentro Inventario en el menú, vuelve a ponerlo"),
    ("es", "base.app.enable", "vuelve a poner Tareas en el menú"),
    ("es", "base.app.enable", "quiero que vuelva a salir Citas en el menú"),
    ("es", "base.app.enable", "vuelve a poner Caja en el menú"),
    ("en", "base.app.disable", "take Reservations out of the menu, we don't use it"),
    ("en", "base.app.disable", "remove Tasks from the menu"),
    ("en", "base.app.disable", "hide Customers from the menu"),
    ("en", "base.app.enable", "put Tasks back on the menu"),
    ("en", "base.app.enable", "I can't find Inventory in the menu, put it back"),
    ("en", "base.app.enable", "add Kitchen to the menu"),
]

#: The owner's probe of layer 2 that asks for an app back «disponible en el menú»: it came 23rd.
APP_BACK_IN_THE_MENU_PROBE = "quiero volver a tener Reservas disponible en el menú con todo lo que tenía"

#: «Del menú», «en el menú» and «al menú» said of a menu of Menus and combos, or of what it offers: none names an app.
MENUS_OF_COMBOS = [
    "quita los postres del menú vegano",
    "quita la tarta de queso del menú",
    "añade el flan al menú del día",
    "ya no damos sopa en el menú infantil",
    "pon la paella en el menú de los domingos",
    "take the soup off the menu",
    "put the lentils in Starters of the menu of the day",
]


def base_groups() -> tuple[tuple[str, ...], ...]:
    return said_by(apps.get_app_config("base"))


def names(phrase: str, wanted: str) -> bool:
    """Whether base's words read ``phrase`` as naming the stem of ``wanted``."""
    return any(shared.stem(wanted) in concept for concept in concepts(phrase, base_groups()))


@pytest.fixture
def owner_catalog(make_user):
    """``owner_catalog(language)``: the catalogue of business A's owner (every app on), who asks in ``language``."""
    of = members(make_user, "menu")
    return lambda language: assistant.tools.catalog(of(Membership.Role.OWNER, language))


def without_base_groups(tools: dict) -> tuple:
    counted = assistant.relevance.ranking(tools)["synonyms"]
    without = tuple(group for group in counted if group not in base_groups())
    assert len(without) == len(counted) - len(base_groups()) > 0  # positive control: exactly base's groups are left out
    return without


@HUB_DB  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("language", "name", "phrase"), APP_IN_THE_MENU)
def test_an_app_said_with_the_menu_brings_turning_it_off_or_on_among_the_first_ten(
    owner_catalog, language, name, phrase
):
    tools = owner_catalog(language)
    assert comparable(phrase) not in probe_phrases()
    place = place_of_no_ask(tools, name, phrase, language)
    assert place is not None and place <= TOP, place
    assert name not in offered_to(tools, phrase, language, synonyms=without_base_groups(tools))[:TOP]


@HUB_DB  # the catalogue is of the apps on in the business (base.activation)
def test_the_probe_that_asks_for_an_app_back_in_the_menu_brings_turning_it_on_among_the_first_ten(owner_catalog):
    tools = owner_catalog("es")
    assert probe_phrases()[comparable(APP_BACK_IN_THE_MENU_PROBE)] == "qa20261108.owner.es.base.app.enable"
    assert offered_place(tools, "base.app.enable", APP_BACK_IN_THE_MENU_PROBE) <= TOP
    without = without_base_groups(tools)
    assert offered_place(tools, "base.app.enable", APP_BACK_IN_THE_MENU_PROBE, synonyms=without) > TOP


@pytest.mark.parametrize(
    ("phrase", "switch"),
    [
        ("quita Tareas del menú", "disable"),
        ("quita del menú Tareas", "disable"),
        ("take the Time clock off the menu", "disable"),
        ("vuelve a poner Tareas en el menú", "enable"),
        ("añade al menú Reservas online", "enable"),
        ("put Price Lists back on the menu", "enable"),
        ("quiero Caja disponible en el menú", "enable"),
        # An app with two names joined («Ventas / TPV», «Menús y combos») is said by either.
        ("quita Ventas del menú", "disable"),
        ("quita TPV del menú", "disable"),
        ("pon Menús en el menú", "enable"),
    ],
)
def test_base_reads_an_apps_name_beside_the_menu_as_the_app_and_where_it_goes_as_its_switch(phrase, switch):
    other = {"disable": "enable", "enable": "disable"}[switch]
    assert names(phrase, "app") and names(phrase, switch) and not names(phrase, other)
    # Positive control: neither live nor the platform's words read it so.
    for without in (assistant.relevance.SYNONYMS, ()):
        assert not any(shared.stem("app") in concept for concept in concepts(phrase, without)), phrase


@pytest.mark.parametrize("phrase", MENUS_OF_COMBOS)
def test_base_reads_no_app_in_a_menu_of_menus_and_combos(phrase):
    assert not any(names(phrase, word) for word in ("app", "enable", "disable"))


def test_base_words_name_an_app_only_beside_a_name_of_an_app_of_the_store(demo):
    assert names("quita Tareas del menú", "app")  # positive control
    assert not names(f"quita {demo.verbose_name} del menú", "app")  # out of the store, never shown to a customer
    assert not names("quita Base del menú", "app")  # the platform is no app a business turns on or off
