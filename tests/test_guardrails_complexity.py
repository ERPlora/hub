"""No Python function gets harder to follow than a cognitive complexity of 15.

complexipy scores each function's cognitive complexity, Sonar's measure: each branch, loop or jump in the flow adds one,
plus one more for every level it is nested in, so deep nesting costs more than a flat run of checks. pyproject.toml's
``[tool.complexipy]`` sets the limit and the code it reads: all the Python but the migrations, which are generated, and
the live and ui submodules, which their own repos check. ``uv run complexipy`` runs it the same way.

The functions that were already over the limit when it came in are frozen in complexipy-snapshot.json, complexipy's own
baseline, each with its score. A function over the limit that has no entry, or that scores more than its entry, fails.
An entry that scores more than its function does now, or whose function is gone, fails until it is lowered or removed:
a plain ``uv run complexipy`` rewrites the file so. Compared with where the branch left origin/main, the snapshot gains
no entry and no entry scores more: it only shrinks. complexipy keys an entry by file and name, so a function that moves
needs its entry recorded again (``uv run complexipy --snapshot-create``); the entry may then follow it, at no higher
score, into the package of the same name or a flat sibling named after it (``base/services/__init__.py`` into
``base/services/sessions.py``). Each old entry carries one function, so a frozen function copied twice fails.

No comment switches the limit off: the configuration makes complexipy disregard its ignore markers.
"""

import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from allow_list_base import REPO, file_at_base, git
from test_guardrails_imports import write_tree
from test_guardrails_ruff import follows

CONFIG = "pyproject.toml"
SNAPSHOT = "complexipy-snapshot.json"
LIMIT = 15
COMPLEXIPY_CONFIGURATION = {
    "paths": ["."],
    "exclude": ["**/migrations/**", "packages/**"],
    "max-complexity-allowed": LIMIT,
    "no-ignore": True,
}
NO_SNAPSHOT_AT_BASE = (
    f"{SNAPSHOT} did not exist where the branch left origin/main: this is the commit that freezes what breaks the limit"
)

Key = tuple[str, str]

NESTED = """
    if a:
        if b:
            if c:
                if d:
                    for item in a:
                        if item:
                            return item
    return None
"""


def complexipy(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    script = Path(sys.executable).with_name("complexipy")
    return subprocess.run([str(script), *args], cwd=cwd, capture_output=True, text=True, check=False)


def scores(cache: Path, cwd: Path = REPO) -> dict[Key, int]:
    """Each function's score with the configuration under ``cwd``, keyed by file and name as complexipy keys its
    snapshot: of the functions of one file that share a name, the first keeps it and each next one takes it followed by a
    hash sign and its position."""
    output = ("--output-format", "json", "--output", "-", "--cache-dir", str(cache))
    result = complexipy("--snapshot-ignore", "--quiet", *output, cwd=cwd)
    # It exits with 1 both when a function is over the limit and when it cannot run; only a run prints the report.
    assert result.returncode in (0, 1) and result.stdout.lstrip().startswith("["), result.stderr
    found: dict[Key, int] = {}
    # The report comes sorted by score, so the functions are put back in the order they are written.
    for function in sorted(json.loads(result.stdout), key=lambda function: (function["path"], function["line_start"])):
        path, name = function["path"], function["function_name"]
        key, times = (path, name), 1
        while key in found:
            times += 1
            key = (path, f"{name}#{times}")
        found[key] = function["complexity"]
    return found


def over_limit(found: dict[Key, int]) -> dict[Key, int]:
    return {key: score for key, score in found.items() if score > LIMIT}


def entries(text: str) -> dict[Key, int]:
    """The snapshot's entries, keyed by file and name, with their scores."""
    return {
        (file["path"], function["name"]): function["complexity"]
        for file in json.loads(text)
        for function in file["functions"]
    }


def against_snapshot(over: dict[Key, int], frozen: dict[Key, int]) -> list[str]:
    """How the functions over the limit and the snapshot's entries disagree."""
    problems = [
        f"{path}::{name} scores {score}, over {LIMIT}: simplify it"
        for (path, name), score in sorted(over.items())
        if (path, name) not in frozen
    ]
    problems += [
        f"{path}::{name} scores {score}, more than the {frozen[(path, name)]} it is frozen at: simplify it"
        for (path, name), score in sorted(over.items())
        if score > frozen.get((path, name), score)
    ]
    problems += [
        f"{path}::{name} is frozen at {score} but is gone or now scores {over.get((path, name), 'within the limit')}: "
        "lower or remove its entry"
        for (path, name), score in sorted(frozen.items())
        if over.get((path, name), 0) < score
    ]
    return problems


def carrier(key: Key, score: int, left: dict[Key, int]) -> Key | None:
    """The entry of ``left`` that may carry ``key``: its own, or one of the same name whose file its function may have
    moved out of, at a score no lower than ``score``."""
    if left.get(key, -1) >= score:
        return key
    path, name = key
    return next(
        (old for old in sorted(left) if old[1] == name and follows(path, old[0]) and left[old] >= score),
        None,
    )


def gained(now: dict[Key, int], before: dict[Key, int]) -> list[str]:
    """The entries of ``now`` that no entry of ``before`` carries: new ones, ones that score more, and copies."""
    left, found = dict(before), []
    for key, score in sorted(now.items()):
        old = carrier(key, score, left)
        if old is None:
            found.append(f"{key[0]}::{key[1]} at {score}")
        else:
            del left[old]
    return found


def test_no_function_scores_more_than_the_limit_or_its_frozen_entry(tmp_path):
    frozen = entries((REPO / SNAPSHOT).read_text(encoding="utf-8"))
    found = against_snapshot(over_limit(scores(tmp_path)), frozen)
    assert found == [], (
        f"Functions over the cognitive complexity limit of {LIMIT}, or {SNAPSHOT} out of step with them. Split a new "
        "or a grown function into smaller ones instead of freezing it:\n" + "\n".join(found)
    )


def test_the_complexipy_configuration_is_exactly_the_limit_and_the_code_it_reads():
    """A looser limit, another excluded folder, honoured ignore markers, a snapshot recorded on every run or a diff
    against a branch would each let a function through: any change to the configuration shows here first, and no other
    file configures complexipy."""
    config = tomllib.loads((REPO / CONFIG).read_text(encoding="utf-8")).get("tool", {}).get("complexipy")
    assert config == COMPLEXIPY_CONFIGURATION
    others = ("complexipy.toml", ".complexipy.toml")
    assert git(REPO, "ls-files", "--cached", "--others", "--exclude-standard", "--", *others).stdout.split() == []


def test_the_snapshot_never_gains_an_entry_or_a_point():
    text = file_at_base(SNAPSHOT)
    if text is None:
        pytest.skip(NO_SNAPSHOT_AT_BASE)
    found = gained(entries((REPO / SNAPSHOT).read_text(encoding="utf-8")), entries(text))
    assert found == [], f"{SNAPSHOT} only shrinks: simplify the function instead of freezing it.\n" + "\n".join(found)


def test_a_function_over_the_limit_without_an_entry_or_above_it_is_reported_and_a_stale_entry_too():
    over = {("base/a.py", "new"): 16, ("base/a.py", "grown"): 30, ("base/a.py", "kept"): 20, ("base/a.py", "less"): 18}
    frozen = {("base/a.py", "grown"): 25, ("base/a.py", "kept"): 20, ("base/a.py", "less"): 22}
    frozen[("base/b.py", "gone")] = 17
    assert against_snapshot(over, frozen) == [
        "base/a.py::new scores 16, over 15: simplify it",
        "base/a.py::grown scores 30, more than the 25 it is frozen at: simplify it",
        "base/a.py::less is frozen at 22 but is gone or now scores 18: lower or remove its entry",
        "base/b.py::gone is frozen at 17 but is gone or now scores within the limit: lower or remove its entry",
    ]


def test_an_entry_follows_its_function_into_its_package_or_a_flat_sibling_at_no_higher_score():
    before = {
        ("base/services/__init__.py", "claim_hub"): 40,
        ("base/services/__init__.py", "Relay::run"): 20,
        ("base/tests/test_services.py", "test_claim"): 18,
        ("apps/sale/services.py", "close"): 30,
    }
    now = {
        ("base/services/provisioning.py", "claim_hub"): 40,
        ("base/services/relay_runs.py", "Relay::run"): 19,
        ("base/tests/test_services_claims.py", "test_claim"): 18,
        ("apps/sale/services.py", "close"): 25,
    }
    assert gained(now, before) == []


def test_a_new_entry_a_higher_score_a_move_elsewhere_a_rename_or_a_copy_is_gained():
    before = {("base/services/__init__.py", "claim_hub"): 40, ("base/queries.py", "home"): 20}
    now = {
        ("base/services/sessions.py", "claim_hub"): 40,
        ("base/services/demos.py", "claim_hub"): 40,
        ("base/queries.py", "home"): 21,
        ("base/tenancy/move.py", "fresh"): 16,
    }
    assert gained(now, before) == [
        "base/queries.py::home at 21",
        "base/services/sessions.py::claim_hub at 40",
        "base/tenancy/move.py::fresh at 16",
    ]
    moved = {("base/tenancy/claims.py", "claim_hub"): 40, ("base/services/sessions.py", "claim_hubs"): 40}
    assert gained(moved, before) == [
        "base/services/sessions.py::claim_hubs at 40",
        "base/tenancy/claims.py::claim_hub at 40",
    ]


def test_a_function_that_stays_keeps_its_own_entry_and_leaves_the_others_to_the_moved_ones():
    before = {("base/services/__init__.py", "run"): 30, ("base/services/demos.py", "run"): 20}
    now = {("base/services/demos.py", "run"): 20, ("base/services/relay_runs.py", "run"): 30}
    assert gained(now, before) == []


def configured_tree(root: Path) -> None:
    lines = ["[tool.complexipy]", *(f"{key} = {json.dumps(value)}" for key, value in COMPLEXIPY_CONFIGURATION.items())]
    write_tree(root, {CONFIG: "\n".join(lines) + "\n"})


def test_the_configuration_scores_every_function_but_the_generated_and_the_submodules_and_reads_no_ignore(tmp_path):
    """The configuration this test asks of pyproject.toml, on a small tree: an ignore marker hides nothing, two
    functions of one name are keyed apart in the order they are written, and the migrations and the submodules are not
    read."""
    configured_tree(tmp_path / "tree")
    write_tree(
        tmp_path / "tree",
        {
            "apps/sale/services.py": (
                f"def close(a, b, c, d):  # complexipy: ignore\n{NESTED}\n\ndef close(a):\n    return a\n"
            ),
            "apps/sale/migrations/0002_close.py": f"def forwards(a, b, c, d):\n{NESTED}",
            "packages/live/live/run.py": f"def run(a, b, c, d):\n{NESTED}",
            "base/flat.py": "def flat(a):\n    if a:\n        return a\n    return None\n",
        },
    )
    found = scores(tmp_path / "cache", cwd=tmp_path / "tree")
    assert over_limit(found) == {("apps/sale/services.py", "close"): 21}
    assert found[("apps/sale/services.py", "close#2")] == 0
    assert found[("base/flat.py", "flat")] == 1


def test_complexipy_records_a_moved_function_under_its_new_file_and_the_entry_follows_it(tmp_path):
    """complexipy's own snapshot, recorded before and after part of base/services/__init__.py moves into a submodule."""
    tree = tmp_path / "tree"
    configured_tree(tree)
    write_tree(tree, {"base/services/__init__.py": f"def claim_hub(a, b, c, d):\n{NESTED}"})
    assert complexipy("--snapshot-create", "--quiet", "--cache-dir", str(tmp_path / "cache"), cwd=tree).returncode == 0
    before = entries((tree / SNAPSHOT).read_text(encoding="utf-8"))
    write_tree(
        tree,
        {
            "base/services/__init__.py": "from . import provisioning as provisioning\n",
            "base/services/provisioning.py": f"def claim_hub(a, b, c, d):\n{NESTED}",
        },
    )
    assert complexipy("--quiet", "--cache-dir", str(tmp_path / "cache"), cwd=tree).returncode == 1
    assert complexipy("--snapshot-create", "--quiet", "--cache-dir", str(tmp_path / "cache"), cwd=tree).returncode == 0
    now = entries((tree / SNAPSHOT).read_text(encoding="utf-8"))
    assert now == {("base/services/provisioning.py", "claim_hub"): 21}
    assert gained(now, before) == []
    assert against_snapshot(over_limit(scores(tmp_path / "cache", cwd=tree)), now) == []
