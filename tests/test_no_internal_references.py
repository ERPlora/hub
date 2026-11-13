"""Code is read by people who have never seen the project's planning documents.

Comments, docstrings, test names and messages have to make sense on their own, so the code never points at a plan
section, a dated planning round, a delivery slice or phase, a task id, a dated plan or spec, or who asked for a change
and when. Their prose does not cite the codes of an internal audit or review either: the reader has not seen it, so
the reason is written out. Markdown files are left out: they are where the plans live.
"""

import ast
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
            r"[Rr](onda|ound) [0-9]{4}-[0-9]{2}",
            r"[Tt]ajada S?[0-9]",
            r"([Pp]hase|[Ff]ase) [0-9]",
            # The word boundary keeps an invoice series' number template (PREFIX-YYYY-NNNNNN) out of the task ids.
            r"\b(FIX|APP|CLOSE|MIG)-[A-Z0-9]+-[A-Z0-9-]+",
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


def marked_prose(kind: str, text: str) -> dict[int, str]:
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
                    pieces.append(token)
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
            if (
                INTERNAL_REFERENCE.search(read)
                or names_a_slice(path, read)
                or AUDIT_CODE.search(prose.get(number, ""))
            ):
                found.append(f"{path}:{number}: {line.strip()}")
    return found


def test_code_never_points_at_internal_plans():
    paths = code_files()
    expected = {"tests/test_no_internal_references.py", "Dockerfile", "patches/@ionic__vue@8.8.9.patch"}
    assert expected <= set(paths), "git ls-files listed no code"
    found = internal_references(paths)
    assert not found, "Code that points at internal plans, rounds, slices or audits:\n" + "\n".join(found)


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


@pytest.mark.parametrize(
    "text",
    [
        "Voice and video calls (Plan " + SECTION_SIGN + "66)",
        "see PLAN-HUB " + SECTION_SIGN + "84",
        "PLAN.md" + SECTION_SIGN + "5",
        "the hub's file store (PLAN-HUB " + "block 7)",
        "the limits of " + SECTION_SIGN + "14.2",
        "register_apps --check (round 16, spec " + SECTION_SIGN + "4.3)",
        "The website's theme (round " + "2026-10-22)",
        "ronda " + "2026-11-10f",
        "tajada " + "S3",
        "Tajada " + "4",
        "register the apps, then wait (phase" + " 1)",
        "Phase" + " 2 of the tenancy",
        "Alcance MVP: fase" + " 1",
        "the tabs (FIX" + "-LAUNCH-TABS)",
        "await capture(page, 'APP" + "-BASE-9-panel')",
        "the second flow of APP" + "-INVOICE-3",
        "CLOSE" + "-ACCOUNTS-F06",
        "MIG" + "-HUB-12",
        "the sparkles of the Hub (BASE" + "-G132)",
        "Plan" + " 2026-10-22, decision 3",
        "spec" + " 2026-10-11",
        "docs" + "/plans/2026-10-22-fase-2-tenencia.md",
        "docs" + "/superpowers/specs/2026-10-10-knowledge.md",
        "// Regression (Ioan" + ", 2026-10-22): every keystroke re-rendered the form",
        "# Ioan" + " (2026-10-22): the copyright line is the platform's credit",
        "# Ioan" + "'s redesign (2026-10-22): the header invites to write",
        "the old Hub's `retention.rs`, Ioan" + " 2026-08-10",
    ],
)
def test_the_scan_catches_each_kind_of_reference(text):
    assert INTERNAL_REFERENCE.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "total = round(amount, 2)",
        "Plan the refund before the payment",
        "Section 5 of the AEAT schema",
        "the second round 2 of retries",
        "fixed by hub#781",
        "New number template; empty = PREFIX-YYYY-NNNNNN.",
        "BASE-F12: a flow of the Hub's WORKBOOK",
        "the subscription schedule's next phase",
        "the plan's price for 2026",
        "docs/api/openapi.json",
        "under Ioan's supervision",
        "the Plan block of the checkout",
    ],
)
def test_the_scan_leaves_ordinary_text_alone(text):
    assert not INTERNAL_REFERENCE.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "an app whose tables are still being made (S" + "3)",
        "A copy of the business's data (S" + "2b): none is ever made",
        "made, or making them failed (S" + "3, ``base.activation``)",
        "the reset (S" + "2b, the worker's emptying of a reset)",
        "a hub's model lives in its own database (S" + "5: there is no shared one)",
        "the size of the business's database (BASE-F40, S" + "2b)",
        "the review of hub#471 C1; S" + "3)",
        "never one without its own database, since S" + "5 there is no shared one",
        "Since S" + "5 there is no shared database",
        "the registry's events stay in control's after S" + "5 too",
        "a session opened before S" + "1's rule",
        "the tenancy's slices S" + "1–S" + "7",
        "S" + "2a-S" + "3 of the tenancy",
    ],
)
def test_the_scan_catches_a_slice_label(text):
    assert names_a_slice("base/services.py", text)


@pytest.mark.parametrize(
    "text",
    [
        '(S3, {"bucket_name": "erplora-hubs-pre"}),',
        'description="Its number or name (S1, Terrace A); empty = the first free number of the zone."',
        '["Barra 2 Bis", "S1", "S2", "S10", "Terraza A"]',
        "await snap(page, 'S3-on', width);",
        "S3 in AWS and the disk locally",
        "On S3, ``ListObjectsV2`` pages of a thousand keys",
        "S3's conditional write: written only if nobody has the key",
        "since 2026 every business keeps its own copies",
    ],
)
def test_the_scan_leaves_data_named_like_a_slice_alone(text):
    assert not names_a_slice("base/services.py", text)


def test_the_tax_authoritys_operation_keys_are_not_slices_in_the_invoicing_apps():
    subject = "a domestic sale is subject (S" + "1) at its rate"
    assert not names_a_slice("apps/invoice/platform.py", subject)
    assert not names_a_slice("apps/verifactu/xml.py", "the kinds of subject operation (S" + "1, S" + "2)")
    assert names_a_slice("base/services.py", subject)
    activation = "making them failed (S" + "3, ``base.activation``)"
    assert names_a_slice("apps/verifactu/tests/test_app_disable.py", activation)


def test_a_slice_label_is_named_by_file_and_line_but_a_tax_key_is_not(tmp_path):
    for folder in ("base", "apps/invoice"):
        (tmp_path / folder).mkdir(parents=True)
    label = '"""Never in production (S' + '5)."""'
    (tmp_path / "base" / "context.py").write_text(label + "\n", encoding="utf-8")
    (tmp_path / "apps" / "invoice" / "platform.py").write_text("# subject (S" + "1) at its rate\n", encoding="utf-8")
    found = internal_references(["base/context.py", "apps/invoice/platform.py"], root=tmp_path)
    assert found == [f"base/context.py:1: {label}"]


def test_an_end_to_end_spec_keeps_its_capture_keys_but_not_its_comments(tmp_path):
    spec = tmp_path / "tests" / "e2e" / "some.spec.ts"
    spec.parent.mkdir(parents=True)
    lines = (
        "// The flows of the people (@TASK) at three sizes",
        "const KEY = '@FIX';",
        'const atEverySize = captureAtEverySize("@TASK");',
        "await capture(page, `@TASK-${key}-${vp.label}`);",
        " * a capture `@TASK-<key>-<size>` stays for the eye",
        "test('@FIX: the panel opens', async ({ page }) => {",
        "test.describe(`@TASK review`, () => {",
        "await go('http://localhost/'); // the @PHASE page",
        "await shot('a'); // it's @FIX, isn't it",
    )
    text = "\n".join(lines).replace("@TASK", "APP" + "-BASE-9").replace("@FIX", "FIX" + "-HUB-SOME-KEY")
    spec.write_text(text.replace("@PHASE", "fase" + " 2") + "\n", encoding="utf-8")
    found = internal_references(["tests/e2e/some.spec.ts"], root=tmp_path)
    assert [line.split(":")[1] for line in found] == ["1", "5", "6", "7", "8", "9"]


def test_outside_the_end_to_end_specs_a_string_literal_is_read_too(tmp_path):
    (tmp_path / "base").mkdir()
    (tmp_path / "base" / "keys.ts").write_text("const KEY = 'FIX" + "-HUB-SOME-KEY';\n", encoding="utf-8")
    (tmp_path / "tests" / "e2e").mkdir(parents=True)
    (tmp_path / "tests" / "e2e" / "seed.py").write_text('"""The seed (APP' + '-BASE-2)."""\n', encoding="utf-8")
    found = internal_references(["base/keys.ts", "tests/e2e/seed.py"], root=tmp_path)
    assert [line.split(":")[0] for line in found] == ["base/keys.ts", "tests/e2e/seed.py"]


def test_a_patch_comment_that_points_at_a_plan_is_caught(tmp_path):
    patch = "patches/@scope__package@1.0.0.patch"
    (tmp_path / "patches").mkdir()
    comment = "+         * ERPlora patch: the queue of PLAN-HUB " + SECTION_SIGN + "84."
    (tmp_path / patch).write_text("+        /**\n" + comment + "\n+         */\n", encoding="utf-8")
    assert is_code(patch)
    assert internal_references([patch], root=tmp_path) == [f"{patch}:2: {comment}"]


def test_each_reference_is_named_by_file_and_line(tmp_path):
    (tmp_path / "clean.py").write_text("total = round(amount, 2)\n", encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("FROM python\n# see PLAN " + SECTION_SIGN + "3\n", encoding="utf-8")
    assert internal_references(["clean.py", "Dockerfile"], root=tmp_path) == [
        "Dockerfile:2: # see PLAN " + SECTION_SIGN + "3"
    ]


@pytest.mark.parametrize(
    "text",
    [
        "a wrong current password is said in the panel's words (audit 2 R-26)",
        "a failure is said with «Retry» (audit 2026-10-14, R-04/R-08)",
        "as with the SSE down in the audit of 2026-10-14",
        "the dialog behind as deep as FormModal says (UX audit U-90)",
        "every target is 44 px (W-F6, W-13 of the mockups)",
        "for that business (UX-AUDIT-4 W-F2/X-03/V-37)",
        "lives in a landmark of its own (S-05: axe `region`)",
        "the long value wraps inside the card (W-19)",
        "the views of the account plane (hubs 0007, L1-A2)",
        "the Account page's models (0006, L3-A)",
        "a downgrade waits for the end of the period (review of L3-C)",
        "the safety net of unpaid plans (lot L2-B)",
        "not Las Palmas: no 0 % by a guess (finding 1)",
        "WCAG 1.4.4 (audit R-02): no maximum-scale",
        "the page's clock on the server's time (review of 2026-10-15, finding 8)",
        "Review of 2026-10-15, finding 4: «System» is only the system",
        "the switch is the operation's alone (review 2026-10-15, item 3)",
        "describe('FlowEditor: review 2026-10-15', () => {",
        "it never counts «until now» (review of 2026-10-15, findings 1–3)",
        "Migration 0002 of the attendance app (findings 4 and 7)",
        "a race that only bites now and then (review 3)",
        "What the till cannot charge is not offered (review 4, 9)",
        "the tasks of its active apps on its own scope (review of hub#471, C1)",
        "on that database and on its scope (review of hub#471 C1)",
        "a move, started or not (reviews of W8, rounds 2 and 3)",
        "a business of the Canary Islands declares IGIC (TAX-F11, VF-17)",
        "the switch is saved by «set_enabled», after the document (item 3)",
        "what an automation may never do (items 1 and 2)",
    ],
)
def test_the_scan_catches_each_kind_of_audit_code(text):
    assert AUDIT_CODE.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "treated as VAT-included (TJUE *Tulică* C-249/12 and C-250/12)",
        "CJEU C-375/15 (BAWAG): the email is the notice",
        "the ruling in case C-41/14",
        "the invoice A-1 of the series A is cancelled",
        "New number template; empty = PREFIX-YYYY-NNNNNN.",
        "BASE-F12: a flow of the Hub's WORKBOOK",
        "SALES-F03 charges the ticket",
        "fixed by hub#781",
        "decoded as UTF-8, dated as ISO-8601",
        "a COVID-19 surcharge",
        "the characters [A-Z0-9] and [^A-Z0-9]",
        "the audit log keeps 90 days",
        "the audit entries older than 90 days",
        "after finding 3 rows the loop stops",
        "a ticket F2 or its rectification (R5); the rectifying invoices R1–R5",
        "a domestic sale is subject (S" + "1) at its rate",
        "RD 1619/2012: the rectification of a simplified invoice is simplified",
        "the regions PT-20 and ES-MD",
        "staff is no more than anyone there (review of hub#490)",
        "a deadlock, review of hub#61: a route locks the route it replaces",
        "the manager reviews 2 corrections a day",
        "a review of the order before it is paid",
        "the worker's review has run yet (every quarter of an hour)",
        "the cart keeps each item 3 days",
        "a menu of 4 items (2 dishes and 2 drinks)",
    ],
)
def test_the_scan_leaves_rulings_series_and_flows_alone(text):
    assert not AUDIT_CODE.search(text)


def found_lines(found):
    return [int(line.split(":")[1]) for line in found]


def test_an_audit_code_is_caught_in_python_prose_but_not_in_its_data(tmp_path):
    (tmp_path / "apps" / "invoice").mkdir(parents=True)
    lines = (
        '"""The numbers of the invoices (lot L3-C)."""',
        'SERIES = "A-1"',
        "# W-19: the toolbar measures its own row.",
        'note = CharField(help_text="kept as it was (review of L2-A)")',
        "",
        "",
        "def test_the_first_name_is_required():",
        '    """Audit 2 S-10: a blank first name',
        '    was saved (finding 1)."""',
        '    sent = "<sum1:NumSerieFactura>A-1</sum1:NumSerieFactura>"',
        "    return sent  # VAT-inclusive (TJUE C-249/12 and C-250/12)",
    )
    (tmp_path / "apps" / "invoice" / "numbers.py").write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert found_lines(internal_references(["apps/invoice/numbers.py"], root=tmp_path)) == [1, 3, 8, 9]


def test_an_audit_code_is_caught_in_a_script_comment_or_test_title_but_not_in_a_capture_key(tmp_path):
    spec = tmp_path / "tests" / "e2e" / "some.spec.ts"
    spec.parent.mkdir(parents=True)
    lines = (
        "// The toolbar on one line (audit 2026-10-14, R-14).",
        "const series = 'A-1';",
        "const key = 'R-05';",
        "it('waits for an address (audit 2 R-32)', () => {",
        "  expect(key).toBe(series); /* W-F2 */ expect(1).toBe(1);",
        "});",
        "test(",
        "  'refused (R-05): a toast says why',",
        "  async () => {",
        "    await capture(page, 'R-05-desktop'); // the capture keeps its key",
        "    /* the row is measured on its own box,",
        "       as the table fits its columns (W-19) */",
        "    const ruling = 'C-249/12'; // TJUE C-249/12",
        "  },",
        ");",
    )
    spec.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert found_lines(internal_references(["tests/e2e/some.spec.ts"], root=tmp_path)) == [1, 4, 5, 8, 12]


def test_an_audit_code_is_caught_in_the_comments_of_a_component_a_template_and_a_patch(tmp_path):
    (tmp_path / "base" / "frontend").mkdir(parents=True)
    (tmp_path / "base" / "templates").mkdir(parents=True)
    (tmp_path / "patches").mkdir()
    (tmp_path / "base" / "frontend" / "Row.vue").write_text(
        "<template>\n"
        "  <!-- the Google row (U-63) -->\n"
        "  <p class=\"note\">{{ t('R-05') }}</p>\n"
        "</template>\n"
        '<script setup lang="ts">\n'
        "// The first name is required (audit 2 S-10).\n"
        'const series = "A-1";\n'
        "</script>\n"
        "<style scoped>\n"
        "/* 44 px targets on a phone\n"
        "   (W-F6, W-13 of the mockups) */\n"
        "</style>\n",
        encoding="utf-8",
    )
    (tmp_path / "base" / "templates" / "page.html").write_text(
        "{# The security lists (audit 2 R-10) #}\n"
        '<p data-series="A-1">R-02</p>\n'
        "<!-- R-02: no maximum-scale -->\n",
        encoding="utf-8",
    )
    (tmp_path / "patches" / "some-lib@1.0.0.patch").write_text(
        "diff --git a/dist/index.js b/dist/index.js\n"
        "--- a/dist/index.js\n"
        "+++ b/dist/index.js\n"
        "@@ -1,3 +1,4 @@\n"
        "   * one page at a time\n"
        "+  * and its title may wrap (R-25)\n"
        "+ const series = 'R-25';\n",
        encoding="utf-8",
    )
    found = internal_references(
        ["base/frontend/Row.vue", "base/templates/page.html", "patches/some-lib@1.0.0.patch"], root=tmp_path
    )
    assert [":".join(line.split(":")[:2]) for line in found] == [
        "base/frontend/Row.vue:2",
        "base/frontend/Row.vue:6",
        "base/frontend/Row.vue:11",
        "base/templates/page.html:1",
        "base/templates/page.html:3",
        "patches/some-lib@1.0.0.patch:6",
    ]


@pytest.mark.parametrize(
    ("path", "text"),
    [
        ("Dockerfile", 'FROM python\nENV SERIES="R-05"\n# the toolbar wraps (W-19)\n'),
        ("docker/Dockerfile.dev", 'ARG KEY="R-05"\n# the toolbar wraps (W-19)\n'),
        ("docker/entrypoint.sh", 'echo "R-05"\n# the toolbar wraps (W-19)\n'),
        (".github/workflows/deploy.yml", 'name: "R-05"\n# the toolbar wraps (W-19)\n'),
        ("pyproject.toml", 'key = "R-05"\n# the toolbar wraps (W-19)\n'),
        ("pytest.ini", "[pytest]\n; the toolbar wraps (W-19)\n"),
        ("base/sql/rows.sql", "SELECT 'R-05';\n-- the toolbar wraps (W-19)\n"),
        ("frontend/theme.css", '.a::after { content: "R-05"; }\n/* the toolbar wraps (W-19) */\n'),
        ("frontend/theme.scss", '$key: "R-05";\n// the toolbar wraps (W-19)\n'),
        ("frontend/widget.tsx", "const key = 'R-05';\n// the toolbar wraps (W-19)\n"),
        ("babel.config.cjs", "const key = 'R-05';\n/* the toolbar wraps (W-19) */\n"),
        ("eslint.config.mjs", "const key = 'R-05';\n// the toolbar wraps (W-19)\n"),
    ],
)
def test_an_audit_code_is_caught_in_the_comments_of_every_kind_of_code_file(tmp_path, path, text):
    (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / path).write_text(text, encoding="utf-8")
    assert found_lines(internal_references([path], root=tmp_path)) == [len(text.splitlines())]
