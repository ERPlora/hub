"""Python functions stay small and simple enough for a person to follow.

ruff checks every function against the limits: cyclomatic complexity 10 (C901), 50 statements (PLR0915), 12 branches
(PLR0912), 6 returns (PLR0911) and 5 arguments, in all or positional (PLR0913, PLR0917). In tests the argument limits do
not apply, because pytest hands fixtures over as arguments. The functions that were already over a limit when it came in
carry a ``# noqa: <rule>`` on their definition line, and RUF100 fails a ``noqa`` that no longer silences anything.

Those exceptions, and ESLint's suppressions of the TypeScript and Vue limits (eslint-suppressions.json), the block caps
of a Vue page included, only shrink: each rule keeps at most the exceptions it had where the branch left origin/main,
wherever they moved since, and no comment switches a limit off without being counted. A limit the branch's
eslint.config.js turns on and main's does not name yet has nothing to compare with: the change that turns it on freezes
what breaks it today.
"""

import json
import re
import subprocess
import sys
import tomllib
from collections import Counter

import pytest
from allow_list_base import REPO, file_at_base, git, grep_at_base

PRODUCTION = "base/probe.py"
TEST = "base/tests/test_probe.py"

LIMIT_RULES = frozenset({"C901", "PLR0911", "PLR0912", "PLR0913", "PLR0915", "PLR0917"})
ESLINT_LIMITS = ("complexity", "max-depth", "max-params", "max-lines-per-function", "vue/max-lines-per-block")
SUPPRESSIONS = "eslint-suppressions.json"
ESLINT_CONFIG = "eslint.config.js"
PYTHON = ("*.py", ":(exclude)*/migrations/*")
SCRIPTS = ("*.ts", "*.tsx", "*.vue", "*.js", "*.mjs", "*.cjs")
# A noqa on the line that opens a function, where ruff reports its limits, or alone on its line. A file-wide one, with
# the ruff or flake8 prefix, also counts after other text of a comment alone on its line. ruff reads noqa in any case.
FILE_WIDE = r"([Rr][Uu][Ff][Ff]|[Ff][Ll][Aa][Kk][Ee]8)[[:space:]]*:[[:space:]]*"
NOQA_MARKER = (
    rf"^[[:space:]]*(((async[[:space:]]+)?def[[:space:]].*)?#[[:space:]]*({FILE_WIDE})?|#.*#[[:space:]]*{FILE_WIDE})"
    r"[Nn][Oo][Qq][Aa][^#]*"
)
# A range suppression, `# ruff: disable[<codes>]` alone on its line, which silences its codes down to the matching
# `# ruff: enable[…]`.
RANGE_MARKER = r"^[[:space:]]*#[[:space:]]*[Rr][Uu][Ff][Ff][[:space:]]*:[[:space:]]*[Dd][Ii][Ss][Aa][Bb][Ll][Ee][[:space:]]*\[[^]]*\]"
# An ESLint directive: a comment that opens with `eslint`, `eslint-disable…` or `eslint-enable`.
ESLINT_COMMENT = r"(/\*|//|<!--)[[:space:]]*eslint(-disable(-next-line|-line)?|-enable)?[[:space:]][^*]*"
ESLINT_DIRECTIVE = re.compile(r"eslint(-disable(?:-next-line|-line)?|-enable)?\s(.*)")


def ruff(command: str, *args: str, code: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ruff", command, "--no-cache", *args],
        cwd=REPO,
        input=code,
        capture_output=True,
        text=True,
        check=False,
    )


def rules_found(code: str, path: str) -> list[str]:
    """The rules ruff reports for ``code`` linted as the file ``path``, with the repo's configuration."""
    result = ruff("check", "--output-format", "json", "--stdin-filename", path, "-", code=code)
    assert result.returncode in (0, 1), result.stderr
    return sorted(finding["code"] for finding in json.loads(result.stdout))


def branchy(name: str, branches: int, noqa: str = "") -> str:
    """A function whose cyclomatic complexity is ``branches`` + 1."""
    body = "".join(f"    if value == {index}:\n        value += 1\n" for index in range(branches))
    return f"def {name}(value):{noqa}\n{body}    return value\n"


def with_arguments(count: int) -> str:
    names = ", ".join(f"a{index}" for index in range(count))
    return f"def taking({names}):\n    return [{names}]\n"


def grep_now(pattern: str, *pathspecs: str) -> list[str]:
    """Each match of the extended regular expression in the working tree, new files included."""
    found = git(REPO, "grep", "--untracked", "-h", "-o", "-E", pattern, "--", *pathspecs)
    assert found.returncode in (0, 1), found.stderr
    return found.stdout.splitlines()


def after_noqa(marker: str) -> str:
    return re.split("noqa", marker, flags=re.IGNORECASE)[-1].lstrip()


def limit_codes(marker: str) -> list[str]:
    """The function limits a noqa marker names; ruff only reads codes written in capitals."""
    after = after_noqa(marker)
    return [code for code in re.findall(r"[A-Z]+[0-9]+", after) if code in LIMIT_RULES] if after.startswith(":") else []


def noqa_bypasses(markers: list[str]) -> list[str]:
    """A noqa without codes, which silences every rule; a `# ruff: noqa` that names no code or a limit; and any
    `# flake8: noqa`, which ruff takes as a file-wide exemption."""
    found = []
    for marker in markers:
        flake8 = re.search(r"flake8\s*:\s*noqa", marker, re.IGNORECASE) is not None
        file_wide = re.search(r"ruff\s*:\s*noqa", marker, re.IGNORECASE) is not None
        if flake8 or not after_noqa(marker).startswith(":") or (file_wide and limit_codes(marker)):
            found.append(marker)
    return found


def range_bypasses(markers: list[str]) -> list[str]:
    """Range suppressions that name one of the limits."""
    return [marker for marker in markers if LIMIT_RULES & set(re.findall(r"[A-Z]+[0-9]+", marker))]


def eslint_bypasses(comments: list[str]) -> list[str]:
    """ESLint directives that disable every rule, or that disable or reconfigure one of the limits."""
    found = []
    for comment in comments:
        match = ESLINT_DIRECTIVE.search(comment)
        if match is None:
            continue
        rules = re.split(r"(?:^|\s)--(?:\s|$)", re.sub(r"\s*(-->|\*/)\s*$", "", match.group(2)))[0]
        bare_disable = (match.group(1) or "").startswith("-disable") and not rules.strip()
        if bare_disable or any(rule in rules for rule in ESLINT_LIMITS):
            found.append(comment)
    return found


def noqa_counts(markers: list[str]) -> Counter[str]:
    return Counter(code for marker in markers for code in limit_codes(marker))


def suppression_counts(text: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for rules in json.loads(text).values():
        counts.update({rule: entry["count"] for rule, entry in rules.items() if rule in ESLINT_LIMITS})
    return counts


def comparable(counts: Counter[str], config: str, base_config: str) -> Counter[str]:
    """The exceptions of the limits there is something to compare with: those the base configuration already names,
    and those the current one does not name at all."""
    return Counter({rule: count for rule, count in counts.items() if rule not in config or rule in base_config})


def grown(now: Counter[str], before: Counter[str]) -> list[str]:
    return [
        f"{rule}: {now[rule]} exceptions, {before[rule]} where the branch left origin/main"
        for rule in sorted(now)
        if now[rule] > before[rule]
    ]


def test_every_python_function_stays_within_the_limits():
    result = ruff("check", "--output-format", "concise", ".")
    assert result.returncode == 0, (
        "Python functions over their limits, or a noqa that silences nothing any more (remove it):\n"
        + result.stdout
        + result.stderr
    )


def test_complexity_over_ten_fails_and_ten_passes():
    assert rules_found(branchy("simple_enough", 9), PRODUCTION) == []
    assert rules_found(branchy("too_complex", 10), PRODUCTION) == ["C901"]


def test_statements_branches_and_returns_have_their_limits():
    statements = "def long():\n" + "".join(f"    x{index} = {index}\n" for index in range(51)) + "    return x0\n"
    returns = "def many(value):\n" + "".join(f"    if value == {i}:\n        return {i}\n" for i in range(6)) + "    return -1\n"
    assert rules_found(statements, PRODUCTION) == ["PLR0915"]
    assert rules_found(returns, PRODUCTION) == ["PLR0911"]
    assert "PLR0912" in rules_found(branchy("branchy", 13), PRODUCTION)


def test_more_than_five_arguments_fail_in_production_but_not_in_tests():
    assert rules_found(with_arguments(5), PRODUCTION) == []
    assert rules_found(with_arguments(6), PRODUCTION) == ["PLR0913", "PLR0917"]
    assert rules_found(with_arguments(6), TEST) == []
    assert rules_found(with_arguments(6), "apps/sale/conftest.py") == []


def test_the_other_limits_still_apply_to_tests():
    assert rules_found(branchy("test_too_complex", 10), TEST) == ["C901"]


def test_a_noqa_that_silences_nothing_fails():
    assert rules_found(branchy("simple_enough", 9, noqa="  # noqa: C901"), PRODUCTION) == ["RUF100"]
    assert rules_found(branchy("too_complex", 10, noqa="  # noqa: C901"), PRODUCTION) == []


def test_only_these_limits_are_checked():
    assert rules_found("import os\nx=1;y = 2\n", PRODUCTION) == []


@pytest.mark.parametrize("path", ["apps/sale/migrations/0001_initial.py", "base/migrations/0002_probe.py"])
def test_migrations_are_left_out(path):
    assert rules_found(branchy("forwards", 12), path) == []


def test_ruff_never_formats_the_code():
    """The code keeps its own layout: ruff is here only for the limits, and an editor that formats with it on save
    must find nothing to format."""
    result = ruff("format", "--check", "--diff", "base/services/__init__.py")
    assert (result.returncode, result.stdout) == (0, ""), result.stdout[:2000] + result.stderr


def test_the_codes_of_a_noqa_marker_are_read_after_it():
    assert limit_codes("def _move(  # noqa: C901, PLR0913") == ["C901", "PLR0913"]
    assert limit_codes("def fixture(store):  # noqa: F811 - the fixture") == []
    assert limit_codes("# ruff: noqa: PLR0915") == ["PLR0915"]


def test_a_limit_switched_off_without_being_counted_is_found():
    markers = ["def a():  # noqa", "def b():  # noqa - reason", "# ruff: noqa", "# ruff: noqa: C901", "# flake8: noqa"]
    markers += ["# Flake8: NOQA: E501", "# ruff: noqa: F401", "def c():  # noqa: C901", "def d():  # noqa: E731"]
    assert noqa_bypasses(markers) == markers[:6]


def test_a_file_wide_noqa_written_after_another_comment_is_found(tmp_path):
    """ruff takes a `ruff: noqa` or `flake8: noqa` anywhere in a comment alone on its line, but not after code."""
    lines = ["# a note # ruff: noqa", "# see # flake8: noqa: C901", "# a note on noqa", "x = 1  # ruff: noqa"]
    (tmp_path / "probe.py").write_text("\n".join(lines) + "\n", encoding="utf-8")
    found = git(tmp_path, "grep", "--no-index", "-h", "-o", "-E", NOQA_MARKER, "--", "probe.py")
    assert noqa_bypasses(found.stdout.splitlines()) == lines[:2]


def test_a_range_suppression_of_a_limit_is_found():
    markers = ["# ruff: disable[C901]", "# ruff: disable[E501, PLR0912]", "# ruff: disable[E501]", "# RUFF: DISABLE[PLR0915]"]
    assert range_bypasses(markers) == [markers[0], markers[1], markers[3]]


def test_an_eslint_comment_that_switches_a_limit_off_is_found():
    comments = [
        "eslint-disable vue/one-component-per-file -- one throwaway host component per case ",
        "eslint-disable-next-line complexity",
        "eslint-disable-line max-params, max-depth -- reason",
        "eslint max-lines-per-function: off ",
        "eslint-disable ",
        "eslint-disable-next-line -- a reason but no rule",
        "eslint-enable vue/one-component-per-file ",
        "<!-- eslint-disable-next-line vue/no-v-html -->",
        "<!-- eslint-disable -->",
    ]
    assert eslint_bypasses(comments) == [*comments[1:6], comments[8]]


def test_exceptions_are_counted_per_rule_wherever_they_are():
    markers = ["def a(  # noqa: C901, PLR0913", "def b():  # noqa: C901", "def c():  # noqa: F811"]
    assert noqa_counts(markers) == Counter({"C901": 2, "PLR0913": 1})
    suppressions = {
        "a.vue": {"complexity": {"count": 2}, "max-params": {"count": 1}},
        "b.ts": {"complexity": {"count": 1}, "vue/one-component-per-file": {"count": 4}},
    }
    assert suppression_counts(json.dumps(suppressions)) == Counter({"complexity": 3, "max-params": 1})


def test_a_rule_may_lose_exceptions_and_move_them_but_never_gain_one():
    before = Counter({"C901": 2, "PLR0913": 1})
    assert grown(Counter({"C901": 1}), before) == []
    assert grown(Counter({"C901": 3, "PLR0911": 1}), before) == [
        "C901: 3 exceptions, 2 where the branch left origin/main",
        "PLR0911: 1 exceptions, 0 where the branch left origin/main",
    ]


def test_an_eslint_comment_that_switches_the_block_caps_of_a_vue_page_off_is_found():
    comments = ["<!-- eslint-disable vue/max-lines-per-block -->", "eslint-disable vue/max-lines-per-block ", "<!-- eslint-disable-next-line vue/no-v-html -->"]
    assert eslint_bypasses(comments) == comments[:2]


def test_the_block_caps_of_a_vue_page_are_counted_like_the_function_limits():
    suppressions = {"a.vue": {"vue/max-lines-per-block": {"count": 2}, "complexity": {"count": 1}}}
    assert suppression_counts(json.dumps(suppressions)) == Counter({"vue/max-lines-per-block": 2, "complexity": 1})


LIMITS_CONFIG = "export default [{ rules: { complexity: ['error', 15] } }];"
BLOCKS_CONFIG = "export default [{ rules: { complexity: ['error', 15], 'vue/max-lines-per-block': ['error'] } }];"


def test_a_limit_the_branch_turns_on_freezes_what_breaks_it_today():
    counts = Counter({"complexity": 3, "vue/max-lines-per-block": 30})
    assert comparable(counts, BLOCKS_CONFIG, LIMITS_CONFIG) == Counter({"complexity": 3})


def test_once_main_turns_a_limit_on_its_suppressions_only_shrink():
    counts = Counter({"complexity": 3, "vue/max-lines-per-block": 30})
    assert comparable(counts, BLOCKS_CONFIG, BLOCKS_CONFIG) == counts


def test_a_limit_the_config_does_not_name_is_compared_like_the_rest():
    assert comparable(Counter({"max-depth": 1}), LIMITS_CONFIG, LIMITS_CONFIG) == Counter({"max-depth": 1})


def test_no_function_limit_is_switched_off_without_being_counted():
    found = noqa_bypasses(grep_now(NOQA_MARKER, *PYTHON)) + range_bypasses(grep_now(RANGE_MARKER, *PYTHON))
    found += eslint_bypasses(grep_now(ESLINT_COMMENT, *SCRIPTS))
    assert not found, "Limits switched off by a comment instead of fixing the function:\n" + "\n".join(found)


def test_the_python_function_exceptions_never_grow():
    if "[tool.ruff.lint]" not in (file_at_base("pyproject.toml") or ""):
        pytest.skip("ruff's limits are not configured where the branch left origin/main: this is the commit that brings them")
    now = noqa_counts(grep_now(NOQA_MARKER, *PYTHON))
    found = grown(now, noqa_counts(grep_at_base(NOQA_MARKER, *PYTHON)))
    assert not found, "New `# noqa` for a function limit: fix the function instead.\n" + "\n".join(found)


def test_the_eslint_suppressions_never_grow():
    before = file_at_base(SUPPRESSIONS)
    if before is None:
        pytest.skip(f"there is no {SUPPRESSIONS} where the branch left origin/main: this is the commit that brings it")
    now = suppression_counts((REPO / SUPPRESSIONS).read_text(encoding="utf-8"))
    config = (REPO / ESLINT_CONFIG).read_text(encoding="utf-8")
    found = grown(comparable(now, config, file_at_base(ESLINT_CONFIG) or ""), suppression_counts(before))
    assert not found, f"New suppressions in {SUPPRESSIONS}: fix the function instead.\n" + "\n".join(found)


RUFF_CONFIGURATION = {
    "target-version": "py314",
    "extend-exclude": ["migrations", "packages"],
    "force-exclude": True,
    "format": {"exclude": ["*"]},
    "lint": {
        "select": ["C901", "PLR0911", "PLR0912", "PLR0913", "PLR0915", "PLR0917", "RUF100"],
        "external": ["A002", "B018", "BLE001", "E402", "E731", "F401", "F403", "F405", "F811", "N801", "N802", "N803"],
        "mccabe": {"max-complexity": 10},
        "pylint": {"max-args": 5, "max-positional-args": 5, "max-branches": 12, "max-returns": 6, "max-statements": 50},
        "per-file-ignores": {
            "**/tests/**": ["PLR0913", "PLR0917"],
            "**/test_*.py": ["PLR0913", "PLR0917"],
            "**/conftest.py": ["PLR0913", "PLR0917"],
        },
    },
}


def test_the_ruff_configuration_is_exactly_the_limits():
    """Excluding a folder, ignoring a rule or loosening a value would switch a limit off for good: any change to the
    configuration shows here first, and no other file configures ruff."""
    assert tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["ruff"] == RUFF_CONFIGURATION
    configs = git(REPO, "ls-files", "--cached", "--others", "--exclude-standard", "--", "*ruff.toml", "*pyproject.toml")
    assert configs.stdout.split() == ["pyproject.toml"]
