"""The scan's issues of other repositories and pieces of work named by a label."""

import pytest
from test_no_internal_references import OTHER_REPO_ISSUE, WORK_LABEL, found_lines, internal_references


@pytest.mark.parametrize(
    "text",
    [
        "the dishes of a menu hang from its header (kitchen#57)",
        "sales#522 and hub#1156: the kitchen gets the dishes the table chose",
        "a model reading a stranger's message (gh:appointments#143)",
        "the old checklist spoke English to a Spanish reader (gh:hub#868)",
        "the selection bar counts the rows in Spanish (ERPlora/ui#122)",
        "erplora-old/whatsapp_inbox#199: two numbers share their national digits",
        "the outbox has its section named in the staff's language (erplora/live#7)",
        "the till never charges twice (cash_register#12)",
        "a gateway that answers late (verifactu-gateway#4)",
        "the old board's rule (pm#43)",
        "the panel's login (saas#144, ui#20)",
        "a weight for set_enabled (live#53)",
        "the mail goes out through OVH (aws#67)",
        "the data table's columns (outfitkit#12)",
        "the vertical's templates (knowledge#3)",
    ],
)
def test_the_scan_catches_an_issue_of_another_repository(text):
    assert OTHER_REPO_ISSUE.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "fixed by hub#781",
        "the client never decides the script prefix (ERPlora/hub#2)",
        "Vitest looks at its clock only once it has returned (vitest-dev/vitest#2920)",
        "the theme's colour --bs-primary:#0b5cad",
        "the colour #0b5cad of the header",
        "a refund of a refund (#146)",
        "a ticket F2 or its rectification (R5); the rectifying invoices R1–R5",
        "the tax authority's keys S1, S2 and E1",
        "see https://www.rfc-editor.org/rfc/rfc9110#section-15",
        "the second table of https://example.org/spec.html#5.2",
        "the user @erplora#1 of the chat",
    ],
)
def test_the_scan_leaves_this_repositorys_issues_and_upstream_ones_alone(text):
    assert not OTHER_REPO_ISSUE.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "Edited by tenancy W10 (an exception to «an applied migration is never edited»)",
        "a person of the business's database (base.HubUser, W10)",
        "W10: the caller is a person of the business's database",
        "Written by hand, as the other apps', until V3 generates them from `/api/openapi.json`",
        "the op → route map the SDK's client uses (hand-written until V3).",
        "tests left broke the next tests, W8 2026-10-31",
        "the editor's image upload, as ImageUpload's `upload` (W3, @erplora/ui/components)",
        "the worker's lease (W9)",
    ],
)
def test_the_scan_catches_a_work_label(text):
    assert WORK_LABEL.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "silences Django's check W008 on purpose",
        "security.W004 is about HSTS",
        "the request carries X-Erplora-Signature-V2 over the path",
        "the W3C's rule for focus",
        "an address in IPv4 or IPv6",
        "keys are UUIDv7",
        "AWS SigV4 signs the request",
        "the version path /api/V2/ and the module api.V2",
        "the V8 engine collects it later",
        "reCAPTCHA v3 scores the request",
        "a ticket F2 or its rectification (R5)",
        "the tax authority's keys S1 and E1",
        "fixed by hub#781",
        "the capture W10-panel",
    ],
)
def test_the_scan_leaves_versions_and_check_ids_alone(text):
    assert not WORK_LABEL.search(text)


def test_another_repositorys_issue_and_a_work_label_are_caught_in_python_prose_but_not_in_its_data(tmp_path):
    (tmp_path / "apps" / "sale").mkdir(parents=True)
    lines = (
        '"""The dishes of a menu (kitchen#57)."""',
        'rehearsal = {"rows": [{"line": 1, "name": "Vino", "sku": "V1"}]}',
        "# A person of the business's database (base.HubUser, W10).",
        'LIVE = pytest.mark.xfail(strict=True, reason="ERPlora/live#53: no weight for set_enabled")',
        "# fixed by hub#781; the header X-Erplora-Signature-V2; Django's check W008",
        "",
        "",
        "def test_the_refund_of_a_refund():",
        '    """sales#131: a refund',
        '    of a refund (written by hand until V3)."""',
        '    return make_product("Wax", "W1")',
    )
    (tmp_path / "apps" / "sale" / "refunds.py").write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert found_lines(internal_references(["apps/sale/refunds.py"], root=tmp_path)) == [1, 3, 9, 10]


def test_another_repositorys_issue_and_a_work_label_are_caught_in_a_spec_but_not_in_its_capture_keys(tmp_path):
    spec = tmp_path / "tests" / "e2e" / "some.spec.ts"
    spec.parent.mkdir(parents=True)
    lines = (
        "// The selection bar counts the rows (ERPlora/ui#122).",
        "const KEY = 'kitchen#57-desktop';",
        "test('sales#131: the refund of a refund', async ({ page }) => {",
        "  await capture(page, 'W10-panel'); // the person of the business's database (W10)",
        "  await page.goto('/sale/#131'); // fixed by hub#781",
        "});",
        "describe(`the types written by hand until V3`, () => {});",
    )
    spec.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert found_lines(internal_references(["tests/e2e/some.spec.ts"], root=tmp_path)) == [1, 3, 4, 7]
