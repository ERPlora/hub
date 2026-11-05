"""No manual of an app tells that the scheduled tasks run on one fixed scope (hub#805, hub#626).

Since the tenancy's cut (hub#602) the worker enters each business it serves, in its own database and on its own scope
(``base.worker._serve_hub``), and ``settings.WORKER_SCOPE_SLUG`` only stays for ``base.scheduler.run_due`` without a
scope, which is the suite's tests written before the tenancy. Whoever maintains an app, or reviews it against its
WORKBOOK, starts from what its WORKBOOK and its README say; both languages are read, whatever the case, with the text's
line breaks undone.
"""

from pathlib import Path

import pytest
from django.conf import settings

#: The words that tell of the fixed scope, in the two languages of the manuals.
FIXED_SCOPE = (
    "WORKER_SCOPE_SLUG",
    "ámbito fijo",
    "un solo ámbito",
    "sobre un solo hub",
    "sobre el ámbito del worker",
    "único negocio fijo",
    "fixed scope",
    "over a single hub",
)
#: Flows says what the setting stays for: the tests written before the tenancy, and only them.
SAYS_WHAT_IT_STAYS_FOR = {"apps/flow/WORKBOOK.md"}


def manuals() -> list[str]:
    root = Path(settings.BASE_DIR)
    found = [path for name in ("WORKBOOK*.md", "README*.md") for path in (*root.glob(f"apps/*/{name}"), *root.glob(f"base/{name}"))]
    return sorted(str(path.relative_to(root)) for path in found)


def fixed_scope_words(text: str) -> list[str]:
    unwrapped = " ".join(text.split()).casefold()
    return [words for words in FIXED_SCOPE if words.casefold() in unwrapped]


def test_the_words_are_found_across_a_line_break():
    assert fixed_scope_words("la corre en el ámbito\n  fijo de la fase 1") == ["ámbito fijo"]


def test_the_words_are_found_whatever_their_case():
    assert fixed_scope_words("Ámbito fijo de la fase 1") == ["ámbito fijo"]
    assert fixed_scope_words("Fixed scope in phase 1") == ["fixed scope"]
    assert fixed_scope_words("WORKER_SCOPE_SLUG") == ["WORKER_SCOPE_SLUG"]


def test_the_words_of_the_issue_are_found():
    assert fixed_scope_words("corren en un único negocio fijo") == ["único negocio fijo"]


def test_every_app_and_language_is_read():
    read = manuals()
    assert {"apps/reservation/WORKBOOK.md", "apps/reservation/WORKBOOK.en.md", "base/WORKBOOK.md"} <= set(read)


def test_the_readme_of_each_app_is_read_too():
    assert {"apps/reservation/README.md", "apps/cart_checkout/README.md"} <= set(manuals())


@pytest.mark.parametrize("manual", sorted(set(manuals()) - SAYS_WHAT_IT_STAYS_FOR))
def test_no_manual_tells_of_a_fixed_scope(manual):
    text = (Path(settings.BASE_DIR) / manual).read_text(encoding="utf-8")
    assert fixed_scope_words(text) == []
