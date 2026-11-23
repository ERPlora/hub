"""The card of changing how the business asks for the PIN from the assistant (``base.access.settings_update``): each
control of the «PIN pad» card of Settings › General that the change sets, by its name there and the value it will show
— never «Always, and again after a while without use» with no minutes. Asking again after inactivity takes its minutes:
without them the write is refused before any card, and the assistant asks the person how many."""

import json
from pathlib import Path

import pytest
from django.conf import settings
from django.utils import translation
from live import assistant as shared
from live.operations import get

from base import assistant
from base.models.access import AccessSettings
from base.services import profile
from base.tenancy.tests.business import HUB_DB, in_business_a
from base.tests.card_values import ctx

__all__ = ["in_business_a"]

pytestmark = HUB_DB

UPDATE = "base.access.settings_update"


def fields(arguments: dict, language: str) -> list[dict]:
    return assistant.cards.card(get(UPDATE), arguments, language, ctx(language=language))["fields"]


def pin_pad(label: str, on: bool) -> dict:
    return {"name": "pin_pad", "label": label, "kind": "bool", "value": on}


def ask_again(label: str, value: str) -> dict:
    return {"name": "ask_again", "label": label, "kind": "text", "value": value}


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", [pin_pad("Show PIN pad", True), ask_again("Ask again after inactivity", "10 min")]),
        ("es", [pin_pad("Mostrar pinpad", True), ask_again("Volver a preguntar tras inactividad", "10 min")]),
    ],
)
def test_asking_again_after_some_minutes_says_the_pin_pad_and_its_minutes_as_settings_does(language, expected):
    """hub#2201: «Pedir el PIN: Siempre, y otra vez tras un rato sin usar» named an option Settings does not have and
    hid the minutes. The card says the two controls of Settings › General it sets."""
    assert fields({"pin_policy": "always", "pin_inactivity_minutes": 10}, language) == expected


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", [pin_pad("Show PIN pad", True), ask_again("Ask again after inactivity", "Until signing out")]),
        ("es", [pin_pad("Mostrar pinpad", True), ask_again("Volver a preguntar tras inactividad", "Hasta cerrar sesión")]),
    ],
)
def test_once_per_shift_is_until_signing_out_as_settings_calls_it(language, expected):
    AccessSettings.objects.create(pin_policy="never")
    assert fields({"pin_policy": "per_shift"}, language) == expected


@pytest.mark.parametrize(("language", "label"), [("en", "Show PIN pad"), ("es", "Mostrar pinpad")])
def test_never_asking_turns_the_pin_pad_off(language, label):
    assert fields({"pin_policy": "never", "pin_inactivity_minutes": 5}, language) == [pin_pad(label, False)]


@pytest.mark.parametrize(
    ("language", "label", "value"), [("en", "PIN digits", "6 digits"), ("es", "Dígitos del PIN", "6 dígitos")]
)
def test_the_digits_are_said_as_settings_offers_them(language, label, value):
    assert fields({"pin_length": 6}, language) == [
        {"name": "pin_length", "label": label, "kind": "text", "value": value}
    ]


@pytest.mark.parametrize(
    ("policy", "value"), [("always", "Volver a preguntar tras inactividad: 15 min"), ("per_shift", None)]
)
def test_minutes_alone_say_what_settings_will_show_after_the_change(policy, value):
    """The minutes count only when it asks again after inactivity: sent alone to a business that asks until signing
    out, Settings will still say «Hasta cerrar sesión», and so does the card."""
    AccessSettings.objects.create(pin_policy=policy, pin_inactivity_minutes=5)
    [line] = fields({"pin_inactivity_minutes": 15}, "es")
    assert f"{line['label']}: {line['value']}" == (value or "Volver a preguntar tras inactividad: Hasta cerrar sesión")


@pytest.mark.parametrize("language", ["en", "es"])
def test_the_cards_words_are_the_ones_of_the_pin_pad_card_of_settings(language):
    """The card names each control as the screen does (``base.pinPolicy`` of base's catalogue), in each language."""
    catalogue = json.loads((Path(settings.BASE_DIR) / f"base/frontend/locale/{language}.json").read_text())
    screen = catalogue["base"]["pinPolicy"]
    with translation.override(language):
        said = {
            "show": str(profile.SHOW_PIN_PAD),
            "again": str(profile.ASK_AGAIN),
            "untilSignOut": str(profile.UNTIL_SIGNING_OUT),
            "minutes": str(profile.MINUTES) % {"n": "{n}"},
            "six": str(profile.DIGITS) % {"n": 6},
            "digits": str(profile.PIN_DIGITS),
        }
    assert said == {key: screen[key] for key in said}


def test_asking_again_after_inactivity_without_its_minutes_is_refused_before_any_card():
    """The assistant never makes the minutes up, nor do the stored ones apply unseen: the model hears which datum is
    missing and asks the person, as Settings offers no «after inactivity» without its minutes."""
    op = get(UPDATE)
    refused = shared.invalid_arguments(op, {"pin_policy": "always"})
    assert (refused.outcome, refused.code) == ("error", "invalid_payload")
    assert set(json.loads(refused.content)["error"]["fields"]) == {"pin_inactivity_minutes"}
    assert shared.invalid_arguments(op, {"pin_policy": "always", "pin_inactivity_minutes": 10}) is None
    assert shared.invalid_arguments(op, {"pin_policy": "per_shift"}) is None
    assert shared.invalid_arguments(op, {"pin_inactivity_minutes": 10}) is None
