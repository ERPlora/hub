"""Code is read by people who have never seen the project's planning documents.

Comments, docstrings, test names and messages have to make sense on their own, so the code never points at a plan
section, a dated planning round or a delivery slice. Markdown files are left out: they are where the plans live.
"""

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

# Built from its code point so that this file does not trip its own scan.
SECTION_SIGN = "\N{SECTION SIGN}"

INTERNAL_REFERENCE = re.compile(
    "|".join(
        (
            SECTION_SIGN + r" ?[0-9]",
            r"(Plan|PLAN)(-[A-Z]+)?(\.md)? ?" + SECTION_SIGN,
            r"[Rr](onda|ound) [0-9]{4}-[0-9]{2}",
            r"[Tt]ajada S?[0-9]",
        )
    )
)

CODE_SUFFIXES = frozenset(
    {
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".mjs",
        ".cjs",
        ".vue",
        ".sh",
        ".css",
        ".scss",
        ".html",
        ".toml",
        ".yml",
        ".yaml",
        ".sql",
        ".ini",
        # The comments a patch adds end up in the installed dependency, read like any other code.
        ".patch",
    }
)


def is_code(path: str) -> bool:
    return Path(path).suffix in CODE_SUFFIXES or Path(path).name.startswith("Dockerfile")


def code_files() -> list[str]:
    """Tracked files plus new ones not ignored, so a reference is caught before its first commit.

    The submodules of ``packages/`` are listed as one entry each and are not files: their own repos scan them.
    """
    listing = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=REPO,
        check=True,
        capture_output=True,
    ).stdout
    paths = sorted({path for path in listing.decode().split("\0") if path})
    return [path for path in paths if is_code(path) and (REPO / path).is_file()]


def internal_references(paths, root: Path = REPO) -> list[str]:
    found = []
    for path in paths:
        text = (root / path).read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), 1):
            if INTERNAL_REFERENCE.search(line):
                found.append(f"{path}:{number}: {line.strip()}")
    return found


def test_code_never_points_at_internal_plans():
    paths = code_files()
    expected = {"tests/test_no_internal_references.py", "Dockerfile", "patches/@ionic__vue@8.8.9.patch"}
    assert expected <= set(paths), "git ls-files listed no code"
    found = internal_references(paths)
    assert not found, "Code that points at internal plans, rounds or slices:\n" + "\n".join(found)


@pytest.mark.parametrize(
    "path",
    [
        "Dockerfile",
        "docker/Dockerfile.dev",
        "base/services.py",
        "base/frontend/pages/FilesPage.vue",
        "tests/e2e/helpers.ts",
        "frontend/widget.tsx",
        "eslint.config.mjs",
        "babel.config.cjs",
        "docker/entrypoint.sh",
        "frontend/theme.scss",
        "pyproject.toml",
        ".github/workflows/deploy.yml",
        "base/templates/base/receipt.html",
        "pytest.ini",
        "patches/@ionic__vue@8.8.9.patch",
    ],
)
def test_every_kind_of_code_file_is_scanned(path):
    assert is_code(path)


@pytest.mark.parametrize("path", ["README.md", "base/WORKBOOK.md", "base/locale/es/LC_MESSAGES/django.po", "uv.lock"])
def test_documents_and_data_are_left_out(path):
    assert not is_code(path)


@pytest.mark.parametrize(
    "text",
    [
        "Voice and video calls (Plan " + SECTION_SIGN + "66)",
        "see PLAN-HUB " + SECTION_SIGN + "84",
        "PLAN.md" + SECTION_SIGN + "5",
        "the limits of " + SECTION_SIGN + "14.2",
        "register_apps --check (round 16, spec " + SECTION_SIGN + "4.3)",
        "The website's theme (round " + "2026-10-22)",
        "ronda " + "2026-11-10f",
        "tajada " + "S3",
        "Tajada " + "4",
    ],
)
def test_the_scan_catches_each_kind_of_reference(text):
    assert INTERNAL_REFERENCE.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "total = round(amount, 2)",
        "Plan the refund before the payment",
        "Section 5 of the AEAT schema",
        "the second round 2 of retries",
        "fixed by hub#781",
    ],
)
def test_the_scan_leaves_ordinary_text_alone(text):
    assert not INTERNAL_REFERENCE.search(text)


def test_a_patch_comment_that_points_at_a_plan_is_caught(tmp_path):
    patch = "patches/@scope__package@1.0.0.patch"
    (tmp_path / "patches").mkdir()
    comment = "+         * ERPlora patch: the queue of PLAN-HUB " + SECTION_SIGN + "84."
    (tmp_path / patch).write_text("+        /**\n" + comment + "\n+         */\n", encoding="utf-8")
    assert is_code(patch)
    assert internal_references([patch], root=tmp_path) == [f"{patch}:2: {comment}"]


def test_each_reference_is_named_by_file_and_line(tmp_path):
    (tmp_path / "clean.py").write_text("total = round(amount, 2)\n", encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("FROM python\n# see PLAN " + SECTION_SIGN + "3\n", encoding="utf-8")
    assert internal_references(["clean.py", "Dockerfile"], root=tmp_path) == [
        "Dockerfile:2: # see PLAN " + SECTION_SIGN + "3"
    ]
