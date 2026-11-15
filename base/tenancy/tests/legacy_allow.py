"""The suite's fallback is on only for the tests ``.legacy-fallback-allow`` names; every other test runs as production.

The fallback (``legacy.py``) keeps every business of the tests written before the tenancy in control's test database.
The list names, one ``<file>::<test>`` per line, the tests that still lean on it; any other test runs without it, and
leaning on it there fails as it fails in production (``HubContextMissing``, ``HubWithoutDatabase``). A test is listed by
its file and name, whatever its cases: the CI's shards spread the cases of a file, and of a test, over several jobs, and
each case finds its own line. The list only shrinks: ``tests/test_guardrails_legacy_fallback.py`` refuses a line
origin/main does not have, and a run that ran every case of a listed test, every one passing, without leaning on the
fallback once fails, naming the line to remove.
"""

import re
from collections import Counter
from dataclasses import dataclass

import pytest

ALLOW_FILE = ".legacy-fallback-allow"
STALE_TITLE = f"These tests ran every case without leaning on the suite's fallback; remove their lines from {ALLOW_FILE}:"
ENTRY = re.compile(r"[\w./-]+\.py(::\w+)+")
_LEANINGS_BEFORE = pytest.StashKey[int]()


def entry_of(nodeid: str) -> str:
    """The line of the list that names the test of ``nodeid``: its file and name, without its case."""
    name, bracket, _case = nodeid.partition("[")
    return name if bracket else nodeid


def parse_allow(text: str) -> tuple[set[str], list[str]]:
    """The tests the list names, and what is wrong with the lines that cannot be read."""
    entries: set[str] = set()
    errors: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        if ENTRY.fullmatch(entry) is None:
            errors.append(f"{ALLOW_FILE}:{number}: expected '<file>::<test>', got {line!r}")
        elif entry in entries:
            errors.append(f"{ALLOW_FILE}:{number}: {entry} is listed twice")
        else:
            entries.add(entry)
    return entries, errors


def worker_pass(now) -> None:
    """The pass of ``legacy.worker_pass``, counted as leaning on the fallback: the worker's loop serves only the hubs
    with their own database, so a test that runs it on the suite's businesses needs this one instead."""
    from base.tenancy import context
    from base.tenancy.tests import legacy

    context._leaning_on_the_fallback()
    legacy.worker_pass(now)


def _leanings() -> int:
    from base.tenancy import context

    return context._test_fallback_entries


@dataclass
class _Seen:
    """What the run saw of a listed test: its cases selected, the ones done, and whether all passed and any leaned."""

    cases: int
    complete: bool
    done: int = 0
    passed: bool = True
    leaned: bool = False

    def is_stale(self) -> bool:
        return self.complete and self.done == self.cases and self.passed and not self.leaned


class LegacyAllow:
    def __init__(self, config: pytest.Config) -> None:
        allow = config.rootpath / ALLOW_FILE
        self.allowed, errors = parse_allow(allow.read_text(encoding="utf-8") if allow.is_file() else "")
        if errors:
            raise pytest.UsageError("\n".join(errors))
        self.narrowed = any("::" in arg for arg in config.args)
        self.on_a_worker = hasattr(config, "workerinput")
        self.partial: set[str] = set()
        self.cases: Counter[str] = Counter()
        self.seen: dict[str, _Seen] = {}
        self.stale: list[str] = []

    def pytest_deselected(self, items) -> None:
        self.partial.update(entry_of(item.nodeid) for item in items)

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        self.cases = Counter(entry_of(item.nodeid) for item in session.items)

    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_protocol(self, item: pytest.Item, nextitem):
        from base.tenancy import context
        from base.tenancy.tests.legacy import LEGACY

        context._test_fallback = LEGACY if entry_of(item.nodeid) in self.allowed else None
        item.stash[_LEANINGS_BEFORE] = _leanings()
        try:
            return (yield)
        finally:
            context._test_fallback = None

    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_makereport(self, item: pytest.Item, call):
        report = yield
        entry = entry_of(item.nodeid)
        if entry in self.allowed:
            report.legacy_fallback = {
                "entry": entry,
                "cases": self.cases[entry],
                "complete": entry not in self.partial,
                "leaned": _leanings() > item.stash[_LEANINGS_BEFORE],
            }
        return report

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        listed = getattr(report, "legacy_fallback", None)
        if listed is None:
            return
        seen = self.seen.setdefault(listed["entry"], _Seen(cases=listed["cases"], complete=listed["complete"]))
        seen.passed = seen.passed and not (report.failed or report.skipped)
        if report.when == "teardown":
            seen.done += 1
            seen.leaned = seen.leaned or listed["leaned"]

    def pytest_sessionfinish(self, session: pytest.Session) -> None:
        if self.on_a_worker or self.narrowed:
            return
        self.stale = sorted(entry for entry, seen in self.seen.items() if seen.is_stale())
        if self.stale:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED

    def pytest_terminal_summary(self, terminalreporter) -> None:
        if self.stale:
            terminalreporter.section(ALLOW_FILE)
            terminalreporter.line(STALE_TITLE)
            for entry in self.stale:
                terminalreporter.line(f"  {entry}")


def pytest_configure(config: pytest.Config) -> None:
    config.pluginmanager.register(LegacyAllow(config), "legacy_allow")
