"""Guardrail of Sales' tests: a date or a time is taken when the test runs, never when its module is imported.

pytest imports every module first and runs the tests after, so a ``YEAR = timezone.localdate().year`` at module level
is the year of the collection: a run that crosses New Year's Eve (Madrid) expects last year's numbers while the till
numbers its documents with the year the operations take (``timezone.localdate()`` when they run), and the suite falls.
A test asks for the ``today`` fixture instead.

What runs at import: the bodies of modules and classes, decorators (``@pytest.mark.parametrize`` values included) and
default values. The body of a function or of a lambda runs with the test, so it may read the clock.
"""

import ast
from pathlib import Path

CLOCK_CALLS = frozenset({"localdate", "localtime", "now", "today", "utcnow"})
TESTS_DIR = Path(__file__).resolve().parent


class _ClockAtImport(ast.NodeVisitor):
    def __init__(self):
        self.lines: list[int] = []

    def visit_Call(self, node: ast.Call):
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name in CLOCK_CALLS:
            self.lines.append(node.lineno)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
        # The body runs with the test; the decorators and the default values, at import.
        for expr in (*node.decorator_list, *node.args.defaults, *node.args.kw_defaults):
            if expr is not None:
                self.visit(expr)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node: ast.Lambda):
        for expr in (*node.args.defaults, *node.args.kw_defaults):
            if expr is not None:
                self.visit(expr)


def clock_at_import(source: str) -> list[int]:
    """The lines of ``source`` that read the clock when the module is imported."""
    visitor = _ClockAtImport()
    visitor.visit(ast.parse(source))
    return sorted(visitor.lines)


def test_the_scanner_sees_the_clock_read_at_import():
    source = (
        "TODAY = timezone.localdate()\n"
        "DAY = dt.date.today().strftime('%Y%m%d')\n"
        "class TestTill:\n"
        "    stamp = timezone.now()\n"
        "@pytest.mark.parametrize('day', [timezone.localdate()])\n"
        "def test_a(day): ...\n"
        "async def test_b(at=dt.datetime.utcnow()): ...\n"
        "NUMBER = f'TICKET-{timezone.localdate().year}-000001'\n"
        "OPENING = timezone.localtime().replace(hour=9)\n"
    )
    assert clock_at_import(source) == [1, 2, 4, 5, 7, 8, 9]


def test_the_scanner_lets_a_test_read_the_clock_when_it_runs():
    source = (
        "def test_a():\n"
        "    today = timezone.localdate()\n"
        "async def test_b():\n"
        "    now = timezone.now()\n"
        "class TestTill:\n"
        "    def test_c(self):\n"
        "        assert dt.date.today()\n"
        "later = lambda: timezone.localdate()\n"
        "@pytest.fixture\n"
        "def today():\n"
        "    return timezone.localdate()\n"
    )
    assert clock_at_import(source) == []


def test_no_test_of_sales_reads_the_clock_at_import():
    files = sorted(TESTS_DIR.rglob("*.py"))
    assert Path(__file__).resolve() in files
    offenders = [
        f"{path.relative_to(TESTS_DIR)}:{line}" for path in files for line in clock_at_import(path.read_text())
    ]
    assert offenders == []
