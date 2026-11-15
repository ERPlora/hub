"""Python code stays clear of the mistakes ruff finds, besides the function limits.

Next to the limits tests/test_guardrails_lint.py describes, ruff checks the rule families E4, E7 and E9 (imports out of
place, statements that read wrong, code that cannot be read), F (an import or a variable left unused, a name never
defined, a key written twice), B (a closure that reads a loop variable late, a zip that silently drops what is left
over) and DJ (a nullable text field, a form that takes every field of its model). That test runs ruff over the code;
this one pins its configuration down.

What broke one of these rules when it came in is frozen in pyproject.toml's ``[tool.ruff.lint.per-file-ignores]``, one
entry per file with the rules it breaks. An entry that no longer silences anything fails here, and compared with where
the branch left origin/main the entries gain no file-and-rule pair: the list only shrinks. An entry may follow its code
into the package of the same name (``base/schemas.py`` into ``base/schemas/__init__.py`` or ``base/schemas/money.py``)
or into flat siblings named after it (``test_services.py`` into ``test_services_payments.py``). The ``noqa`` markers
that name one of these rules only shrink too, per rule, wherever they moved.

In tests a fixture comes back as an argument under the name it was imported with, so redefining a name (F811) is not
checked there, like the argument limits.
"""

import json
import re
import tomllib
from collections import Counter
from pathlib import Path

import pytest
from allow_list_base import REPO, file_at_base, git, grep_at_base
from test_guardrails_lint import PRODUCTION, PYTHON, RANGE_MARKER, TEST, grep_now, grown, rules_found, ruff

CONFIG = "pyproject.toml"
FAMILIES = ("B", "DJ", "E4", "E7", "E9", "F")
LIMITS = ("C901", "PLR0911", "PLR0912", "PLR0913", "PLR0915", "PLR0917")
# One whole rule of the families: F401 or E402, never a family alone, nor BLE001 or E501.
FAMILY_RULE = re.compile(f"({'|'.join(FAMILIES)})[0-9]+")
TEST_GLOBS = ("**/tests/**", "**/test_*.py", "**/conftest.py")
TEST_EXEMPTIONS = ["F811", "PLR0913", "PLR0917"]
GLOB = re.compile(r"[*?\[\]{}!]")
# A noqa that names codes, anywhere on its line; ruff reads noqa in any case.
NOQA_CODES = r"#[[:space:]]*[Nn][Oo][Qq][Aa][[:space:]]*:[^#]*"
NOQA = "# noqa"
NO_RULES_AT_BASE = (
    "ruff did not check these rules where the branch left origin/main: this is the commit that brings them and freezes "
    "what breaks them today"
)

RUFF_CONFIGURATION = {
    "target-version": "py314",
    "extend-exclude": ["migrations", "packages"],
    "force-exclude": True,
    "format": {"exclude": ["*"]},
    "lint": {
        "select": sorted([*FAMILIES, *LIMITS, "RUF100"]),
        "external": ["A002", "B018", "BLE001", "E402", "E731", "F401", "F403", "F405", "F811", "N801", "N802", "N803"],
        "mccabe": {"max-complexity": 10},
        "pylint": {"max-args": 5, "max-positional-args": 5, "max-branches": 12, "max-returns": 6, "max-statements": 50},
        "per-file-ignores": dict.fromkeys(TEST_GLOBS, TEST_EXEMPTIONS),
    },
}

FORM = """from django import forms

from base.models import Membership


class MembershipForm(forms.ModelForm):
    class Meta:
        model = Membership
        fields = "__all__"
"""


def ruff_config(text: str) -> dict:
    return tomllib.loads(text).get("tool", {}).get("ruff", {})


def current_config() -> dict:
    return ruff_config((REPO / CONFIG).read_text(encoding="utf-8"))


def frozen(config: dict) -> dict[str, list[str]]:
    """The per-file-ignores entries that name one file: what broke a rule there when it came in."""
    ignores = config.get("lint", {}).get("per-file-ignores", {})
    return {path: rules for path, rules in ignores.items() if not GLOB.search(path)}


def without_frozen(config: dict) -> dict:
    """The configuration with only the per-file-ignores that apply to a kind of file, never to one file."""
    lint = config.get("lint", {})
    ignores = {path: rules for path, rules in lint.get("per-file-ignores", {}).items() if GLOB.search(path)}
    return config | {"lint": lint | {"per-file-ignores": ignores}}


def pairs(entries: dict[str, list[str]]) -> set[tuple[str, str]]:
    return {(path, rule) for path, rules in entries.items() for rule in rules}


def python_files() -> set[str]:
    listed = git(REPO, "ls-files", "--cached", "--others", "--exclude-standard", "--", "*.py")
    assert listed.returncode == 0, listed.stderr
    return set(listed.stdout.split())


def entry_problems(entries: dict[str, list[str]], files: set[str]) -> list[str]:
    """What is wrong with each frozen entry: a path that is not a Python file of the repo, or a rule that is not one
    whole rule of the families."""
    problems = []
    for path, rules in sorted(entries.items()):
        if "/" not in path:
            problems.append(f"{path}: ruff reads a name without a folder as every file of that name; fix the file")
        elif path not in files:
            problems.append(f"{path}: no such Python file; move the entry with its code, or remove it")
        wrong = [rule for rule in rules if not FAMILY_RULE.fullmatch(rule)]
        problems += [f"{path}: {rule} is not one rule of {', '.join(FAMILIES)}" for rule in wrong]
    return problems


def inline_table(table: dict[str, list[str]]) -> str:
    return "{" + ", ".join(f"{json.dumps(key)} = {json.dumps(value)}" for key, value in table.items()) + "}"


def found_without_the_entries(entries: dict[str, list[str]]) -> set[tuple[str, str]]:
    """Each file-and-rule pair ruff finds in the frozen files once their entries are lifted."""
    if not entries:
        return set()
    kept = without_frozen(current_config())["lint"]["per-file-ignores"]
    lifted = f"lint.per-file-ignores = {inline_table(kept)}"
    result = ruff("check", "--output-format", "json", "--config", lifted, *entries)
    assert result.returncode in (0, 1), result.stderr
    findings = json.loads(result.stdout)
    return {(Path(found["filename"]).relative_to(REPO).as_posix(), found["code"]) for found in findings}


def unneeded(entries: dict[str, list[str]], found: set[tuple[str, str]]) -> list[str]:
    return [f"{path}: {rule}" for path, rule in sorted(pairs(entries) - found)]


def module_of(path: str) -> str:
    return path.removesuffix(".py").removesuffix("/__init__").replace("/", ".")


def follows(path: str, old: str) -> bool:
    """Whether ``path`` may hold code ``old`` held: the same module, one inside its package, or a flat sibling named
    after it."""
    module, before = module_of(path), module_of(old)
    return module == before or module.startswith((f"{before}.", f"{before}_"))


def gained(now: dict[str, list[str]], before: dict[str, list[str]]) -> list[str]:
    """The frozen pairs ``now`` holds that ``before`` did not, leaving out those that followed their code."""
    old = pairs(before)
    return [
        f"{path}: {rule}"
        for path, rule in sorted(pairs(now) - old)
        if not any(rule == old_rule and follows(path, old_path) for old_path, old_rule in old)
    ]


def family_codes(markers: list[str]) -> Counter[str]:
    """The rules of the families each noqa or range marker names."""
    codes = [code for marker in markers for code in re.findall(r"[A-Z]+[0-9]+", marker)]
    return Counter(code for code in codes if FAMILY_RULE.fullmatch(code))


@pytest.mark.parametrize(
    ("code", "rule"),
    [
        ("import os\n", "F401"),
        ("first = 1; second = 2\n", "E702"),
        ("double = lambda value: value * 2\n", "E731"),
        ("def paired(a, b):\n    return list(zip(a, b))\n", "B905"),
        (FORM, "DJ007"),
    ],
    ids=["F401", "E702", "E731", "B905", "DJ007"],
)
def test_each_family_finds_its_mistake(code, rule):
    assert rules_found(code, PRODUCTION) == [rule]


def test_redefining_a_name_counts_in_production_but_not_in_tests():
    twice = "def shop():\n    return 1\n\n\ndef shop():\n    return 2\n"
    assert rules_found(twice, PRODUCTION) == ["F811"]
    assert rules_found(twice, TEST) == []
    assert rules_found(twice, "apps/sale/conftest.py") == []


def test_layout_and_style_are_still_not_checked():
    code = f"import sys\nimport os\nvalue=1\nLONG = '{'a' * 120}'  \nprint(os, sys, value, LONG)\n"
    assert rules_found(code, PRODUCTION) == []


def test_the_ruff_configuration_is_exactly_the_rules_and_the_limits():
    """Excluding a folder, ignoring a rule everywhere or loosening a value would switch a check off for good: any change
    to the configuration shows here first, and no other file configures ruff. The entries of one file are the frozen
    ones, which the tests below keep shrinking."""
    assert without_frozen(current_config()) == RUFF_CONFIGURATION
    configs = git(REPO, "ls-files", "--cached", "--others", "--exclude-standard", "--", "*ruff.toml", "*pyproject.toml")
    assert configs.stdout.split() == [CONFIG]


def test_no_rule_leaves_the_selection():
    before = ruff_config(file_at_base(CONFIG) or "").get("lint", {}).get("select", [])
    assert sorted(set(before) - set(current_config()["lint"]["select"])) == []


def test_each_frozen_entry_names_a_file_and_whole_rules():
    assert entry_problems(frozen(current_config()), python_files()) == []


def test_each_frozen_entry_still_silences_something():
    entries = frozen(current_config())
    found = unneeded(entries, found_without_the_entries(entries))
    assert found == [], f"Frozen rules a file no longer breaks: remove them from {CONFIG}.\n" + "\n".join(found)


def test_the_frozen_entries_never_gain_one():
    before = ruff_config(file_at_base(CONFIG) or "")
    if not set(FAMILIES) <= set(before.get("lint", {}).get("select", [])):
        pytest.skip(NO_RULES_AT_BASE)
    found = gained(frozen(current_config()), frozen(before))
    assert found == [], "The frozen rules only shrink: fix the code instead of freezing it.\n" + "\n".join(found)


def test_the_noqa_markers_of_these_rules_never_grow():
    now = family_codes(grep_now(NOQA_CODES, *PYTHON) + grep_now(RANGE_MARKER, *PYTHON))
    before = family_codes(grep_at_base(NOQA_CODES, *PYTHON) + grep_at_base(RANGE_MARKER, *PYTHON))
    found = grown(now, before)
    assert found == [], "A new noqa for one of these rules: fix the code instead.\n" + "\n".join(found)


def test_a_rule_is_one_whole_rule_of_the_families():
    rules, others = ("F401", "E402", "E902", "B905", "DJ001"), ("F", "E4", "BLE001", "E501", "C901", "RUF100", "f401")
    assert [code for code in rules if not FAMILY_RULE.fullmatch(code)] == []
    assert [code for code in others if FAMILY_RULE.fullmatch(code)] == []


def test_a_frozen_entry_names_one_python_file_and_whole_rules():
    entries = {
        "base/assistant.py": ["F401"],
        "conftest.py": ["F401"],
        "base/gone.py": ["E731"],
        "base/auth.py": ["F", "BLE001", "C901", "RUF100"],
    }
    assert entry_problems(entries, {"base/assistant.py", "base/auth.py", "conftest.py"}) == [
        "base/auth.py: F is not one rule of B, DJ, E4, E7, E9, F",
        "base/auth.py: BLE001 is not one rule of B, DJ, E4, E7, E9, F",
        "base/auth.py: C901 is not one rule of B, DJ, E4, E7, E9, F",
        "base/auth.py: RUF100 is not one rule of B, DJ, E4, E7, E9, F",
        "base/gone.py: no such Python file; move the entry with its code, or remove it",
        "conftest.py: ruff reads a name without a folder as every file of that name; fix the file",
    ]


def test_an_entry_ruff_no_longer_needs_is_reported():
    entries = {"base/assistant.py": ["F401"], "base/files.py": ["B905", "B911"]}
    found = {("base/assistant.py", "F401"), ("base/files.py", "B911"), ("base/auth.py", "F401")}
    assert unneeded(entries, found) == ["base/files.py: B905"]


def test_only_the_entries_of_one_file_are_frozen():
    config = {"lint": {"select": ["F"], "per-file-ignores": {"**/tests/**": ["F811"], "base/auth.py": ["F401"]}}}
    assert frozen(config) == {"base/auth.py": ["F401"]}
    assert without_frozen(config) == {"lint": {"select": ["F"], "per-file-ignores": {"**/tests/**": ["F811"]}}}


def test_a_pair_new_to_the_list_is_gained_and_one_that_follows_its_code_is_not():
    before = {"base/schemas.py": ["F811"], "apps/sale/tests/test_services.py": ["B023"]}
    now = {
        "base/schemas/__init__.py": ["F811"],
        "base/schemas/money.py": ["F811"],
        "apps/sale/tests/test_services_payments.py": ["B023"],
        "base/schemas.py": ["F401", "F811"],
        "base/queries.py": ["F811"],
        "apps/sale/tests/test_servicesx.py": ["B023"],
        "apps/sale/tests/test_service.py": ["B023"],
        "base/__init__.py": ["F811"],
    }
    assert gained(now, before) == [
        "apps/sale/tests/test_service.py: B023",
        "apps/sale/tests/test_servicesx.py: B023",
        "base/__init__.py: F811",
        "base/queries.py: F811",
        "base/schemas.py: F401",
    ]


def test_the_noqa_markers_count_only_the_rules_of_the_families():
    markers = [
        f"import os  {NOQA}: F401",
        f"{NOQA}: E402, F403 - star import of the settings",
        f"def a():  {NOQA}: C901",
        f"x = 1  {NOQA}: BLE001",
        "# ruff: disable[B905]",
    ]
    assert family_codes(markers) == Counter({"F401": 1, "E402": 1, "F403": 1, "B905": 1})
