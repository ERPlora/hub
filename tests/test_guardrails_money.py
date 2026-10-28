"""Guardrail of how the server writes money (flow money-text): only ``base.business.money_text`` writes an amount with
its currency. Babel's ``format_currency`` skips CLDR's currency spacing and glues a code to the figure («PLN15.50»
where the browser writes «PLN 15.50»), and a symbol put next to a figure by hand (``get_currency_symbol``) is the same
mistake by another road (saas#1859 glued «€» so). A second formatter, or a copy of the fix, drifts from the first.

Static and fast, like ``tests/test_guardrails.py``: a pure function over source text, proven by a made-up offender (the
positive control), then run over ``base/``, ``control/`` and ``apps/`` outside ``tests/``.
"""

import ast
from pathlib import Path, PurePosixPath

HUB_DIR = Path(__file__).resolve().parent.parent
SOURCE_ROOTS = ("base", "control", "apps")
#: The one formatter of money of the server.
OWNER = PurePosixPath("base/business.py")
#: Babel's functions that write an amount with its currency, or the currency to glue by hand.
FORBIDDEN = frozenset({"format_currency", "get_currency_symbol"})


def money_offenses(source: str) -> list[str]:
    """Each use of ``FORBIDDEN`` in ``source``: imported, called or reached as an attribute (``numbers.format_currency``)."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            found += [f"{node.lineno}: import {alias.name}" for alias in node.names if alias.name in FORBIDDEN]
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN:
            found.append(f"{node.lineno}: .{node.attr}")
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN:
            found.append(f"{node.lineno}: {node.id}")
    return found


def _sources():
    for root in SOURCE_ROOTS:
        for path in sorted((HUB_DIR / root).rglob("*.py")):
            relative = PurePosixPath(path.relative_to(HUB_DIR).as_posix())
            if "tests" in relative.parts or relative == OWNER:
                continue
            yield relative, path.read_text(encoding="utf-8")


def test_the_check_catches_a_second_formatter_of_money():
    glued = "from babel.numbers import format_currency\n\ndef price(units):\n    return format_currency(units, 'PLN', locale='en')\n"
    by_attribute = "from babel import numbers\n\nprice = numbers.format_currency(1, 'PLN', locale='en')\n"
    by_hand = "from babel.numbers import format_decimal, get_currency_symbol\n\ntext = get_currency_symbol('PLN') + '1'\n"
    assert money_offenses(glued) == ["1: import format_currency", "4: format_currency"]
    assert money_offenses(by_attribute) == ["3: .format_currency"]
    assert money_offenses(by_hand) == ["1: import get_currency_symbol", "3: get_currency_symbol"]
    assert money_offenses("from base.business import money_text\n\ntext = money_text(1550, 'PLN')\n") == []


def test_only_base_business_writes_money():
    offenses = [f"{path}:{offense}" for path, source in _sources() for offense in money_offenses(source)]
    assert offenses == [], "write money with base.business.money_text (flow money-text):\n" + "\n".join(offenses)
