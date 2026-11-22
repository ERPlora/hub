"""The scan's codes of an internal audit or review, looked for in the prose of every kind of code file."""

import pytest
from test_no_internal_references import AUDIT_CODE, found_lines, internal_references


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
