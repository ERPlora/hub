"""The card of changing one's own preferences from the assistant (``base.profile.preferences_set``, BASE-F64): it says
what was asked and nothing else, and the yes changes only that. Asked only for the language, the model had to make up
the theme, the palette and the size to call it: the card read «English · 100%» and the yes wiped the person's own
appearance."""

from functools import partial

import pytest
from live.context import OperationContext
from live.operations import get

from base import assistant
from base.tenancy.tests.business import HUB_DB, in_business_a
from base.tests.assistant_context import owner_of_a
from base.tests.card_values import ctx
from base.tests.test_assistant_yes_for_its_card import no_card_but_the_model_hears, turn_as, yes_to
from base.tests.test_services_assistant import call

__all__ = ["in_business_a"]

pytestmark = HUB_DB

SET = "base.profile.preferences_set"
MINE = {"language": "es", "theme_mode": "dark", "palette": "forest", "ui_scale": 120}


def line(arguments: dict, language: str) -> list[tuple]:
    fields = assistant.cards.card(get(SET), arguments, language, ctx(language=language))["fields"]
    return [(field["name"], field["kind"], field["label"], field["value"]) for field in fields]


def kept(person: OperationContext) -> dict:
    """The preferences «My profile» keeps for ``person``."""
    profile = get("base.profile.get")
    answer = profile(person, profile.input()).model_dump()
    return {name: answer[name] for name in MINE}


@pytest.fixture
def owner(make_user) -> OperationContext:
    person = owner_of_a(make_user, "es")
    choose = get(SET)
    choose(person, choose.input(**MINE))
    return person


@pytest.mark.parametrize(
    ("arguments", "value"),
    [
        ({"language": "en"}, "English"),
        ({"theme_mode": "light"}, "Claro"),
        ({"palette": "ocean"}, "Océano"),
        ({"ui_scale": 90}, "90%"),
    ],
)
def test_the_card_says_the_one_preference_asked_and_the_yes_changes_only_that(owner, arguments, value):
    plan = turn_as(owner, call(SET, arguments))
    assert [(field["name"], field["value"]) for field in plan["confirm"]["fields"]] == [(*arguments, value)]
    assert kept(owner) == MINE
    [ran] = yes_to(plan, turn_of=partial(turn_as, owner))["executed"]
    assert (ran["name"], ran["outcome"]) == (SET, "ok")
    assert kept(owner) == {**MINE, **arguments}


def test_what_the_model_leaves_as_null_is_neither_said_nor_changed(owner):
    plan = turn_as(owner, call(SET, {"language": "en", "theme_mode": None, "palette": None, "ui_scale": None}))
    assert [field["name"] for field in plan["confirm"]["fields"]] == ["language"]
    yes_to(plan, turn_of=partial(turn_as, owner))
    assert kept(owner) == {**MINE, "language": "en"}


@pytest.mark.parametrize("arguments", [{}, {"language": None, "theme_mode": None}])
def test_preferences_that_name_none_show_no_card(owner, arguments):
    no_card_but_the_model_hears(turn_as(owner, call(SET, arguments)), "invalid_payload")
    assert kept(owner) == MINE


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        (
            "en",
            [
                ("language", "text", "Language", "The business's language"),
                ("theme_mode", "text", "Appearance", "The business's appearance"),
                ("palette", "text", "Palette", "The business's palette"),
            ],
        ),
        (
            "es",
            [
                ("language", "text", "Idioma", "El idioma del negocio"),
                ("theme_mode", "text", "Apariencia", "La apariencia del negocio"),
                ("palette", "text", "Paleta", "La paleta del negocio"),
            ],
        ),
    ],
)
def test_back_to_the_business_s_is_said_and_never_left_blank(language, expected):
    """Empty is a choice of «My profile»; a blank datum does not show, and the card would say nothing of what it does."""
    assert line({"language": "", "theme_mode": "", "palette": ""}, language) == expected
