"""The merge driver resolves only WORKBOOK.en.md's generated source hash."""

import shlex
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

from base import catalog

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


def repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "Merge test")
    git(root, "config", "user.email", "merge@example.invalid")
    attributes = PROJECT_ROOT / ".gitattributes"
    if attributes.exists():
        shutil.copy(attributes, root / ".gitattributes")
    manage = PROJECT_ROOT / "manage.py"
    driver = (
        f"uv run --no-sync --project {shlex.quote(str(PROJECT_ROOT))} "
        f"python {shlex.quote(str(manage))} merge_workbook_translation %O %A %B %P"
    )
    git(root, "config", f"merge.{DRIVER_NAME}.driver", driver)
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


def test_a_real_translation_body_conflict_is_not_hidden(tmp_path):
    root = repository(tmp_path)
    git(root, "checkout", "-qb", "branch-b")
    commit_documents(
        root,
        "branch B",
        BASE_SPANISH.replace("Original dos.", "Cambio B."),
        BASE_ENGLISH.replace("Original two.", "Shared change B."),
    )
    git(root, "checkout", "-q", "main")
    commit_documents(
        root,
        "branch A",
        BASE_SPANISH.replace("Original uno.", "Cambio A."),
        BASE_ENGLISH.replace("Original two.", "Shared change A."),
    )
    git(root, "checkout", "-q", "branch-b")

    merged = git(root, "merge", "main", check=False)

    assert merged.returncode != 0
    assert git(root, "diff", "--name-only", "--diff-filter=U").stdout.splitlines() == [
        catalog.WORKBOOK_EN
    ]
    english = (root / catalog.WORKBOOK_EN).read_text(encoding="utf-8")
    assert "<<<<<<<" in english and "=======" in english and ">>>>>>>" in english
    assert "Shared change A." in english and "Shared change B." in english
