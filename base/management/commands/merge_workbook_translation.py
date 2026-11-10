"""Git merge driver for WORKBOOK.en.md: merge its body and refresh its source hash.

It writes the file only when the merge is clean. Anything else (a conflict in either text, a hash no committed
WORKBOOK.md has, a branch whose ``manage.py`` has no such command) fails, and the README's driver then runs git's own
three-way merge with its markers: never only one side's copy (hub#1082).
"""

import subprocess
import tempfile
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from base import catalog

_PLACEHOLDER = "0" * 64
#: What ``git config merge.workbook-translation.driver`` runs (README): this command, or git's own merge when it fails.
DRIVER = (
    "uv run --no-sync python manage.py merge_workbook_translation %O %A %B %P"
    " || git merge-file -L ours -L base -L theirs %A %O %B"
)


def _header(text: str, path: str):
    match = catalog._HEADER_RE.match(text)
    if match is None:
        raise CommandError(f"{path}: the translation has no valid source-hash header.")
    return match


def _git_text(*args: str) -> str:
    result = subprocess.run(["git", *args], text=True, capture_output=True, check=False)
    if result.returncode:
        raise CommandError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout


def _source_version(translation: str, translation_path: str, source_path: str) -> str:
    expected = _header(translation, translation_path).group(1)
    commits = _git_text("rev-list", "--all", "--", source_path).splitlines()
    for commit in commits:
        result = subprocess.run(
            ["git", "show", f"{commit}:{source_path}"], text=True, capture_output=True, check=False
        )
        if result.returncode:
            continue
        try:
            actual = catalog.source_hash(catalog.user_part(result.stdout))
        except catalog.WorkbookError:
            continue
        if actual == expected:
            return result.stdout
    raise CommandError(
        f"{translation_path}: no committed {source_path} matches its source hash; "
        "update the stale translation before merging."
    )


def _merge_file(directory: Path, name: str, texts: dict[str, str]):
    for version, text in texts.items():
        (directory / f"{name}-{version}").write_text(text, encoding="utf-8")
    return subprocess.run(
        [
            "git",
            "merge-file",
            "-p",
            str(directory / f"{name}-current"),
            str(directory / f"{name}-base"),
            str(directory / f"{name}-other"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )


class Command(BaseCommand):
    help = "Merge WORKBOOK.en.md without conflicting on its generated source hash."
    # A merge waits for it once per conflicting file: no system checks to run.
    requires_system_checks = ()

    def add_arguments(self, parser):
        for name in ("base", "current", "other", "path"):
            parser.add_argument(name)

    def handle(self, *args, base: str, current: str, other: str, path: str, **options):
        translations = {
            name: Path(filename).read_text(encoding="utf-8")
            for name, filename in (("base", base), ("current", current), ("other", other))
        }
        normalized = {
            name: f"{text[: match.start(1)]}{_PLACEHOLDER}{text[match.end(1) :]}"
            for name, text in translations.items()
            if (match := _header(text, path)) is not None
        }
        source_path = Path(path).with_name(catalog.WORKBOOK).as_posix()
        sources = {
            name: _source_version(text, path, source_path)
            for name, text in translations.items()
        }

        with tempfile.TemporaryDirectory(prefix="workbook-translation-") as directory:
            temporary = Path(directory)
            merged_source = _merge_file(temporary, "source", sources)
            merged = _merge_file(temporary, "translation", normalized)
        if merged_source.returncode:
            raise CommandError(
                f"{source_path}: its merge is not clean; resolve it with the translation."
            )
        if merged.returncode:
            raise CommandError(f"{path}: its translated body does not merge clean: {merged.stderr}")

        match = _header(merged.stdout, path)
        digest = catalog.source_hash(catalog.user_part(merged_source.stdout))
        result = f"{merged.stdout[: match.start(1)]}{digest}{merged.stdout[match.end(1) :]}"
        Path(current).write_text(result, encoding="utf-8")
