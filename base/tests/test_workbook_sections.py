"""A WORKBOOK cut at its headings and the mark its translation keeps of each Spanish section."""

import hashlib

import pytest

from base.tests.apps_on_disk import NOT_CLOSING
from base.workbook_sections import behind, current_body, mark, marked, prose_lines, sections

SOURCE = """\
## Para qué sirve

Guarda cosas.

```text
## No es un título
```

## Flujos

### THINGS-F01 Crear una cosa
Estado: hecho
"""
BODY = """\
## What it is for

Keeps things.

```text
## No es un título
```

## Flows

### THINGS-F01 Create a thing
Status: done
"""
PURPOSE = "## Para qué sirve\n\nGuarda cosas.\n\n```text\n## No es un título\n```\n\n"
FLOWS = "## Flujos\n\n"
CREATE = "### THINGS-F01 Crear una cosa\nEstado: hecho\n"


def hash_of(section: str) -> str:
    return hashlib.sha256(section.strip().encode()).hexdigest()[:12]


def test_it_is_cut_at_every_heading_outside_the_code_blocks_and_nothing_is_lost():
    assert sections(SOURCE) == [PURPOSE, FLOWS, CREATE]


def test_what_goes_before_the_first_heading_is_a_section_of_its_own():
    assert sections(f"Primero.\n\n{FLOWS}") == ["Primero.\n\n", FLOWS]
    assert sections("") == []


def test_the_mark_is_the_hash_of_its_section_whatever_blank_lines_end_it():
    assert mark(CREATE) == f"<!-- from WORKBOOK.md sha256:{hash_of(CREATE)} -->"
    assert mark(f"{CREATE}\n\n") == mark(CREATE) == mark(CREATE.rstrip("\n"))
    assert mark(CREATE.replace("hecho", "parcial")) != mark(CREATE)


def test_a_translation_carries_under_each_heading_the_mark_of_its_section():
    assert marked(SOURCE, BODY) == (
        BODY.replace("## What it is for\n", f"## What it is for\n{mark(PURPOSE)}\n")
        .replace("## Flows\n", f"## Flows\n{mark(FLOWS)}\n")
        .replace("### THINGS-F01 Create a thing\n", f"### THINGS-F01 Create a thing\n{mark(CREATE)}\n")
    )


@pytest.mark.parametrize(
    "other",
    [
        BODY.replace("## Flows\n", "Flows\n"),
        BODY.replace("## Flows\n", "## Flows\n\n### More\n"),
        BODY.replace("## Flows\n", "### Flows\n"),
        f"Before.\n\n{BODY.replace('## Flows', 'Flows')}",
    ],
    ids=["one-fewer", "one-more", "another-level", "a-text-before-for-a-heading-less"],
)
def test_a_translation_with_other_headings_cannot_be_marked(other):
    assert marked(SOURCE, other) is None


def test_a_current_translation_is_read_without_its_marks_byte_for_byte():
    assert current_body(SOURCE, marked(SOURCE, BODY)) == BODY


@pytest.mark.parametrize(
    "changed",
    [
        SOURCE.replace("Guarda cosas.", "Guarda cosas y personas."),
        SOURCE.replace("No es un título", "Tampoco lo es"),
        SOURCE.replace("Crear una cosa", "Crear cosas"),
        SOURCE.replace("## Flujos", "## Flujos\n\n### THINGS-F02 Borrar una cosa"),
        SOURCE.replace(CREATE, ""),
        f"{CREATE}\n{PURPOSE}{FLOWS}",
    ],
    ids=["its-text", "its-code-block", "its-heading", "a-section-added", "a-section-removed", "another-order"],
)
def test_a_translation_is_behind_as_soon_as_a_section_of_the_source_is_another(changed):
    assert current_body(changed, marked(SOURCE, BODY)) is None


def swapped(text: str) -> str:
    first, second = mark(PURPOSE), mark(FLOWS)
    return text.replace(first, "FIRST").replace(second, first).replace("FIRST", second)


@pytest.mark.parametrize(
    "text",
    [
        BODY,
        f"<!-- generated from WORKBOOK.md sha256:{'0' * 64} -->\n\n{BODY}",
        marked(SOURCE, BODY).replace(f"{mark(FLOWS)}\n", ""),
        marked(SOURCE, BODY).replace(f"{mark(FLOWS)}\n\n", f"\n{mark(FLOWS)}\n"),
        swapped(marked(SOURCE, BODY)),
        marked(SOURCE, BODY).replace("Status: done", "Status: done\n\n## More"),
        "",
    ],
    ids=["no-marks", "the-whole-file-s", "one-missing", "one-line-below", "swapped", "one-heading-more", "empty"],
)
def test_a_translation_without_each_mark_under_its_heading_is_not_current(text):
    assert current_body(SOURCE, text) is None


def test_only_the_sections_whose_mark_is_missing_are_behind_each_with_the_mark_to_write():
    changed = SOURCE.replace("Guarda cosas.", "Guarda cosas y personas.").replace(
        CREATE, f"{CREATE}\n### THINGS-F02 Borrar una cosa\nEstado: hecho\n"
    )
    purpose = PURPOSE.replace("Guarda cosas.", "Guarda cosas y personas.")
    delete = "### THINGS-F02 Borrar una cosa\nEstado: hecho\n"

    assert behind(changed, marked(SOURCE, BODY)) == [
        f"## Para qué sirve → {mark(purpose)}",
        f"### THINGS-F02 Borrar una cosa → {mark(delete)}",
    ]
    assert behind(SOURCE, marked(SOURCE, BODY)) == []


@pytest.mark.parametrize(("fence", "inner"), NOT_CLOSING.values(), ids=NOT_CLOSING)
def test_the_prose_lines_are_the_numbered_ones_outside_the_fenced_code_blocks(fence, inner):
    """What ``translate_workbooks --check`` reads for a Spanish date: an unclosed block runs to the end."""
    text = f"Before.\n{fence}\n{inner}\nDD/MM/AAAA\n{fence}\nAfter.\n~~~\nDD/MM/AAAA"
    assert list(prose_lines(text)) == [(1, "Before."), (6, "After.")]
