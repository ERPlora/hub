"""The tests that may lean on the suite's fallback only get fewer.

``.legacy-fallback-allow`` names them (``base/tenancy/tests/legacy_allow.py``): it never gains a line compared with the
list where the branch left origin/main, and a line whose test is gone leaves it. A listed test that runs every case
without leaning on the fallback is caught by the run itself, which fails naming its line.
"""

import functools
import re
from pathlib import Path

import pytest
from allow_list_base import REPO, file_at_base

from base.tenancy.tests.legacy_allow import ALLOW_FILE, parse_allow


def gained(entries: set[str], base_entries: set[str]) -> list[str]:
    """Lines the list has and the base list did not."""
    return [
        f"{entry}: new in {ALLOW_FILE}; the list only shrinks, so make the test run as production does"
        for entry in sorted(entries - base_entries)
    ]


def gone(entries: set[str], repo: Path) -> list[str]:
    """Lines whose file is gone, or no longer says the names of their test."""

    @functools.cache
    def text_of(path: str) -> str | None:
        file = repo / path
        return file.read_text(encoding="utf-8") if file.is_file() else None

    found = []
    for entry in sorted(entries):
        path, *names = entry.split("::")
        text = text_of(path)
        if text is None or not all(re.search(rf"\b{name}\b", text) for name in names):
            found.append(f"{entry}: no such test any more; remove its line from {ALLOW_FILE}")
    return found


def entries_in(text: str) -> set[str]:
    entries, errors = parse_allow(text)
    assert not errors, "\n".join(errors)
    return entries


def current_entries() -> set[str]:
    allow = REPO / ALLOW_FILE
    return entries_in(allow.read_text(encoding="utf-8") if allow.is_file() else "")


def test_the_list_never_gains_a_line():
    base = file_at_base(ALLOW_FILE)
    if base is None:
        pytest.skip(f"the comparison point has no {ALLOW_FILE} yet: this is the commit that brings it")
    found = gained(current_entries(), entries_in(base))
    assert not found, "The tests that lean on the suite's fallback only get fewer:\n" + "\n".join(found)


def test_every_line_names_a_test_that_still_exists():
    found = gone(current_entries(), REPO)
    assert not found, f"Lines of {ALLOW_FILE} that have to go:\n" + "\n".join(found)


def test_the_list_may_lose_lines_but_never_gain_one():
    before = {"base/tests/test_a.py::test_one", "base/tests/test_a.py::test_two"}

    assert gained({"base/tests/test_a.py::test_one"}, before) == []
    assert gained({*before, "base/tests/test_b.py::test_new"}, before) == [
        f"base/tests/test_b.py::test_new: new in {ALLOW_FILE}; "
        "the list only shrinks, so make the test run as production does"
    ]


def test_a_line_whose_file_or_test_is_gone_has_to_leave(tmp_path):
    tests = tmp_path / "base" / "tests"
    tests.mkdir(parents=True)
    (tests / "test_a.py").write_text(
        "from base.tests.shared import test_imported\n\n\ndef test_one():\n    pass\n\n\nclass TestTwo:\n"
        "    def test_two(self):\n        pass\n"
    )
    entries = {
        "base/tests/test_a.py::test_one",
        "base/tests/test_a.py::TestTwo::test_two",
        "base/tests/test_a.py::test_imported",
        "base/tests/test_a.py::test_on",
        "base/tests/test_a.py::TestGone::test_two",
        "base/tests/test_gone.py::test_one",
    }

    assert gone(entries, tmp_path) == [
        f"base/tests/test_a.py::TestGone::test_two: no such test any more; remove its line from {ALLOW_FILE}",
        f"base/tests/test_a.py::test_on: no such test any more; remove its line from {ALLOW_FILE}",
        f"base/tests/test_gone.py::test_one: no such test any more; remove its line from {ALLOW_FILE}",
    ]
