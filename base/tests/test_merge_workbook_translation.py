"""The merge driver resolves only WORKBOOK.en.md's generated source hash."""

import shlex
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

from base import catalog
from base.management.commands import merge_workbook_translation

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DRIVER_NAME = "workbook-translation"
BASE_SPANISH = """\
## Uno

Original uno.

## Dos

Original dos.

## Para quien lo mantiene
"""
BASE_ENGLISH = """\
## One

Original one.

## Two

Original two.
"""


def git(repository: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=repository,
        check=check,
        text=True,
        capture_output=True,
    )


def write_documents(repository: Path, spanish: str, english: str) -> None:
    source = catalog.user_part(spanish)
    header = catalog.en_header(catalog.source_hash(source))
    (repository / catalog.WORKBOOK).write_text(spanish, encoding="utf-8")
    (repository / catalog.WORKBOOK_EN).write_text(
        f"{header}\n\n{english}", encoding="utf-8"
    )


def commit_documents(repository: Path, message: str, spanish: str, english: str) -> None:
    write_documents(repository, spanish, english)
    git(repository, "add", catalog.WORKBOOK, catalog.WORKBOOK_EN)
    git(repository, "commit", "-qm", message)


#: How the README's driver reads from a checkout of this repository (``manage.py`` at its root).
README_RUN = "uv run --no-sync python manage.py"


def driver_from(manage: Path, command: str = "merge_workbook_translation") -> str:
    """The README's driver, run from ``manage``'s project for a repository elsewhere; ``command`` stands for an older
    branch, whose ``manage.py`` has no such command."""
    driver = merge_workbook_translation.DRIVER
    assert driver.count(f"{README_RUN} merge_workbook_translation ") == 1
    run = f"uv run --no-sync --project {shlex.quote(str(manage.parent))} python {shlex.quote(str(manage))}"
    return driver.replace(f"{README_RUN} merge_workbook_translation ", f"{run} {command} ")


def repository(tmp_path: Path, driver: str | None = None) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "Merge test")
    git(root, "config", "user.email", "merge@example.invalid")
    attributes = PROJECT_ROOT / ".gitattributes"
    if attributes.exists():
        shutil.copy(attributes, root / ".gitattributes")
    git(root, "config", f"merge.{DRIVER_NAME}.driver", driver or driver_from(PROJECT_ROOT / "manage.py"))
    commit_documents(root, "base", BASE_SPANISH, BASE_ENGLISH)
    return root


def translation_state(repository: Path) -> str:
    config = SimpleNamespace(path=str(repository), label="things")
    return catalog.workbook_translation(config).state


def test_two_branches_merge_when_only_the_translation_hash_conflicts(tmp_path):
    root = repository(tmp_path)
    git(root, "checkout", "-qb", "branch-b")
    commit_documents(
        root,
        "branch B",
        BASE_SPANISH.replace("Original dos.", "Cambio B."),
        BASE_ENGLISH.replace("Original two.", "Change B."),
    )
    git(root, "checkout", "-q", "main")
    commit_documents(
        root,
        "branch A",
        BASE_SPANISH.replace("Original uno.", "Cambio A."),
        BASE_ENGLISH.replace("Original one.", "Change A."),
    )
    git(root, "checkout", "-q", "branch-b")

    merged = git(root, "merge", "main", check=False)

    assert merged.returncode == 0, merged.stdout + merged.stderr
    assert git(root, "diff", "--name-only", "--diff-filter=U").stdout == ""
    spanish = (root / catalog.WORKBOOK).read_text(encoding="utf-8")
    english = (root / catalog.WORKBOOK_EN).read_text(encoding="utf-8")
    assert "Cambio A." in spanish and "Cambio B." in spanish
    assert "Change A." in english and "Change B." in english
    assert translation_state(root) == "current"

    (root / catalog.WORKBOOK).write_text(
        spanish.replace("Cambio B.", "Otro cambio sin traducir."), encoding="utf-8"
    )
    assert translation_state(root) == "stale"


def merge_conflicting_translation(root: Path, branch_a: str, branch_b: str) -> str:
    git(root, "checkout", "-qb", "branch-b")
    commit_documents(
        root,
        "branch B",
        BASE_SPANISH.replace("Original dos.", "Cambio B."),
        branch_b,
    )
    git(root, "checkout", "-q", "main")
    commit_documents(
        root,
        "branch A",
        BASE_SPANISH.replace("Original uno.", "Cambio A."),
        branch_a,
    )
    git(root, "checkout", "-q", "branch-b")

    merged = git(root, "merge", "main", check=False)

    assert merged.returncode != 0
    assert git(root, "diff", "--name-only", "--diff-filter=U").stdout.splitlines() == [
        catalog.WORKBOOK_EN
    ]
    return (root / catalog.WORKBOOK_EN).read_text(encoding="utf-8")


def test_a_real_translation_body_conflict_is_not_hidden(tmp_path):
    root = repository(tmp_path)

    english = merge_conflicting_translation(
        root,
        BASE_ENGLISH.replace("Original two.", "Shared change A."),
        BASE_ENGLISH.replace("Original two.", "Shared change B."),
    )

    assert "<<<<<<<" in english and "=======" in english and ">>>>>>>" in english
    assert "Shared change A." in english and "Shared change B." in english


def test_multiple_real_translation_body_conflicts_keep_all_markers(tmp_path):
    root = repository(tmp_path)
    filler = "\n\n".join(f"Paragraph {n}." for n in range(20))
    spaced_english = BASE_ENGLISH.replace("\n## Two\n", f"\n\n{filler}\n\n## Two\n")
    commit_documents(root, "space sections", BASE_SPANISH, spaced_english)

    english = merge_conflicting_translation(
        root,
        spaced_english.replace("Original one.", "Shared first A.").replace(
            "Original two.", "Shared second A."
        ),
        spaced_english.replace("Original one.", "Shared first B.").replace(
            "Original two.", "Shared second B."
        ),
    )

    # git's own markers, the header's among them (git joins it with the near first section's): once the body is
    # resolved, the stale check asks for its new hash.
    assert english.startswith("<<<<<<< ours\n<!-- generated from WORKBOOK.md sha256:")
    assert english.count("<<<<<<<") == english.count("=======") == english.count(">>>>>>>") == 2
    for text in ("Shared first A.", "Shared first B.", "Shared second A.", "Shared second B."):
        assert text in english
    assert translation_state(root) == "stale"


def test_the_readme_activates_the_driver_with_git_s_own_merge_behind_it():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    assert f"merge.{DRIVER_NAME}.driver" in readme
    assert shlex.quote(merge_workbook_translation.DRIVER) in readme
    assert merge_workbook_translation.DRIVER.endswith("|| git merge-file -L ours -L base -L theirs %A %O %B")


def test_a_branch_without_the_command_keeps_both_translations_in_git_s_markers(tmp_path):
    """The config is per clone: a branch from before the command (its ``manage.py`` has none) merges as git would, with
    both sides' text in its markers, never only its own copy."""
    root = repository(tmp_path, driver_from(PROJECT_ROOT / "manage.py", command="no_such_command"))

    english = merge_conflicting_translation(
        root,
        BASE_ENGLISH.replace("Original one.", "Change A."),
        BASE_ENGLISH.replace("Original two.", "Change B."),
    )

    assert "<<<<<<<" in english and ">>>>>>>" in english
    assert "Change A." in english and "Change B." in english


def test_a_conflicting_spanish_source_leaves_its_translation_in_markers_too(tmp_path):
    root = repository(tmp_path)
    git(root, "checkout", "-qb", "branch-b")
    commit_documents(
        root,
        "branch B",
        BASE_SPANISH.replace("Original dos.", "Cambio B."),
        BASE_ENGLISH.replace("Original two.", "Change B."),
    )
    git(root, "checkout", "-q", "main")
    commit_documents(
        root,
        "branch A",
        BASE_SPANISH.replace("Original dos.", "Cambio A."),
        BASE_ENGLISH.replace("Original two.", "Change A."),
    )
    git(root, "checkout", "-q", "branch-b")

    merged = git(root, "merge", "main", check=False)

    assert merged.returncode != 0
    assert sorted(git(root, "diff", "--name-only", "--diff-filter=U").stdout.splitlines()) == sorted(
        [catalog.WORKBOOK, catalog.WORKBOOK_EN]
    )
    english = (root / catalog.WORKBOOK_EN).read_text(encoding="utf-8")
    assert "<<<<<<<" in english and "Change A." in english and "Change B." in english
