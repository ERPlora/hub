"""Code is read by people who have never seen the project's planning documents.

Comments, docstrings, test names and messages have to make sense on their own, so the code never points at a plan
section, a dated planning round, a delivery slice or phase, a task id, a dated plan or spec, or who asked for a change
and when. Their prose does not cite the codes of an internal audit or review, an issue of another of the project's
repositories, a piece of work by its label, a numbered decision or a flow of the old product or an entry of the
migration's register either, nor does it tell the code's history by its dates or how the work was done: the reader has
not seen them, so the reason or the fact that holds today is written out. A test title is read with the constants it
interpolates written out.
Markdown files are left out: they are where the plans live.
"""

import ast
import functools
import io
import re
import subprocess
import tokenize
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

# Built from its code point so that this file does not trip its own scan.
SECTION_SIGN = "\N{SECTION SIGN}"

INTERNAL_REFERENCE = re.compile(
    "|".join(
        (
            SECTION_SIGN + r" ?[0-9]",
            r"(Plan|PLAN)(-[A-Z]+)?(\.md)? ?" + SECTION_SIGN,
            r"(Plan|PLAN)(-[A-Z]+)?(\.md)? block [0-9]",
            r"[Rr](ondas?|ounds?) [0-9]{4}-[0-9]{2}",
            r"[Tt]ajada S?[0-9]",
            r"([Pp]hase|[Ff]ase) [0-9]",
            # The word boundary keeps an invoice series' number template (PREFIX-YYYY-NNNNNN) out of the task ids.
            r"\b(FIX|APP|CLOSE|MIG)-[A-Z0-9_]+-[A-Z0-9_-]+",
            r"BASE-G[0-9]+",
            r"([Pp]lan|[Ss]pec) 20[0-9]{2}-[0-9]{2}",
            r"docs/(plans|superpowers)/",
            r"Ioan('s [a-z]+)?,? \(?20[0-9]{2}-[0-9]{2}",
            r"\(Ioan[,)]",
        )
    )
)

# A delivery slice's label: alone in brackets, opening or closing a bracketed aside, after «since», «after» or
# «before», or as a span. The lowercase word or backtick after an opening label keeps data such as a tuple whose first
# item is the S3 backend, or a table named «S1» next to «Terrace A», out of it.
SLICE_LABEL = re.compile(
    r"\(S[0-9][a-z]?\)"
    r"|\(S[0-9][a-z]?[,;:] [a-z`]"
    r"|[,;] S[0-9][a-z]?\)"
    r"|\b([Ss]ince|[Aa]fter|[Bb]efore) S[0-9][a-z]?\b"
    r"|\bS[0-9][a-z]?[–-]S[0-9]"
)
SLICE_NAME = re.compile(r"S[0-9][a-z]?")

# In the invoicing apps S1 and S2 are the tax authority's kinds of subject operation: data, not slices.
TAX_KEY_DIRS = ("apps/invoice/", "apps/verifactu/")
TAX_KEYS = frozenset({"S1", "S2"})


def names_a_slice(path: str, line: str) -> bool:
    for match in SLICE_LABEL.finditer(line):
        tax_keys = path.startswith(TAX_KEY_DIRS) and set(SLICE_NAME.findall(match.group())) <= TAX_KEYS
        if not tax_keys:
            return True
    return False


# The end-to-end specs name their captures after the task that added them, and renaming those string literals would
# orphan the evidence already taken. There only comments and test titles are read.
E2E_DIR = "tests/e2e/"
E2E_SCRIPT_SUFFIXES = frozenset({".ts", ".js", ".mjs"})
COMMENT_OR_STRING = re.compile(r"""//.*|'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"|`(?:[^`\\]|\\.)*`""")
TEST_TITLE_OPENER = re.compile(r"\b(?:test|it|describe)(?:\.\w+)*\(\s*$")
# A test title that interpolates a constant (``${KEY}``) reads as if the constant's text were written in it.
SCRIPT_CONSTANT = re.compile(
    r"""^\s*(?:export\s+)?const\s+(?P<name>[A-Z][A-Z0-9_]*)\s*=\s*(?P<quote>['"`])(?P<value>[^'"`$\\\n]*)(?P=quote)""",
    re.MULTILINE,
)
INTERPOLATED_CONSTANT = re.compile(r"\$\{(?P<name>[A-Z][A-Z0-9_]*)\}")


def script_constants(text: str) -> dict[str, str]:
    return {match.group("name"): match.group("value") for match in SCRIPT_CONSTANT.finditer(text)}


def with_constants_written_out(title: str, constants: dict[str, str]) -> str:
    return INTERPOLATED_CONSTANT.sub(lambda match: constants.get(match.group("name"), match.group(0)), title)


# The codes of an internal audit or review: a finding's letter and number, a delivery lot, a review's numbered
# findings, points or items, a review named by its date, the lettered finding of a pull request's review, and the
# audit's own name and date. The same shape is data elsewhere (an invoice series, a capture key, a region), so they are
# only looked for in prose: comments, docstrings and test titles. A ruling of the Court of Justice has a year after a
# slash and is not one of them, and neither is a fiscal key such as R5 or S1, nor an issue of this repository alone.
AUDIT_CODE_SHAPES = (
    r"(?<![\w\[\^-])[A-Z]-(?:[0-9]{2}|[A-Z][0-9])(?!\w|/[0-9])",
    r"(?<![\w\[\^-])L[0-9]-[A-Z][0-9]?(?!\w|/[0-9])",
    r"\bUX-AUDIT-[0-9]+",
    r"\bVF-[0-9]+",
    r"\b[Aa]udit (?:of )?(?:2\b|20[0-9]{2}-)",
    r"\b[Rr]eview (?:of )?20[0-9]{2}-[0-9]{2}",
    r"\([Rr]eview [0-9]+(?:, [0-9]+)*\)",
    r"\([Ii]tems? [0-9]+(?:(?:, | and )[0-9]+)*\)",
    r"\b[Rr]eviews? of (?:[a-z]+#[0-9]+,? )?[A-Z][0-9]+\b",
    r"\b[Ff]indings? [0-9]+(?:(?:[–-]| and )[0-9]+)*\)",
)
AUDIT_CODE = re.compile("|".join(AUDIT_CODE_SHAPES))

# An issue of another of the project's repositories, or of the old product's, is a number the reader cannot look up
# from here, so the prose says what it was about instead: the short form that names another repository or an old
# module, the ``gh:`` form of the old product's repositories and the full form of a repository of either organisation.
# This repository's own issues (``hub#781``) stay, and so does an upstream project's issue in GitHub's full form
# (``vitest-dev/vitest#2920``), which anyone can open.
OTHER_REPO_ISSUE = re.compile(
    r"(?<![\w/.:@#-])gh:[\w.-]+#[0-9]"
    r"|(?<![\w/.:@#-])(?i:erplora)/(?!hub#)[\w.-]+#[0-9]"
    r"|(?<![\w/.:@#-])(?i:erplora-old)/[\w.-]+#[0-9]"
    r"|(?<![\w/.:@#-])(?!hub#)[A-Za-z][\w-]*#[0-9]"
)

# A piece of work named by a W or a V and its number, as in «tenancy W» or «until V generates them» followed by one or
# two digits: the reader cannot know what it was, so the prose states the fact. A version inside a header's name, a system check's id and the V8 engine
# are data, not work.
WORK_LABEL = re.compile(r"(?<![\w./-])(?:W[0-9]{1,2}|V(?!8\b)[0-9]{1,2})(?![\w-])")

# A decision of the old product's architecture records, by its number: the record is not in this repository, so the
# prose keeps the decision and drops the number. Four digits after the dash, as the records were numbered; a hotel's
# average daily rate («ADR 120») is not one.
OLD_DECISION = re.compile(r"\bADR-[0-9]{4}\b")

# An entry of the migration's register of what the old product did and the new one still lacked, named by an app's
# prefix, a G and a number: the register is not in this repository, so the prose names the behaviour.
MIGRATION_GAP = re.compile(r"(?<![\w-])[A-Z][A-Z0-9_]*-G[0-9]+\b")

# A note on how the work was done that the reader cannot follow: the tracking file, a task named by its id alone (a
# close, a fix or an app's task with a single word after the dash), the market survey's skill, a measure told by its day
# and the old product's screenshots, which are not in this repository. A capture key's template, whose task id goes on
# with a dash, names a file and stays.
PROCESS_NOTE = re.compile(
    r"\bTODO\.md\b"
    r"|(?<![\w-])(?:APP|FIX|CLOSE|MIG)-[A-Z][A-Z0-9_]*\b(?!-)"
    r"|\bmarket-decision\b"
    r"|\b[Mm]easured (?:on )?20[0-9]{2}-[0-9]{2}"
    r"|\bdocs/reference/"
)

# A planning document named in prose, the Hub's or the database's: the reader has not seen it, so the rule it fixed is
# written out. A capture key that only contains the word goes on after a dash and stays.
PLAN_DOCUMENT = re.compile(r"(?<![\w-])PLAN(?:-[A-Z]+|\.md)\b")

PROSE_ONLY_SCANS = (AUDIT_CODE, OTHER_REPO_ISSUE, WORK_LABEL, OLD_DECISION, MIGRATION_GAP, PROCESS_NOTE, PLAN_DOCUMENT)

# A flow is named by its id when a WORKBOOK defines it: this repository's (``### SALE-F01 …``), the SaaS's or the native
# app's, which live in their own repositories and are listed here by their prefixes. Any other flow id is the old
# product's, which the reader cannot look up, so the prose says what the flow does instead. The old modules wrote theirs
# in lower case and the old Hub's were quoted after ``old-hub`` and a colon.
WORKBOOK_FLOW_HEADING = re.compile(r"^### (?P<prefix>[A-Z][A-Z0-9_]*)-F[0-9]+\b", re.MULTILINE)
SAAS_AND_APP_FLOW_PREFIXES = frozenset(
    {"ACCOUNTS", "APPS", "ASSISTANT", "BILLING", "FISCAL", "HUBS", "PUBLIC", "WHATSAPP", "HUB_APP", "HUB_PERIPHERALS"}
)
FLOW_ID = re.compile(r"(?<![\w-])(?P<prefix>[A-Z][A-Z0-9_]*)-F[0-9]+\b|(?<![\w-])[a-z][a-z_]+-f[0-9]+\b|\bold-hub:")


@functools.cache
def workbook_flow_prefixes() -> frozenset[str]:
    listing = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "*WORKBOOK.md"],
        cwd=REPO,
        check=True,
        capture_output=True,
    ).stdout
    paths = [path for path in listing.decode().split("\0") if path]
    return frozenset(
        match.group("prefix")
        for path in paths
        for match in WORKBOOK_FLOW_HEADING.finditer((REPO / path).read_text(encoding="utf-8"))
    )


def names_an_old_flow(text: str) -> bool:
    known = workbook_flow_prefixes() | SAAS_AND_APP_FLOW_PREFIXES
    return any(match.group("prefix") not in known for match in FLOW_ID.finditer(text))


# The code's history told by its date: a day alone in brackets, or a day after «until», «before», «since» or «as of»
# with no word before them (they open a sentence, an aside or the line), so a rule «valid until» a day stays. The prose
# says what holds today instead. A day that shows a format (after «ISO», «8601» or «YYYY-MM-DD») is not history, and
# neither is one the file's code uses: that is the test's data, written as text or as year, month and day (JavaScript
# counts the months from 0).
DATED_HISTORY = re.compile(
    r"(?<!ISO )(?<!8601 )(?<!YYYY-MM-DD )\((?P<day>20[0-9]{2}-[0-9]{2}-[0-9]{2})\)"
    r"|(?:^|[^\w\s])\s*(?:[Uu]ntil|[Bb]efore|[Ss]ince|[Aa]s of) (?P<when>20[0-9]{2}-[0-9]{2}(?:-[0-9]{2})?)\b"
)


def uses_the_date(day: str, text: str, prose: dict[int, str]) -> bool:
    if text.count(day) > sum(line.count(day) for line in prose.values()):
        return True
    parts = [int(part) for part in day.split("-")]
    if len(parts) < 3:
        return False
    year, month, date = parts
    return any(re.search(rf"\b{year},\s*0?{number},\s*0?{date}\b", text) for number in (month, month - 1))


def tells_dated_history(line: str, text: str, prose: dict[int, str]) -> bool:
    return any(
        not uses_the_date(match.group("day") or match.group("when"), text, prose)
        for match in DATED_HISTORY.finditer(line)
    )


PATCH_SUFFIX = ".patch"
DOCKERFILE = "Dockerfile"
SCRIPT_SUFFIXES = frozenset({".ts", ".tsx", ".js", ".mjs", ".cjs", ".vue", PATCH_SUFFIX})
LINE_COMMENTS = {
    **dict.fromkeys(SCRIPT_SUFFIXES | {".scss"}, ("//",)),
    **dict.fromkeys((".sh", ".toml", ".yml", ".yaml", DOCKERFILE), ("#",)),
    ".ini": ("#", ";"),
    ".sql": ("--",),
}
BLOCK_COMMENTS = {
    **{
        suffix: {"/*": "*/"}
        for suffix in (".ts", ".tsx", ".js", ".mjs", ".cjs", PATCH_SUFFIX, ".css", ".scss", ".sql")
    },
    ".vue": {"/*": "*/", "<!--": "-->"},
    ".html": {"<!--": "-->", "{#": "#}", "{% comment %}": "{% endcomment %}"},
}
PATCH_HEADERS = ("+++", "---", "@@", "diff ", "index ")

CODE_SUFFIXES = frozenset(
    {
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".mjs",
        ".cjs",
        ".vue",
        ".sh",
        ".css",
        ".scss",
        ".html",
        ".toml",
        ".yml",
        ".yaml",
        ".sql",
        ".ini",
        # The comments a patch adds end up in the installed dependency, read like any other code.
        PATCH_SUFFIX,
    }
)


def is_code(path: str) -> bool:
    return Path(path).suffix in CODE_SUFFIXES or Path(path).name.startswith(DOCKERFILE)


def code_files() -> list[str]:
    """Tracked files plus new ones not ignored, so a reference is caught before its first commit.

    The submodules of ``packages/`` are listed as one entry each and are not files: their own repos scan them.
    """
    listing = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=REPO,
        check=True,
        capture_output=True,
    ).stdout
    paths = sorted({path for path in listing.decode().split("\0") if path})
    return [path for path in paths if is_code(path) and (REPO / path).is_file()]


def without_string_literals(line: str) -> str:
    """The line with its string literals emptied, except a test's title; comments stay whole."""
    if line.lstrip().startswith(("//", "/*", "*")):
        return line

    def keep_comment_and_title(match: re.Match) -> str:
        token = match.group(0)
        if token.startswith("//") or TEST_TITLE_OPENER.search(line[: match.start()]):
            return token
        return '""'

    return COMMENT_OR_STRING.sub(keep_comment_and_title, line)


def prose_lines(path: str, text: str) -> dict[int, str]:
    """Line number → the prose on it: its comments, its docstrings and its test titles."""
    if Path(path).name.startswith(DOCKERFILE):
        return marked_prose(DOCKERFILE, text)
    suffix = Path(path).suffix
    if suffix == ".py":
        return python_prose(text)
    return marked_prose(suffix, text)


def python_prose(text: str) -> dict[int, str]:
    lines = text.splitlines()
    try:
        tree = ast.parse(text)
        comments = [t for t in tokenize.generate_tokens(io.StringIO(text).readline) if t.type == tokenize.COMMENT]
    except (SyntaxError, tokenize.TokenError):
        # A file that does not parse yet is read whole rather than not at all.
        return dict(enumerate(lines, 1))
    prose = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for number in range(node.lineno, node.end_lineno + 1):
                prose[number] = lines[number - 1]
    for comment in comments:
        number = comment.start[0]
        prose[number] = prose.get(number, "") + " " + comment.string
    return prose


def marked_prose(kind: str, text: str) -> dict[int, str]:  # noqa: C901, PLR0912
    """The comments of a file whose comments are marked (``//``, ``/* */``, ``<!-- -->``, ``#``…) and, in a script,
    the titles of its tests; every other string literal is left out."""
    script = kind in SCRIPT_SUFFIXES
    quotes = "'\"`" if script else "'\""
    blocks = BLOCK_COMMENTS.get(kind, {})
    tokens = re.compile(
        "|".join(
            [re.escape(marker) + ".*" for marker in LINE_COMMENTS.get(kind, ())]
            + [re.escape(opener) for opener in blocks]
            + [rf"{q}(?:[^{q}\\]|\\.)*{q}" for q in quotes]
        )
    )
    patch = kind == PATCH_SUFFIX
    constants = script_constants(text) if script else {}
    prose = {}
    closer = None
    title_next = False
    for number, line in enumerate(text.splitlines(), 1):
        if patch:
            if line.startswith(PATCH_HEADERS):
                closer, title_next = None, False
                continue
            line = line[1:]
            # A hunk can start inside a doc comment, after its opener.
            if closer is None and line.lstrip().startswith("*"):
                prose[number] = line
                continue
        pieces = []
        position = 0
        while position < len(line):
            if closer:
                end = line.find(closer, position)
                if end < 0:
                    pieces.append(line[position:])
                    break
                pieces.append(line[position:end])
                position, closer = end + len(closer), None
                continue
            match = tokens.search(line, position)
            if not match:
                break
            token = match.group(0)
            if token in blocks:
                closer = blocks[token]
            elif token[0] not in quotes:
                pieces.append(token)
            elif script:
                before = line[: match.start()]
                if TEST_TITLE_OPENER.search(before) or (title_next and not before.strip()):
                    pieces.append(with_constants_written_out(token, constants))
            position = match.end()
        title_next = script and closer is None and bool(TEST_TITLE_OPENER.search(line))
        if pieces:
            prose[number] = " ".join(pieces)
    return prose


def internal_references(paths, root: Path = REPO) -> list[str]:
    found = []
    for path in paths:
        e2e_script = path.startswith(E2E_DIR) and Path(path).suffix in E2E_SCRIPT_SUFFIXES
        text = (root / path).read_text(encoding="utf-8", errors="replace")
        prose = prose_lines(path, text)
        for number, line in enumerate(text.splitlines(), 1):
            read = without_string_literals(line) if e2e_script else line
            said = prose.get(number, "")
            if (
                INTERNAL_REFERENCE.search(read)
                or INTERNAL_REFERENCE.search(said)
                or names_a_slice(path, read)
                or any(scan.search(said) for scan in PROSE_ONLY_SCANS)
                or names_an_old_flow(said)
                or tells_dated_history(said, text, prose)
            ):
                found.append(f"{path}:{number}: {line.strip()}")
    return found


def found_lines(found):
    return [int(line.split(":")[1]) for line in found]


def test_code_never_points_at_internal_plans():
    paths = code_files()
    expected = {"tests/test_no_internal_references.py", "Dockerfile", "patches/@ionic__vue@8.8.9.patch"}
    assert expected <= set(paths), "git ls-files listed no code"
    found = internal_references(paths)
    assert not found, (
        "Code that points at internal plans, rounds, slices, audits, other repositories' issues, work labels, the old"
        " product's flows, the migration's register or notes on how the work was done:\n" + "\n".join(found)
    )


@pytest.mark.parametrize(
    "path",
    [
        "Dockerfile",
        "docker/Dockerfile.dev",
        "base/services.py",
        "base/frontend/pages/FilesPage.vue",
        "tests/e2e/helpers.ts",
        "frontend/widget.tsx",
        "eslint.config.mjs",
        "babel.config.cjs",
        "docker/entrypoint.sh",
        "frontend/theme.scss",
        "pyproject.toml",
        ".github/workflows/deploy.yml",
        "base/templates/base/receipt.html",
        "pytest.ini",
        "patches/@ionic__vue@8.8.9.patch",
    ],
)
def test_every_kind_of_code_file_is_scanned(path):
    assert is_code(path)


@pytest.mark.parametrize("path", ["README.md", "base/WORKBOOK.md", "base/locale/es/LC_MESSAGES/django.po", "uv.lock"])
def test_documents_and_data_are_left_out(path):
    assert not is_code(path)
