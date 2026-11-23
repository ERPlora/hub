"""The screens the assistant is told VeriFactu shows each thing on, by the path of its menu entry: the turn's links name
each screen by that path, in the person's language. Asked where to read the responsible declaration, the model sent
the owner to «VeriFactu › Configuration», for the read that gives it was told to be «VeriFactu's configuration», and
answered «I haven't signed a declaration» as if it were the one who signs it; the declaration is on Settings, and
ERPlora signs it as the software's producer.
"""

import re

from django.apps import apps
from django.utils import translation
from live.assistant import description
from live.operations import get, registry

CONFIGURATION = "/verifactu/config"
SETTINGS = "/verifactu/settings"
A_SCREEN = re.compile(r"/verifactu/[a-z_]+")


def menu_paths() -> dict[str, object]:
    return {nav.path: nav.label for nav in apps.get_app_config("verifactu").navigation}


def said_on_each_screen(name: str) -> dict[str, str]:
    """What the description of ``name`` says of each screen it names: the sentence that names it, by its path."""
    sentences = re.split(r"(?<=\.)\s+", description(get(name)))
    return {path: sentence for sentence in sentences for path in A_SCREEN.findall(sentence)}


def test_the_configuration_read_puts_the_declaration_and_the_producer_on_settings():
    said = said_on_each_screen("verifactu.config.get")
    assert set(said) == {CONFIGURATION, SETTINGS}
    assert "responsible declaration" in said[SETTINGS] and "producer" in said[SETTINGS]
    assert "declaration" not in said[CONFIGURATION] and "producer" not in said[CONFIGURATION]


def test_the_configuration_read_puts_the_certificate_and_the_authorisation_on_configuration():
    said = said_on_each_screen("verifactu.config.get")
    assert "own certificate uploaded here" in said[CONFIGURATION] and "authorisation" in said[CONFIGURATION]
    assert "environment" in said[SETTINGS] and "route" in said[SETTINGS]
    assert "authorisation" not in said[SETTINGS] and "environment" not in said[CONFIGURATION]


def test_the_configuration_read_says_erplora_signs_the_declaration():
    said = said_on_each_screen("verifactu.config.get")[SETTINGS]
    assert "ERPlora signs" in said.partition("responsible declaration")[2]


def test_every_screen_a_verifactu_tool_names_is_one_of_its_menu():
    named = {
        path
        for op in registry.values()
        if op.app_label == "verifactu"
        for path in A_SCREEN.findall(description(op))
    }
    assert named and named <= set(menu_paths())


def test_the_screen_of_the_declaration_is_settings_in_english_and_ajustes_in_spanish():
    label = menu_paths()[SETTINGS]
    with translation.override("en"):
        english = str(label)
    with translation.override("es"):
        spanish = str(label)
    assert (english, spanish) == ("Settings", "Ajustes")
