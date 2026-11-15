"""What a word means in the Hub (hub#1145): the platform says its own words (``base.assistant.SYNONYMS``) and each app
says its own in its ``LiveAppConfig`` (``base.assistant.SYNONYMS_ATTRIBUTE``); ``base.assistant.synonyms`` gathers
them, and a turn ranks with all of them (``base.assistant.RANKING``). A malformed declaration is said at start
(``base.E017``) and never read."""

import unicodedata

import pytest
from django.apps import apps
from django.core import checks
from live import assistant as shared
from live.meta import all_live_app_configs
from live.operations import registry

from base import assistant


def stems_of(*words: str) -> frozenset[str]:
    return frozenset(shared.stem(word) for word in words)


def concepts(phrase: str, groups) -> frozenset[frozenset[str]]:
    return shared.asked([phrase], groups).concepts


@pytest.fixture
def table():
    return apps.get_app_config("table")


@pytest.fixture
def printing():
    return apps.get_app_config("printing")


def test_a_group_an_app_declares_names_its_concept(table, monkeypatch):
    phrase = "enséñame la zarpa del gato"
    assert stems_of("zarpa", "claw") not in concepts(phrase, assistant.synonyms())  # positive control: nobody says it
    monkeypatch.setattr(table, assistant.SYNONYMS_ATTRIBUTE, (("zarpa", "claw"),), raising=False)
    gathered = assistant.synonyms()
    assert ("zarpa", "claw") in gathered
    assert stems_of("zarpa", "claw") in concepts(phrase, gathered)


def test_a_turn_ranks_with_the_platforms_words_and_every_installed_apps():
    gathered = assistant.synonyms()
    assert assistant.RANKING["synonyms"] == gathered
    assert gathered[: len(assistant.SYNONYMS)] == assistant.SYNONYMS
    declared = [
        tuple(group) for config in all_live_app_configs() for group in getattr(config, assistant.SYNONYMS_ATTRIBUTE, ())
    ]
    assert declared  # positive control: some app says its own words
    assert gathered[len(assistant.SYNONYMS) :] == tuple(declared)


def test_two_apps_that_declare_the_same_word_join_their_groups_whichever_comes_first(table, printing, monkeypatch):
    """The word both say names both groups (``live.assistant`` joins the groups of a stem), and each other word only its
    own group and that word: as if both groups were one list, in any order of the apps."""
    monkeypatch.setattr(table, assistant.SYNONYMS_ATTRIBUTE, (("zarpa", "claw"),), raising=False)
    monkeypatch.setattr(printing, assistant.SYNONYMS_ATTRIBUTE, (("zarpa", "paw"),), raising=False)
    gathered = assistant.synonyms()
    assert ("zarpa", "claw") in gathered and ("zarpa", "paw") in gathered
    assert stems_of("zarpa", "claw", "paw") in concepts("enséñame la zarpa", gathered)
    assert stems_of("zarpa", "claw") in concepts("show me the claw", gathered)
    assert stems_of("zarpa", "paw") in concepts("show me the paw", gathered)
    reversed_order = (*assistant.SYNONYMS, *reversed(gathered[len(assistant.SYNONYMS) :]))
    for phrase in ("enséñame la zarpa", "show me the claw", "show me the paw"):
        assert concepts(phrase, reversed_order) == concepts(phrase, gathered), phrase


def plain(word: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", word) if not unicodedata.combining(c)).lower()


def base_words() -> frozenset[str]:
    """The words base's own operations are named with (``base.person.badge_remove``: person, badge, remove)."""
    return frozenset(
        word for name in registry if name.startswith("base.") for part in name.split(".")[1:] for word in part.split("_")
    )


def test_the_platforms_groups_name_only_what_base_does():
    """``SYNONYMS`` is the platform's: each of its groups names something base's own operations do («placa» is the badge
    of ``base.person.badge_*``). A group of an app's words goes to its app's ``LiveAppConfig``."""
    words = base_words()
    assert "badge" in words and "task" not in words  # positive and negative controls
    assert [group for group in assistant.SYNONYMS if words.isdisjoint(plain(word) for word in group)] == []


def synonym_errors() -> list:
    return [error for error in checks.run_checks(tags=["base"]) if error.id == "base.E017"]


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
    monkeypatch.setattr(table, assistant.SYNONYMS_ATTRIBUTE, declared, raising=False)
    errors = synonym_errors()
    if why is None:
        assert errors == []
        assert {("zarpa", "claw"), ("pata", "paw")} <= set(assistant.synonyms())
        return
    [error] = errors
    assert "table" in error.msg and why in error.msg and error.obj is table
    # What the check refuses is never read; every other app's words are, as before.
    others = tuple(
        tuple(group)
        for config in all_live_app_configs()
        if config is not table
        for group in getattr(config, assistant.SYNONYMS_ATTRIBUTE, ())
    )
    assert assistant.synonyms() == (*assistant.SYNONYMS, *others)
