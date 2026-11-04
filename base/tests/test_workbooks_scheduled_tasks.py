"""No WORKBOOK tells that the scheduled tasks run on one fixed scope (hub#805, hub#626).

Since the tenancy's cut (hub#602) the worker enters each business it serves, in its own database and on its own scope
(``base.worker._serve_hub``), and ``settings.WORKER_SCOPE_SLUG`` only stays for ``base.scheduler.run_due`` without a
scope, which is the suite's tests written before the tenancy. Whoever maintains an app, or reviews it against its
WORKBOOK, starts from what the WORKBOOK says; both languages are read, with the text's line breaks undone.
"""

from pathlib import Path

import pytest
from django.conf import settings

#: The words that tell of the fixed scope, in the WORKBOOK's two languages.
FIXED_SCOPE = (
    "WORKER_SCOPE_SLUG",
    "ámbito fijo",
    "un solo ámbito",
    "sobre un solo hub",
    "fixed scope",
    "over a single hub",
)
#: Flows says what the setting stays for: the tests written before the tenancy, and only them.
SAYS_WHAT_IT_STAYS_FOR = {"apps/flow/WORKBOOK.md"}


def workbooks() -> list[str]:
    root = Path(settings.BASE_DIR)
    found = [*root.glob("apps/*/WORKBOOK*.md"), *root.glob("base/WORKBOOK*.md")]
    return sorted(str(path.relative_to(root)) for path in found)


def fixed_scope_words(text: str) -> list[str]:
    unwrapped = " ".join(text.split())
    return [words for words in FIXED_SCOPE if words in unwrapped]


def test_the_words_are_found_across_a_line_break():
    assert fixed_scope_words("la corre en el ámbito\n  fijo de la fase 1") == ["ámbito fijo"]


def test_every_app_and_language_is_read():
    read = workbooks()
    assert {"apps/reservation/WORKBOOK.md", "apps/reservation/WORKBOOK.en.md", "base/WORKBOOK.md"} <= set(read)


@pytest.mark.parametrize("workbook", sorted(set(workbooks()) - SAYS_WHAT_IT_STAYS_FOR))
def test_no_workbook_tells_of_a_fixed_scope(workbook):
    text = (Path(settings.BASE_DIR) / workbook).read_text(encoding="utf-8")
    assert fixed_scope_words(text) == []
