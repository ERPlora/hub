"""The labels of the closed lists the website keeps inside its JSON (hub#679): the palette and the background of the
theme, what the catalog shows and the days of the opening hours. No field of the models holds them, so the app declares
them (``LiveAppConfig.choices``) and the assistant's card says each value by them: the word the editor shows, in English
and in Spanish, never the code it sends.
"""

import json
from pathlib import Path

import pytest
from django.apps import apps
from django.conf import settings
from django.utils import translation

from apps.website.choices import CHOICES, DAY_LABELS, SECTION_LABELS
from apps.website.schemas import CATALOG_SOURCES, DAYS, MODES, PALETTE_IDS

#: The editor's own words, by language.
EDITOR = {
    language: json.loads((Path(settings.BASE_DIR) / f"apps/website/frontend/locale/{language}.json").read_text())[
        "website"
    ]
    for language in ("en", "es")
}


def editor_words(language: str) -> dict[str, dict[str, str]]:
    """What the editor calls each value of each closed list, in ``language``."""
    words = EDITOR[language]
    return {
        "palette": {palette: words["palette"][palette] for palette in PALETTE_IDS},
        "mode": {mode: words["colours"][mode] for mode in MODES},
        "source": {"inventory": words["fields"]["sourceInventory"], "service": words["fields"]["sourceService"]},
        "day": dict(words["hours"]["days"]),
    }


def test_each_closed_list_of_the_site_is_declared_with_every_value_its_schema_takes():
    """A value the schema takes and the app does not label would reach the card as its code."""
    assert {name: [value for value, _ in labels] for name, labels in CHOICES.items()} == {
        "palette": list(PALETTE_IDS),
        "mode": list(MODES),
        "source": list(CATALOG_SOURCES),
        "day": list(DAYS),
    }


def test_the_app_declares_them_for_the_assistant():
    assert apps.get_app_config("website").choices == CHOICES


@pytest.mark.parametrize("language", ["en", "es"])
def test_each_value_is_said_with_the_word_the_editor_shows(language):
    with translation.override(language):
        said = {name: {value: str(label) for value, label in labels} for name, labels in CHOICES.items()}
    assert said == editor_words(language)


@pytest.mark.parametrize("language", ["en", "es"])
def test_each_section_is_said_with_the_word_the_editor_shows(language):
    with translation.override(language):
        said = {name: str(label) for name, label in SECTION_LABELS.items()}
    assert said == {name: EDITOR[language]["sections"][name] for name in SECTION_LABELS}


def test_the_public_page_says_the_days_with_the_same_labels():
    """One list of the days for the page and for the card."""
    from apps.website.render import _day_names

    with translation.override("es"):
        assert _day_names() == {day: str(label) for day, label in DAY_LABELS}
