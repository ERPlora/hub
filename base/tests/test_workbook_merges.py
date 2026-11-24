"""Two branches that change different sections of one WORKBOOK, each with its translation, merge with plain git: the merge
GitHub makes, which runs no merge driver of the repository."""

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from base.catalog import WORKBOOK, WORKBOOK_EN, user_part, workbook_translation
from base.tests.test_catalog import translated

SPANISH = """\
## Flujos

### THINGS-F01 Crear una cosa
Estado: hecho
Pasos:
1. Pulsa «+».

### THINGS-F02 Borrar una cosa
Estado: hecho
Pasos:
1. Pulsa «Borrar».

### THINGS-F03 Contar las cosas
Estado: hecho
Pasos:
1. Pulsa «Contar».

## Para quien lo mantiene
"""
ENGLISH = """\
## Flows

### THINGS-F01 Create a thing
Status: done
Steps:
1. Press "+".

### THINGS-F02 Delete a thing
Status: done
Steps:
1. Press "Delete".

### THINGS-F03 Count the things
Status: done
Steps:
1. Press "Count".
"""

Manual = tuple[str, str]
BASE: Manual = (SPANISH, ENGLISH)


def changed(*replacements: tuple[str, str], manual: Manual = BASE) -> Manual:
    """``manual`` with the first text of each pair replaced by the second, in Spanish and then in English."""
    texts = []
    for text, (before, after) in zip(manual, replacements, strict=True):
        assert text.count(before) == 1
        texts.append(text.replace(before, after))
    return texts[0], texts[1]


CREATE = changed(("1. Pulsa «+».", "1. Pulsa «Nueva»."), ('1. Press "+".', '1. Press "New".'))
DELETE = changed(("1. Pulsa «Borrar».", "1. Pulsa «Quitar»."), ('1. Press "Delete".', '1. Press "Remove".'))
COUNT_HEADING = changed(("F03 Contar las cosas", "F03 Hacer inventario"), ("F03 Count the things", "F03 Take stock"))
ADD = changed(
    ("### THINGS-F02", "### THINGS-F04 Copiar una cosa\nEstado: hecho\n\n### THINGS-F02"),
    ("### THINGS-F02", "### THINGS-F04 Copy a thing\nStatus: done\n\n### THINGS-F02"),
)
COUNT = SPANISH[SPANISH.index("### THINGS-F03") : SPANISH.index("## Para quien")]
WITHOUT_COUNT = (SPANISH.replace(COUNT, ""), ENGLISH[: ENGLISH.index("### THINGS-F03")])
#: The machine's configuration stays out: its hooks, its signing and its merge drivers.
ENVIRONMENT = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    command = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args]
    return subprocess.run(command, cwd=root, env=ENVIRONMENT, check=False, capture_output=True, text=True)


def write(root: Path, manual: Manual) -> None:
    spanish, english = manual
    (root / WORKBOOK).write_text(spanish, encoding="utf-8")
    (root / WORKBOOK_EN).write_text(translated(user_part(spanish), english), encoding="utf-8")


def commit(root: Path) -> None:
    assert git(root, "add", "-A").returncode == 0
    assert git(root, "commit", "-qm", "change").returncode == 0


def merge(root: Path, theirs: Manual, ours: Manual) -> subprocess.CompletedProcess:
    """What git answers when the branch that wrote ``ours`` merges into a main where ``theirs`` came in meanwhile."""
    git(root, "init", "-q", "-b", "main")
    write(root, BASE)
    commit(root)
    git(root, "checkout", "-qb", "branch")
    write(root, ours)
    commit(root)
    git(root, "checkout", "-q", "main")
    write(root, theirs)
    commit(root)
    return git(root, "merge", "branch")


def state(root: Path):
    return workbook_translation(SimpleNamespace(path=str(root), label="things"))


def lines_added(manual: Manual) -> set[str]:
    return set(manual[1].splitlines()) - set(ENGLISH.splitlines())


@pytest.mark.parametrize(
    ("theirs", "ours"),
    [(CREATE, DELETE), (DELETE, COUNT_HEADING), (CREATE, ADD), (CREATE, WITHOUT_COUNT)],
    ids=["two-sections", "the-next-heading", "a-section-added", "a-section-removed"],
)
def test_branches_that_change_different_sections_merge_and_the_translation_stays_current(tmp_path, theirs, ours):
    merged = merge(tmp_path, theirs, ours)

    assert merged.returncode == 0, merged.stdout
    english = state(tmp_path)
    assert english.state == "current"
    assert lines_added(theirs) | lines_added(ours) <= set(english.body.splitlines())
    assert ("Count" in english.body) is (ours is not WITHOUT_COUNT)


def test_a_section_one_of_the_branches_left_untranslated_is_behind_after_the_merge(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    write(tmp_path, BASE)
    commit(tmp_path)
    git(tmp_path, "checkout", "-qb", "branch")
    (tmp_path / WORKBOOK).write_text(CREATE[0], encoding="utf-8")
    commit(tmp_path)
    git(tmp_path, "checkout", "-q", "main")
    write(tmp_path, DELETE)
    commit(tmp_path)

    assert git(tmp_path, "merge", "branch").returncode == 0
    assert state(tmp_path).state == "stale"
