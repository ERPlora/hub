"""Every code file stays small enough for a person to read and change.

Each language has its cap, in physical lines (blank lines and comments too, as ESLint's ``max-lines`` counts them):

- Python: 500 for production and 1,000 for tests.
- TypeScript and JavaScript: 300 for production and 500 for tests.
- Shell: a script over 100 lines is written in Python instead; a shell test has no figure of its own.
- CSS and Django templates have no figure of their own and keep 1,000 and 1,500.
- A Vue page is measured by blocks in the lint (``vue/max-lines-per-block``), not here.

Generated files (migrations, build output, generated folders) do not count. The files over their cap are listed in
``.file-size-allow``, one per line as ``<lines> <path> <issue>``, with the exact number of lines they had when the list
froze them, every one pointing to the issue that tracks splitting them. That list only shrinks: a listed file may
change but never grows past its number, the change that shrinks it lowers the number to the new size, it leaves the
list once it fits its cap, and compared with the list where the branch left origin/main it gains no path and raises no
number. Two paths may enter it: a ``services.py``, ``queries.py`` or ``schemas.py`` moved whole to
``<name>/__init__.py`` takes its number along, and when a cap comes down the files already over it where the branch
left origin/main enter at most at their size there. The caps only come down too: against that same point none rises
and no measured suffix stops being measured.
"""

import ast
import functools
import re
import subprocess
from collections.abc import Iterable
from pathlib import Path

import pytest
from allow_list_base import REPO, comparison_point, file_at_base, git

ALLOW_FILE = ".file-size-allow"
SELF = "tests/test_guardrails_size.py"
BASE_NAME = "where the branch left origin/main"

SCRIPT_CAPS = (300, 500)
OTHER_CAPS = (1000, 1500)
# Production and test cap of each measured suffix.
CAPS = {
    ".py": (500, 1000),
    ".ts": SCRIPT_CAPS,
    ".tsx": SCRIPT_CAPS,
    ".js": SCRIPT_CAPS,
    ".mjs": SCRIPT_CAPS,
    ".cjs": SCRIPT_CAPS,
    ".sh": (100, 1500),
    ".css": OTHER_CAPS,
    ".html": OTHER_CAPS,
}
# The modules other code imports by name: they become a package before anything new goes next to them.
DOOR_MODULES = frozenset({"services.py", "queries.py", "schemas.py"})
GENERATED_DIRS = frozenset({"migrations", "node_modules", "dist", "generated"})
TEST_DIRS = frozenset({"tests", "__tests__", "e2e"})
ALLOW_LINE = re.compile(r"([0-9]+)\s+(\S+)\s+((?:[\w.-]+/)?[\w.-]*#[0-9]+)")
TRACKING_ISSUE = "hub#1542"
NEW_PATH = "new in {allow}; the list only shrinks, so split the file instead"


def physical_lines(data: bytes) -> int:
    """The lines as an editor numbers them: a last line without its newline still counts."""
    return data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)


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


def cap_of(path: str) -> int:
    production, test = CAPS[Path(path).suffix]
    return test if is_test(path) else production


def is_counted(path: str) -> bool:
    """A code file someone writes by hand: generated ones and other kinds of file do not count."""
    pure = Path(path)
    return pure.suffix in CAPS and GENERATED_DIRS.isdisjoint(pure.parts[:-1])


def parse_allow(text: str) -> tuple[dict[str, int], list[str]]:
    """The number of each listed path, and what is wrong with the lines that cannot be read."""
    ceilings: dict[str, int] = {}
    errors: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.startswith("#"):
            continue
        match = ALLOW_LINE.fullmatch(line.strip())
        if match is None:
            errors.append(f"{ALLOW_FILE}:{number}: expected '<lines> <path> <issue>', got {line!r}")
        elif match.group(2) in ceilings:
            errors.append(f"{ALLOW_FILE}:{number}: {match.group(2)} is listed twice")
        else:
            ceilings[match.group(2)] = int(match.group(1))
    return ceilings, errors


def untracked(text: str) -> list[str]:
    """Lines of the list whose issue is not the one that tracks splitting the listed files."""
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = ALLOW_LINE.fullmatch(line.strip())
        if match is not None and match.group(3) != TRACKING_ISSUE:
            found.append(f"{ALLOW_FILE}:{number}: {match.group(2)} points to {match.group(3)}, not to {TRACKING_ISSUE}")
    return found


def oversized(sizes: dict[str, int], ceilings: dict[str, int]) -> list[str]:
    """Files over their cap that are not listed, and listed files past their number."""
    found = []
    for path, lines in sorted(sizes.items()):
        ceiling = ceilings.get(path)
        if ceiling is None and lines > cap_of(path):
            found.append(f"{path}: {lines} lines, over its cap of {cap_of(path)}")
        elif ceiling is not None and lines > ceiling:
            found.append(f"{path}: {lines} lines, over its number of {ceiling} in {ALLOW_FILE}; a listed file never grows")
    return found


def stale(sizes: dict[str, int], ceilings: dict[str, int]) -> list[str]:
    """Listed paths that are gone or already fit under their cap, whose line has to go."""
    found = []
    for path in sorted(ceilings):
        lines = sizes.get(path)
        if lines is None:
            found.append(f"{path}: listed in {ALLOW_FILE} but not a counted code file; remove its line")
        elif lines <= cap_of(path):
            found.append(f"{path}: {lines} lines fit under its cap of {cap_of(path)}; remove its line from {ALLOW_FILE}")
    return found


def loose(sizes: dict[str, int], ceilings: dict[str, int]) -> list[str]:
    """Numbers left above a file that shrank: they come down to its exact size."""
    return [
        f"{path}: {sizes[path]} lines; lower its number in {ALLOW_FILE} from {ceiling} to {sizes[path]}"
        for path, ceiling in sorted(ceilings.items())
        if path in sizes and ceiling > sizes[path]
    ]


def moved_from(path: str, ceilings: dict[str, int], base: dict[str, int]) -> str | None:
    """The listed ``services.py``, ``queries.py`` or ``schemas.py`` that ``path`` is, moved whole into its package."""
    package, _, name = path.rpartition("/")
    module = f"{package}.py"
    moved = name == "__init__.py" and module.rpartition("/")[2] in DOOR_MODULES
    return module if moved and module in base and module not in ceilings else None


def allowed_number(path: str, ceilings: dict[str, int], base: dict[str, int], base_sizes: dict[str, int]) -> int | None:
    """The highest number ``path`` may have against the base list, or None when it may not be listed.

    ``base_sizes`` holds the lines the comparison point had at the listed paths its list does not name: a file already
    over a cap that came down since enters at most at that size.
    """
    if path in base:
        return base[path]
    module = moved_from(path, ceilings, base)
    if module is not None:
        return base[module]
    lines = base_sizes.get(path)
    return lines if lines is not None and is_counted(path) and lines > cap_of(path) else None


def loosened(ceilings: dict[str, int], base: dict[str, int], base_sizes: dict[str, int]) -> list[str]:
    """Paths the list gained and numbers it raised compared with the base list."""
    found = []
    for path, ceiling in sorted(ceilings.items()):
        allowed = allowed_number(path, ceilings, base, base_sizes)
        if allowed is None:
            found.append(f"{path}: {NEW_PATH.format(allow=ALLOW_FILE)}")
        elif ceiling > allowed:
            found.append(f"{path}: its number in {ALLOW_FILE} went up from {allowed} to {ceiling}; the list only shrinks")
    return found


@functools.cache
def code_sizes(repo: Path = REPO) -> dict[str, int]:
    """Physical lines of each counted code file: the tracked ones and the new ones git does not ignore."""
    listing = git(repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    assert listing.returncode == 0, listing.stderr
    paths = {path for path in listing.stdout.split("\0") if path and is_counted(path)}
    return {path: physical_lines((repo / path).read_bytes()) for path in paths if (repo / path).is_file()}


def sizes_at_base(paths: Iterable[str], repo: Path = REPO) -> dict[str, int]:
    """The lines each of ``paths`` had where the branch left origin/main, leaving out those it did not have."""
    point = comparison_point(repo)
    sizes = {}
    for path in paths:
        shown = subprocess.run(["git", "show", f"{point}:{path}"], cwd=repo, capture_output=True, check=False)
        if shown.returncode == 0:
            sizes[path] = physical_lines(shown.stdout)
    return sizes


def caps_in(source: str) -> dict[str, tuple[int, int]] | None:
    """The ``CAPS`` table as ``source``, the text of this test, sets it; None when it has no such table."""
    pairs: dict[str, tuple[int, int]] = {}
    for node in ast.parse(source).body:
        if not isinstance(node, ast.Assign) or not isinstance(node.targets[0], ast.Name):
            continue
        if node.targets[0].id == "CAPS":
            return {
                key.value: pairs[value.id] if isinstance(value, ast.Name) else ast.literal_eval(value)
                for key, value in zip(node.value.keys, node.value.values, strict=True)
            }
        if isinstance(node.value, ast.Tuple):
            pairs[node.targets[0].id] = ast.literal_eval(node.value)
    return None


def base_caps(repo: Path = REPO) -> dict[str, tuple[int, int]] | None:
    """The caps where the branch left origin/main, or None while this test had no caps by language there."""
    source = file_at_base(SELF, repo)
    return None if source is None else caps_in(source)


def raised_caps(caps: dict[str, tuple[int, int]], before: dict[str, tuple[int, int]]) -> list[str]:
    """Caps above the ones at the comparison point, and suffixes it measured that are no longer measured."""
    found = []
    for suffix, then in before.items():
        if suffix not in caps:
            found.append(f"{suffix}: no longer measured, capped {BASE_NAME}")
            continue
        for kind, now, was in zip(("production", "test"), caps[suffix], then, strict=True):
            if now > was:
                found.append(f"{suffix}: {kind} cap {now}, {was} {BASE_NAME}")
    return found


def base_ceilings() -> dict[str, int] | None:
    """The list where the branch left origin/main, or None where there was no list yet (the commit that brings it)."""
    text = file_at_base(ALLOW_FILE)
    if text is None:
        return None
    ceilings, errors = parse_allow(text)
    assert not errors, "the list at the comparison point cannot be read:\n" + "\n".join(errors)
    return ceilings


def allow_text() -> str:
    """The working tree's list; without the file, nothing is allowed over its cap."""
    allow = REPO / ALLOW_FILE
    return allow.read_text(encoding="utf-8") if allow.is_file() else ""


def current_ceilings() -> dict[str, int]:
    ceilings, errors = parse_allow(allow_text())
    assert not errors, "\n".join(errors)
    return ceilings


def test_code_files_stay_under_their_cap():
    sizes = code_sizes()
    assert "tests/test_guardrails_size.py" in sizes, "git ls-files listed no code"
    found = oversized(sizes, current_ceilings())
    assert not found, "Code files over their cap; what a change adds goes to a new module:\n" + "\n".join(found)


def test_the_allow_list_holds_only_files_still_over_their_cap():
    found = stale(code_sizes(), current_ceilings())
    assert not found, "Lines of the allow list that have to go:\n" + "\n".join(found)


def test_each_number_of_the_allow_list_follows_its_file_down():
    found = loose(code_sizes(), current_ceilings())
    assert not found, f"Numbers of {ALLOW_FILE} to lower:\n" + "\n".join(found)


def test_the_allow_list_never_gains_a_path_nor_raises_a_number():
    before = base_ceilings()
    if before is None:
        pytest.skip(f"the comparison point has no {ALLOW_FILE} yet: this is the commit that brings it")
    ceilings = current_ceilings()
    found = loosened(ceilings, before, sizes_at_base(path for path in ceilings if path not in before))
    assert not found, "The allow list only shrinks:\n" + "\n".join(found)


def test_no_cap_rises_against_main():
    before = base_caps()
    if before is None:
        pytest.skip("this test had no caps by language where the branch left origin/main: this is the commit that brings them")
    found = raised_caps(CAPS, before)
    assert not found, "A cap only comes down:\n" + "\n".join(found)


def test_every_exception_points_to_the_issue_that_tracks_splitting_the_files():
    found = untracked(allow_text())
    assert not found, f"Lines of {ALLOW_FILE} that have to point to {TRACKING_ISSUE}:\n" + "\n".join(found)


@pytest.mark.parametrize(
    ("path", "cap"),
    [
        ("base/services.py", 500),
        ("apps/sale/tests/test_services.py", 1000),
        ("base/tests/helpers.py", 1000),
        ("apps/sale/test_things.py", 1000),
        ("apps/sale/conftest.py", 1000),
        ("frontend/main.ts", 300),
        ("apps/sale/frontend/operations.d.ts", 300),
        ("vitest.setup.fixture.ts", 300),
        ("scripts/app-icons.mjs", 300),
        ("frontend/shell.tsx", 300),
        ("apps/sale/frontend/pages/PosPage.test.ts", 500),
        ("apps/sale/frontend/__tests__/mount-pos.ts", 500),
        ("tests/e2e/helpers.ts", 500),
        ("tests/e2e/sale.spec.ts", 500),
        (".github/scripts/ecs-deploy.sh", 100),
        (".github/scripts/pytest-shard.test.sh", 1500),
        ("base/static/base/hub.css", 1000),
        ("base/templates/base/spa.html", 1000),
        ("base/tests/fixtures/ticket.html", 1500),
    ],
)
def test_each_language_has_its_own_cap(path, cap):
    assert cap_of(path) == cap


@pytest.mark.parametrize(
    ("path", "test"),
    [
        ("base/services.py", False),
        ("vitest.setup.fixture.ts", False),
        ("apps/sale/tests/test_services.py", True),
        ("base/tests/helpers.py", True),
        ("tests/e2e/helpers.ts", True),
        ("apps/sale/frontend/__tests__/mount-pos.ts", True),
        ("apps/sale/test_things.py", True),
        ("apps/sale/conftest.py", True),
        ("apps/sale/frontend/pages/PosPage.test.ts", True),
        ("tests/e2e/sale.spec.ts", True),
        (".github/scripts/pytest-shard.test.sh", True),
    ],
)
def test_a_file_is_a_test_by_its_folder_or_its_name(path, test):
    assert is_test(path) is test


@pytest.mark.parametrize(
    ("path", "counted"),
    [
        ("base/services.py", True),
        ("frontend/main.ts", True),
        ("scripts/app-icons.mjs", True),
        (".github/scripts/ecs-deploy.sh", True),
        ("base/templates/base/spa.html", True),
        ("base/frontend/pages/FilesPage.vue", False),
        ("apps/sale/migrations/0001_initial.py", False),
        ("frontend/dist/assets/main.js", False),
        ("node_modules/vue/index.js", False),
        ("frontend/generated/operations.ts", False),
        ("pnpm-lock.yaml", False),
        ("base/locale/es/LC_MESSAGES/django.po", False),
        ("apps/verifactu/xsd/xmldsig-core-schema.xsd", False),
    ],
)
def test_only_hand_written_code_counts_and_a_vue_page_is_left_to_the_lint_of_its_blocks(path, counted):
    assert is_counted(path) is counted


def test_a_last_line_without_its_newline_counts():
    assert [physical_lines(data) for data in (b"", b"a\n", b"a\nb", b"a\n\n", b"a\r\nb\r\n")] == [0, 1, 2, 2, 2]


def test_an_unlisted_file_over_its_cap_fails_and_one_at_it_passes():
    sizes = {
        "base/big.py": 501,
        "base/edge.py": 500,
        "base/tests/test_big.py": 1001,
        "base/tests/test_edge.py": 1000,
        "frontend/big.ts": 301,
        "frontend/edge.ts": 300,
        "frontend/big.test.ts": 501,
        "frontend/edge.test.ts": 500,
        "scripts/big.sh": 101,
        "scripts/edge.sh": 100,
    }
    assert oversized(sizes, {}) == [
        "base/big.py: 501 lines, over its cap of 500",
        "base/tests/test_big.py: 1001 lines, over its cap of 1000",
        "frontend/big.test.ts: 501 lines, over its cap of 500",
        "frontend/big.ts: 301 lines, over its cap of 300",
        "scripts/big.sh: 101 lines, over its cap of 100",
    ]


def test_a_listed_file_may_stay_at_its_number_but_never_grow_past_it():
    assert oversized({"base/services.py": 5180}, {"base/services.py": 5180}) == []
    assert oversized({"base/services.py": 5181}, {"base/services.py": 5180}) == [
        f"base/services.py: 5181 lines, over its number of 5180 in {ALLOW_FILE}; a listed file never grows"
    ]


def test_a_listed_file_that_fits_or_is_gone_has_to_leave_the_list():
    sizes = {"base/split.py": 500, "base/still.py": 501, "base/tests/test_split.py": 1000}
    ceilings = {"base/split.py": 510, "base/still.py": 501, "base/tests/test_split.py": 1010, "base/gone.py": 600}
    assert stale(sizes, ceilings) == [
        f"base/gone.py: listed in {ALLOW_FILE} but not a counted code file; remove its line",
        f"base/split.py: 500 lines fit under its cap of 500; remove its line from {ALLOW_FILE}",
        f"base/tests/test_split.py: 1000 lines fit under its cap of 1000; remove its line from {ALLOW_FILE}",
    ]


def test_a_listed_file_that_shrank_has_its_number_lowered_to_its_exact_size():
    sizes = {"base/services.py": 5179, "base/queries.py": 2900}
    assert loose(sizes, {"base/services.py": 5180, "base/queries.py": 2900, "base/gone.py": 700}) == [
        f"base/services.py: 5179 lines; lower its number in {ALLOW_FILE} from 5180 to 5179"
    ]


def test_the_list_may_drop_and_lower_entries_but_not_add_or_raise_them():
    before = {"base/services.py": 5180, "base/queries.py": 2900, "base/schemas.py": 2100}
    assert loosened({"base/services.py": 5100, "base/queries.py": 2900}, before, {}) == []
    assert loosened({"base/services.py": 5181, "base/new.py": 600, "base/fits.py": 600}, before, {"base/fits.py": 400}) == [
        f"base/fits.py: new in {ALLOW_FILE}; the list only shrinks, so split the file instead",
        f"base/new.py: new in {ALLOW_FILE}; the list only shrinks, so split the file instead",
        f"base/services.py: its number in {ALLOW_FILE} went up from 5180 to 5181; the list only shrinks",
    ]


@pytest.mark.parametrize("door", ["services", "queries", "schemas"])
def test_a_door_module_moved_whole_into_its_package_keeps_its_number(door):
    assert loosened({f"apps/sale/{door}/__init__.py": 3436}, {f"apps/sale/{door}.py": 3436}, {}) == []


def test_that_move_is_the_only_new_path_and_never_raises_the_number():
    before = {"apps/sale/services.py": 3436, "apps/sale/models.py": 900, "base/queries.py": 2900}
    ceilings = {
        "apps/sale/services/__init__.py": 3437,
        "apps/sale/models/__init__.py": 900,
        "base/queries.py": 2900,
        "base/queries/__init__.py": 2900,
        "apps/sale/services/refunds.py": 600,
    }
    assert loosened(ceilings, before, {}) == [
        f"apps/sale/models/__init__.py: new in {ALLOW_FILE}; the list only shrinks, so split the file instead",
        f"apps/sale/services/__init__.py: its number in {ALLOW_FILE} went up from 3436 to 3437; the list only shrinks",
        f"apps/sale/services/refunds.py: new in {ALLOW_FILE}; the list only shrinks, so split the file instead",
        f"base/queries/__init__.py: new in {ALLOW_FILE}; the list only shrinks, so split the file instead",
    ]


def test_a_file_already_over_a_lowered_cap_enters_at_most_at_its_size_where_the_branch_left_main():
    at_base = {"apps/sale/api.py": 965, "apps/sale/admin.py": 965, "apps/sale/views.py": 500}
    ceilings = {"apps/sale/api.py": 965, "apps/sale/admin.py": 966, "apps/sale/views.py": 500}
    assert loosened(ceilings, {}, at_base) == [
        f"apps/sale/admin.py: its number in {ALLOW_FILE} went up from 965 to 966; the list only shrinks",
        f"apps/sale/views.py: new in {ALLOW_FILE}; the list only shrinks, so split the file instead",
    ]


def test_a_line_of_the_list_that_cannot_be_read_is_reported():
    text = "# a comment\n\n5180 base/services.py hub#1542\n1100 base/x.py\nabc base/y.py hub#1\n5180 base/services.py hub#2\n"
    ceilings, errors = parse_allow(text)
    assert ceilings == {"base/services.py": 5180}
    assert errors == [
        f"{ALLOW_FILE}:4: expected '<lines> <path> <issue>', got '1100 base/x.py'",
        f"{ALLOW_FILE}:5: expected '<lines> <path> <issue>', got 'abc base/y.py hub#1'",
        f"{ALLOW_FILE}:6: base/services.py is listed twice",
    ]


def test_an_exception_that_points_to_another_issue_is_reported():
    text = f"# split them in {TRACKING_ISSUE}\n1200 base/a.py {TRACKING_ISSUE}\n1100 base/b.py hub#1531\n1100 base/c.py saas#1542\n"
    assert untracked(text) == [
        f"{ALLOW_FILE}:3: base/b.py points to hub#1531, not to {TRACKING_ISSUE}",
        f"{ALLOW_FILE}:4: base/c.py points to saas#1542, not to {TRACKING_ISSUE}",
    ]


def test_a_cap_may_not_rise_nor_stop_being_measured():
    before = {".py": (500, 1000), ".ts": (300, 500), ".js": (300, 500), ".sh": (100, 1500)}
    caps = {".py": (501, 1000), ".ts": (300, 501), ".js": (299, 400), ".css": (1000, 1500)}
    assert raised_caps(caps, before) == [
        ".py: production cap 501, 500 where the branch left origin/main",
        ".ts: test cap 501, 500 where the branch left origin/main",
        ".sh: no longer measured, capped where the branch left origin/main",
    ]
    assert raised_caps(before, before) == []


def test_the_caps_are_read_from_the_source_of_this_test():
    assert caps_in(Path(__file__).read_text(encoding="utf-8")) == CAPS


def test_a_source_without_caps_by_language_has_none_to_compare():
    assert caps_in("PRODUCTION_LIMIT = 1000\nTEST_LIMIT = 1500\n") is None


def run_git(repo: Path, *args: str) -> None:
    """Git in a scratch repository, without the machine's hooks or signing."""
    command = ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-c", "user.name=t"]
    subprocess.run([*command, "-c", "user.email=t@example.com", *args], cwd=repo, check=True, capture_output=True)


def commit_files(repo: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text, encoding="utf-8")
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "-m", "change")


def test_new_code_files_count_before_they_are_added_and_ignored_ones_do_not(tmp_path):
    run_git(tmp_path, "init", "-q", "-b", "main")
    commit_files(tmp_path, {".gitignore": "scratch.py\n", "base/services.py": "a\nb\n", "Page.vue": "<template />\n"})
    for name in ("frontend/new.ts", "scratch.py", "README.md", "apps/sale/migrations/0001_initial.py"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("a\n", encoding="utf-8")
    assert code_sizes(tmp_path) == {"base/services.py": 2, "frontend/new.ts": 1}


def test_the_sizes_where_the_branch_left_main_are_read_there(tmp_path):
    run_git(tmp_path, "init", "-q", "-b", "main")
    commit_files(tmp_path, {"base/models.py": "a\n" * 600})
    run_git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
    run_git(tmp_path, "checkout", "-q", "-b", "work")
    commit_files(tmp_path, {"base/models.py": "a\n" * 700, "base/admin.py": "a\n"})
    assert sizes_at_base(["base/models.py", "base/admin.py", "base/gone.py"], tmp_path) == {"base/models.py": 600}


def test_the_caps_where_the_branch_left_main_are_read_there(tmp_path):
    run_git(tmp_path, "init", "-q", "-b", "main")
    commit_files(tmp_path, {SELF: 'BOTH = (500, 1000)\nCAPS = {".py": BOTH, ".sh": (100, 1500)}\n'})
    run_git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
    run_git(tmp_path, "checkout", "-q", "-b", "work")
    commit_files(tmp_path, {SELF: 'CAPS = {".py": (600, 1000)}\n'})
    assert base_caps(tmp_path) == {".py": (500, 1000), ".sh": (100, 1500)}
