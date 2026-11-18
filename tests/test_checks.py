"""``scripts/checks.sh fast``: what a change passes before it is pushed (.githooks/pre-push runs it on the pushed commit).

It runs the guardrail tests of the size of each file, ruff, the import contracts and the cognitive complexity, the
lists that only shrink included, in seconds, without the network or a database. A tree that breaks any of them fails
the command, and its output names the file and the reason.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
COMMAND = "scripts/checks.sh"
KNOTTY = "".join(
    ["def knotty(a, b, c, d, e):\n"]
    + [f"{'    ' * (depth + 1)}if {name}:\n" for depth, name in enumerate("abcdea")]
    + ["                            return 1\n", "    return 0\n"]
)
BREAKS = {
    "apps/demo/filler.py": "".join(f"# filler {line}\n" for line in range(501)),
    "apps/demo/unused.py": "import os\n",
    # Spelled apart so that this file carries no noqa marker of its own.
    "apps/demo/silenced.py": "import os  " + "#" + " noqa: F401\n",
    "apps/demo/knotty.py": KNOTTY,
    "base/crossing.py": "import apps.demo\n\nDEMO = apps.demo\n",
}
REPORTS = {
    "size": "apps/demo/filler.py: 501 lines, over its cap of 500",
    "ruff": "apps/demo/unused.py:1:8: F401",
    "frozen noqa markers": "A new noqa for these rules",
    "complexity": "apps/demo/knotty.py::knotty scores 21, over 15",
    "imports": "base.crossing -> apps.demo",
}


def checks(tree: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """The command as the hook runs it: the suite's own pytest settings do not leak into it, and no database is up."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("PYTEST_")}
    env.update(UV_PROJECT_ENVIRONMENT=sys.prefix, DB_HOST="127.0.0.1", DB_PORT="1")
    return subprocess.run(
        ["bash", COMMAND, *args], cwd=tree, env=env, capture_output=True, text=True, timeout=600, check=False
    )


@pytest.fixture
def head_tree(tmp_path):
    """HEAD checked out on its own, with this checkout's command, so that what a test adds stays out of the suite."""
    tree = tmp_path / "tree"
    subprocess.run(["git", "worktree", "add", "--quiet", "--detach", str(tree), "HEAD"], cwd=REPO, check=True)
    if (REPO / COMMAND).is_file():
        shutil.copy2(REPO / COMMAND, tree / COMMAND)
    yield tree
    subprocess.run(["git", "worktree", "remove", "--force", str(tree)], cwd=REPO, check=True)


def test_fast_passes_on_this_tree():
    done = checks(REPO, "fast")
    assert done.returncode == 0, done.stdout[-4000:] + done.stderr[-2000:]


def test_fast_fails_naming_the_file_and_the_reason_of_every_check(head_tree):
    for path, text in BREAKS.items():
        (head_tree / path).write_text(text, encoding="utf-8")
    done = checks(head_tree, "fast")
    assert done.returncode == 1, done.stdout[-4000:] + done.stderr[-2000:]
    missing = [check for check, report in REPORTS.items() if report not in done.stdout]
    assert missing == [], done.stdout[-8000:]


@pytest.mark.parametrize("args", [(), ("slow",)])
def test_an_unknown_mode_says_which_ones_there_are(args):
    done = checks(REPO, *args)
    assert done.returncode == 2
    assert "fast" in done.stderr
