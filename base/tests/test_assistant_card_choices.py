"""A value of a closed list on the card of a normal write, across the platform (BASE-F97): «Claro», «50 m» or «En sala»
says which option was chosen, never which datum it is, so the card's line names it even when it goes first. Asked for
one thing, the cards read «Cambiar en Mi perfil: 90%», «Cambiar en Control horario: 50 m» or «Cambiar en Cocina:
Campanilla»."""

import pytest
from live.assistant import CHOICE, resolved
from live.assistant.tools import input_schema, risk
from live.operations import Operation, get

from base import assistant
from base.tenancy.tests.business import HUB_DB, in_business_a
from base.tests.card_values import ctx, writes

__all__ = ["in_business_a"]

pytestmark = HUB_DB


def drawn(op: Operation, name: str, value, language: str = "es") -> dict | None:
    """The datum ``name`` of the card of ``op`` asked only for it; ``None`` when its own summary says it in a sentence
    instead (the website's «Diseño: …»)."""
    fields = assistant.cards.card(op, {name: value}, language, ctx(language=language))["fields"]
    return next((field for field in fields if field["name"] == name), None)


def closed_lists() -> list[tuple[Operation, str, object]]:
    """Each closed list a normal write takes, with its first value that is not empty."""
    found = []
    for op in writes():
        if risk(op) != "normal":
            continue
        schema = input_schema(op)
        defs = schema.get("$defs", {})
        for name, prop in schema.get("properties", {}).items():
            enum = resolved(prop, defs).get("enum", ())
            value = next((one for one in enum if one not in ("", None) and not isinstance(one, bool)), None)
            if value is not None:
                found.append((op, name, value))
    return found


def test_every_closed_list_of_a_normal_write_is_said_as_a_choice():
    lists = closed_lists()
    shown = {f"{op.name}.{name}": drawn(op, name, value) for op, name, value in lists}
    unmarked = [key for key, datum in shown.items() if datum is not None and datum.get(CHOICE) is not True]
    assert unmarked == []
    assert len([key for key, datum in shown.items() if datum is not None]) > 50


@pytest.mark.parametrize(
    ("write", "name", "value", "language", "said"),
    [
        ("base.profile.preferences_set", "ui_scale", 110, "es", ("Tamaño de la interfaz", "110%")),
        ("base.profile.preferences_set", "theme_mode", "light", "es", ("Apariencia", "Claro")),
        ("base.profile.preferences_set", "palette", "ocean", "es", ("Paleta", "Océano")),
        ("base.profile.preferences_set", "language", "en", "es", ("Idioma", "English")),
        ("base.profile.preferences_set", "theme_mode", "light", "en", ("Appearance", "Light")),
        ("attendance.settings.update", "geofence_radius_m", 50, "es", ("Radio permitido (m)", "50 m")),
        ("kitchen.settings.update", "sound_tone", "chime", "es", ("Tono del sonido", "Campanilla")),
        ("sale.settings.update", "default_document_type", "ticket", "es", ("Documento por defecto", "Tique")),
    ],
)
def test_the_one_closed_list_asked_is_said_by_its_label_and_marked_a_choice(write, name, value, language, said):
    shown = drawn(get(write), name, value, language)
    assert ((shown["label"], shown["value"]), shown["kind"], shown.get(CHOICE)) == (said, "text", True)


def test_what_the_write_is_about_is_no_choice():
    """A name and a figure keep their own words: only a closed list's value is marked."""
    assert drawn(get("service.service.create"), "name", "Corte").get(CHOICE) is None
    assert drawn(get("service.service.create"), "duration_minutes", 30).get(CHOICE) is None
