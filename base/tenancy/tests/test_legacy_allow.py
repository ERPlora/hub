"""The suite's fallback is on only for the tests ``.legacy-fallback-allow`` names, and the list only shrinks.

Each case runs a small suite of its own in a subprocess, with the plugin and nothing else of the Hub's ``conftest.py``,
so the fallback it turns on and off never touches the test that runs it.
"""

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from base.tenancy import context
from base.tenancy.tests import legacy, legacy_allow

REPO = Path(__file__).resolve().parents[3]

SUITE = """\
import pytest

from base.tenancy import context


def lean():
    context.current()


def test_leaning():
    lean()


@pytest.mark.parametrize("leans", [True, False])
def test_one_case_leaning(leans):
    if leans:
        lean()


def test_not_leaning():
    pass


def test_not_leaning_and_failing():
    raise AssertionError("broken on its own")
"""

LEANING = ["test_suite.py::test_leaning", "test_suite.py::test_one_case_leaning"]


def run_suite(tmp_path: Path, allowed: list[str], *args: str) -> subprocess.CompletedProcess[str]:
    """``pytest`` over ``SUITE`` in ``tmp_path`` with the plugin alone, ``allowed`` as the list."""
    (tmp_path / "test_suite.py").write_text(SUITE)
    (tmp_path / legacy_allow.ALLOW_FILE).write_text("# may still lean on the fallback\n" + "\n".join(allowed) + "\n")
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    command = [sys.executable, "-m", "pytest", "-p", "base.tenancy.tests.legacy_allow", "-p", "no:django"]
    command += ["-p", "no:cacheprovider", "-q", *args]
    environment = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO), "HOME": str(tmp_path)}
    return subprocess.run(
        command, cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=120, check=False
    )


def outcome(run: subprocess.CompletedProcess[str]) -> str:
    return run.stdout + run.stderr


def stale_lines(run: subprocess.CompletedProcess[str]) -> list[str]:
    """The lines the run says to remove from the list."""
    text = outcome(run)
    if legacy_allow.STALE_TITLE not in text:
        return []
    listed = text.split(legacy_allow.STALE_TITLE, 1)[1]
    return [line.strip() for line in listed.splitlines() if line.startswith("  ")]


def test_the_listed_tests_lean_on_the_fallback_and_the_run_passes(tmp_path):
    run = run_suite(tmp_path, LEANING, "test_suite.py::test_leaning", "test_suite.py::test_one_case_leaning")

    assert run.returncode == 0, outcome(run)
    assert "3 passed" in outcome(run)


def test_a_test_the_list_does_not_name_runs_as_production_and_fails_if_it_leans(tmp_path):
    run = run_suite(tmp_path, LEANING[1:], "test_suite.py::test_leaning")

    assert run.returncode == 1
    assert "HubContextMissing" in outcome(run)
    assert "1 failed" in outcome(run)


def test_a_listed_test_that_runs_every_case_without_leaning_has_to_leave_the_list(tmp_path):
    run = run_suite(tmp_path, [*LEANING, "test_suite.py::test_not_leaning"], "test_suite.py", "-k", "not failing")

    assert run.returncode == 1, outcome(run)
    assert "4 passed" in outcome(run)
    assert stale_lines(run) == ["test_suite.py::test_not_leaning"]


def test_the_cases_of_a_listed_test_spread_over_several_processes_are_judged_together(tmp_path):
    allowed = [*LEANING, "test_suite.py::test_not_leaning"]
    run = run_suite(tmp_path, allowed, "test_suite.py", "-k", "not failing", "-n", "2")

    assert run.returncode == 1, outcome(run)
    assert stale_lines(run) == ["test_suite.py::test_not_leaning"]


@pytest.mark.parametrize(
    "selection",
    [
        pytest.param(["test_suite.py::test_one_case_leaning[False]"], id="named-on-the-command-line"),
        pytest.param(["test_suite.py", "-k", "one_case_leaning and False"], id="its-other-cases-deselected"),
    ],
)
def test_a_listed_test_is_not_judged_on_some_of_its_cases(tmp_path, selection):
    run = run_suite(tmp_path, LEANING, *selection)

    assert run.returncode == 0, outcome(run)
    assert stale_lines(run) == []


def test_a_listed_test_that_fails_is_not_judged(tmp_path):
    allowed = [*LEANING, "test_suite.py::test_not_leaning_and_failing"]
    run = run_suite(tmp_path, allowed, "test_suite.py", "-k", "failing")

    assert run.returncode == 1
    assert "broken on its own" in outcome(run)
    assert stale_lines(run) == []


def test_the_worker_s_pass_over_the_suite_s_businesses_counts_as_leaning(monkeypatch):
    passes = []
    monkeypatch.setattr(legacy, "worker_pass", passes.append)
    before = context._test_fallback_entries

    legacy_allow.worker_pass("now")

    assert passes == ["now"]
    assert context._test_fallback_entries == before + 1


@pytest.mark.parametrize(
    ("nodeid", "entry"),
    [
        ("apps/sale/tests/test_services.py::test_a", "apps/sale/tests/test_services.py::test_a"),
        ("apps/sale/tests/test_services.py::test_a[es-1]", "apps/sale/tests/test_services.py::test_a"),
        ("base/tests/test_x.py::TestY::test_z[a::b]", "base/tests/test_x.py::TestY::test_z"),
    ],
)
def test_a_test_is_listed_by_its_file_and_name_whatever_its_case(nodeid, entry):
    assert legacy_allow.entry_of(nodeid) == entry


def test_a_line_of_the_list_that_cannot_be_read_is_reported():
    text = textwrap.dedent(
        """\
        # a comment

        base/tests/test_a.py::test_one
        base/tests/test_a.py::TestTwo::test_two
        base/tests/test_a.py
        base/tests/test_a.py::test_one[1]
        base/tests/test_a.py::test_one
        """
    )

    entries, errors = legacy_allow.parse_allow(text)

    assert entries == {"base/tests/test_a.py::test_one", "base/tests/test_a.py::TestTwo::test_two"}
    assert errors == [
        f"{legacy_allow.ALLOW_FILE}:5: expected '<file>::<test>', got 'base/tests/test_a.py'",
        f"{legacy_allow.ALLOW_FILE}:6: expected '<file>::<test>', got 'base/tests/test_a.py::test_one[1]'",
        f"{legacy_allow.ALLOW_FILE}:7: base/tests/test_a.py::test_one is listed twice",
    ]


def test_this_suite_turns_the_fallback_on_only_for_the_tests_its_list_names(request):
    plugin = request.config.pluginmanager.get_plugin("legacy_allow")

    assert plugin is not None, "the Hub's conftest.py does not load base.tenancy.tests.legacy_allow"
    assert plugin.allowed, f"no test named in {REPO / legacy_allow.ALLOW_FILE}"
    assert legacy_allow.entry_of(request.node.nodeid) not in plugin.allowed
    assert context._test_fallback is None
