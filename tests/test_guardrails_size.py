"""Every code file stays small enough for a person to read and change.

A production file holds at most 1,000 physical lines and a test file at most 1,500. Generated files (migrations, build
output, generated folders) do not count. The files that were already longer when the limit came in are listed in
``.file-size-allow``, one per line as ``<ceiling> <path> <issue>``, and that list only shrinks: a listed file never grows
past its ceiling, a file leaves the list as soon as it fits under its limit, and the list never gains a path or raises a
ceiling compared with the list where the branch left origin/main.
"""

import functools
import re
from pathlib import Path

import pytest
from allow_list_base import REPO, file_at_base, git

ALLOW_FILE = ".file-size-allow"

PRODUCTION_LIMIT = 1000
TEST_LIMIT = 1500
CODE_SUFFIXES = frozenset({".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".vue", ".sh", ".css", ".html"})
GENERATED_DIRS = frozenset({"migrations", "node_modules", "dist", "generated"})
TEST_DIRS = frozenset({"tests", "e2e"})
ALLOW_LINE = re.compile(r"([0-9]+)\s+(\S+)\s+((?:[\w.-]+/)?[\w.-]*#[0-9]+)")


def is_test(path: str) -> bool:
    parts = Path(path).parts
    name = parts[-1]
    return (
        not TEST_DIRS.isdisjoint(parts[:-1])
        or (name.startswith("test_") and name.endswith(".py"))
        or name == "conftest.py"
        or ".test." in name
        or ".spec." in name
    )


def limit_for(path: str) -> int:
    return TEST_LIMIT if is_test(path) else PRODUCTION_LIMIT


def is_counted(path: str) -> bool:
    """A code file someone writes by hand: generated ones and other kinds of file do not count."""
    pure = Path(path)
    return pure.suffix in CODE_SUFFIXES and GENERATED_DIRS.isdisjoint(pure.parts[:-1])


def parse_allow(text: str) -> tuple[dict[str, int], list[str]]:
    """The ceiling of each listed path, and what is wrong with the lines that cannot be read."""
    ceilings: dict[str, int] = {}
    errors: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.startswith("#"):
            continue
        match = ALLOW_LINE.fullmatch(line.strip())
        if match is None:
            errors.append(f"{ALLOW_FILE}:{number}: expected '<ceiling> <path> <issue>', got {line!r}")
        elif match.group(2) in ceilings:
            errors.append(f"{ALLOW_FILE}:{number}: {match.group(2)} is listed twice")
        else:
            ceilings[match.group(2)] = int(match.group(1))
    return ceilings, errors


def oversized(sizes: dict[str, int], ceilings: dict[str, int]) -> list[str]:
    """Files over their limit that are not listed, and listed files over their ceiling."""
    found = []
    for path, lines in sorted(sizes.items()):
        ceiling = ceilings.get(path)
        if ceiling is None and lines > limit_for(path):
            found.append(f"{path}: {lines} lines, over the limit of {limit_for(path)}; split it by responsibility")
        elif ceiling is not None and lines > ceiling:
            found.append(f"{path}: {lines} lines, over its ceiling of {ceiling} in {ALLOW_FILE}; a listed file never grows")
    return found


def stale(sizes: dict[str, int], ceilings: dict[str, int]) -> list[str]:
    """Listed paths that are gone or already fit under their limit: their line has to go."""
    found = []
    for path in sorted(ceilings):
        if path not in sizes:
            found.append(f"{path}: listed in {ALLOW_FILE} but not a counted code file; remove its line")
        elif sizes[path] <= limit_for(path):
            found.append(
                f"{path}: {sizes[path]} lines fit under the limit of {limit_for(path)}; remove its line from {ALLOW_FILE}"
            )
    return found


def loosened(ceilings: dict[str, int], base_ceilings: dict[str, int]) -> list[str]:
    """Paths the list gained and ceilings it raised compared with the base list."""
    found = []
    for path, ceiling in sorted(ceilings.items()):
        before = base_ceilings.get(path)
        if before is None:
            found.append(f"{path}: new in {ALLOW_FILE}; the list only shrinks, so split the file instead")
        elif ceiling > before:
            found.append(f"{path}: its ceiling in {ALLOW_FILE} went up from {before} to {ceiling}; the list only shrinks")
    return found


@functools.cache
def code_sizes() -> dict[str, int]:
    """Physical lines of each counted code file: the tracked ones and the new ones git does not ignore."""
    listing = git(REPO, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    assert listing.returncode == 0, listing.stderr
    paths = {path for path in listing.stdout.split("\0") if path and is_counted(path)}
    return {path: len((REPO / path).read_bytes().splitlines()) for path in paths if (REPO / path).is_file()}


def base_ceilings() -> dict[str, int] | None:
    """The list where the branch left origin/main, or None where there was no list yet (the commit that brings it)."""
    text = file_at_base(ALLOW_FILE)
    if text is None:
        return None
    ceilings, errors = parse_allow(text)
    assert not errors, "the list at the comparison point cannot be read:\n" + "\n".join(errors)
    return ceilings


def current_ceilings() -> dict[str, int]:
    """The working tree's list; without the file, nothing is allowed over its limit."""
    allow = REPO / ALLOW_FILE
    ceilings, errors = parse_allow(allow.read_text(encoding="utf-8") if allow.is_file() else "")
    assert not errors, "\n".join(errors)
    return ceilings


def test_code_files_stay_under_their_size_limit():
    sizes = code_sizes()
    assert "tests/test_guardrails_size.py" in sizes, "git ls-files listed no code"
    found = oversized(sizes, current_ceilings())
    assert not found, "Code files over their size limit:\n" + "\n".join(found)


def test_the_allow_list_holds_only_files_still_over_their_limit():
    found = stale(code_sizes(), current_ceilings())
    assert not found, "Lines of the allow list that have to go:\n" + "\n".join(found)


def test_the_allow_list_never_gains_a_path_nor_raises_a_ceiling():
    before = base_ceilings()
    if before is None:
        pytest.skip(f"the comparison point has no {ALLOW_FILE} yet: this is the commit that brings it")
    found = loosened(current_ceilings(), before)
    assert not found, "The allow list only shrinks:\n" + "\n".join(found)


@pytest.mark.parametrize(
    ("path", "test"),
    [
        ("base/services.py", False),
        ("apps/sale/frontend/pages/PosPage.vue", False),
        ("vitest.setup.fixture.ts", False),
        ("apps/sale/tests/test_services.py", True),
        ("base/tests/helpers.py", True),
        ("tests/e2e/helpers.ts", True),
        ("apps/sale/test_things.py", True),
        ("apps/sale/conftest.py", True),
        ("apps/sale/frontend/pages/PosPage.test.ts", True),
        ("tests/e2e/sale.spec.ts", True),
        (".github/scripts/pytest-shard.test.sh", True),
    ],
)
def test_a_file_is_a_test_by_its_folder_or_its_name(path, test):
    assert is_test(path) is test
    assert limit_for(path) == (TEST_LIMIT if test else PRODUCTION_LIMIT)


@pytest.mark.parametrize(
    ("path", "counted"),
    [
        ("base/services.py", True),
        ("frontend/main.ts", True),
        ("base/frontend/pages/FilesPage.vue", True),
        ("scripts/app-icons.mjs", True),
        (".github/scripts/ecs-deploy.sh", True),
        ("base/templates/base/spa.html", True),
        ("apps/sale/migrations/0001_initial.py", False),
        ("frontend/dist/assets/main.js", False),
        ("node_modules/vue/index.js", False),
        ("frontend/generated/operations.ts", False),
        ("pnpm-lock.yaml", False),
        ("base/locale/es/LC_MESSAGES/django.po", False),
        ("apps/verifactu/xsd/xmldsig-core-schema.xsd", False),
    ],
)
def test_only_hand_written_code_counts(path, counted):
    assert is_counted(path) is counted


def test_an_unlisted_file_over_its_limit_fails_and_one_at_it_passes():
    sizes = {"base/big.py": PRODUCTION_LIMIT + 1, "base/edge.py": PRODUCTION_LIMIT, "base/tests/test_x.py": TEST_LIMIT}
    assert oversized(sizes, {}) == [
        f"base/big.py: {PRODUCTION_LIMIT + 1} lines, over the limit of {PRODUCTION_LIMIT}; split it by responsibility"
    ]


def test_a_listed_file_may_stay_up_to_its_ceiling_but_never_past_it():
    assert oversized({"base/services.py": 5200}, {"base/services.py": 5200}) == []
    assert oversized({"base/services.py": 5201}, {"base/services.py": 5200}) == [
        f"base/services.py: 5201 lines, over its ceiling of 5200 in {ALLOW_FILE}; a listed file never grows"
    ]


def test_a_listed_file_that_fits_or_is_gone_has_to_leave_the_list():
    sizes = {"base/split.py": PRODUCTION_LIMIT, "base/still.py": PRODUCTION_LIMIT + 1}
    ceilings = {"base/split.py": 1100, "base/still.py": 1100, "base/gone.py": 1100}
    assert stale(sizes, ceilings) == [
        f"base/gone.py: listed in {ALLOW_FILE} but not a counted code file; remove its line",
        f"base/split.py: {PRODUCTION_LIMIT} lines fit under the limit of {PRODUCTION_LIMIT}; remove its line from {ALLOW_FILE}",
    ]


def test_the_list_may_drop_and_lower_entries_but_not_add_or_raise_them():
    before = {"base/services.py": 5200, "base/queries.py": 2900, "base/schemas.py": 2100}
    assert loosened({"base/services.py": 5100, "base/queries.py": 2900}, before) == []
    assert loosened({"base/services.py": 5300, "base/new.py": 1100}, before) == [
        f"base/new.py: new in {ALLOW_FILE}; the list only shrinks, so split the file instead",
        f"base/services.py: its ceiling in {ALLOW_FILE} went up from 5200 to 5300; the list only shrinks",
    ]


def test_a_line_of_the_list_that_cannot_be_read_is_reported():
    text = "# a comment\n\n5200 base/services.py hub#1531\n1100 base/x.py\nabc base/y.py hub#1\n5200 base/services.py hub#2\n"
    ceilings, errors = parse_allow(text)
    assert ceilings == {"base/services.py": 5200}
    assert errors == [
        f"{ALLOW_FILE}:4: expected '<ceiling> <path> <issue>', got '1100 base/x.py'",
        f"{ALLOW_FILE}:5: expected '<ceiling> <path> <issue>', got 'abc base/y.py hub#1'",
        f"{ALLOW_FILE}:6: base/services.py is listed twice",
    ]

