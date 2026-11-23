"""What the assistant is told about the year's numbering, so it answers what the Series screen says.

Asked «is this year's invoice numbering ready?» in a business with no series, the model answered «not yet» and offered
to create them: the read it called only counted the series and answered ``configured`` false. The series are born on
their own with the first sale, and one is created by hand only for another prefix or format, or to continue another
system's numbering, as the Series screen says when it has none.
"""

import json
from pathlib import Path

from django.apps import apps
from live import assistant as shared
from live.operations import get

LOCALE = Path(apps.get_app_config("invoice").path) / "frontend/locale"


def told() -> str:
    return shared.description(get("invoice.numbering.status"))


def series_screen_when_empty(language: str) -> str:
    return json.loads((LOCALE / f"{language}.json").read_text())["invoice"]["series"]["empty"]


def test_the_series_screen_says_they_are_born_with_the_first_sale_in_english_and_spanish():
    assert "created on their own with your first sale" in series_screen_when_empty("en")
    assert "Se crean solas con tu primera venta" in series_screen_when_empty("es")


def test_the_numbering_read_tells_the_model_the_series_are_born_with_the_first_sale():
    assert (
        "Nothing has to be done for the numbering to work: the series are created on their own with the first sale"
    ) in told()


def test_the_numbering_read_tells_the_model_when_a_series_is_created_by_hand():
    said = told()
    assert "by hand only to change the prefix or the format, or to continue another system's numbering" in said
    assert "/invoice/series" in said


def test_the_numbering_read_tells_the_model_configured_false_is_nothing_left_to_do():
    assert "so configured false does not mean something is left to do" in told()
