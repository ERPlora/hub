"""The scan's references to plans: their sections, rounds, slices, phases and task ids, and the planning documents named
in prose."""

import pytest
from test_no_internal_references import (
    INTERNAL_REFERENCE,
    PLAN_DOCUMENT,
    SECTION_SIGN,
    internal_references,
    names_a_slice,
)


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
        "on the Home's bell (PLAN-HUB rounds " + "2026-10-21 and 2026-10-23)",
        "the public website's stylesheet (apps/website, rounds " + "2026-10-22)",
        "rondas " + "2026-10-27 y 2026-11-07",
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
        "Cash register's hooks of the Home (FIX" + "-CASH_REGISTER-SETUP-HOOKS)",
        "Captures: `APP" + "-CART_CHECKOUT-CART_CHECKOUT-F12-employee-<width>`",
        "each flow's screen (APP" + "-WHATSAPP_INBOX-1-<flow>-390)",
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
        "CASH_REGISTER-F01 and WHATSAPP_INBOX-F13: flows of the apps' WORKBOOKs",
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


@pytest.mark.parametrize(
    "text",
    [
        "Sales asks Printing for its paper by name (PRINTING-F07; PLAN-HUB «El cobro y la impresión»)",
        "as the hub databases are named (``hub_<hex>``, PLAN-DB)",
        "nothing activates a hub's (PLAN-HUB), so an hour read on it is an hour",
        "the rule of PLAN.md on the order of the work",
        "as a till's quantity field does (PLAN-SAAS: what is typed is not grouped)",
    ],
)
def test_the_scan_catches_a_planning_document_named_in_prose(text):
    assert PLAN_DOCUMENT.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "the right's source is PLAN, PURCHASE or FREE",
        "the capture `FIX" + "-HUB-BASE-PLAN-SPACE-CHECK-<width>` names a file",
        "the plan's price for 2026",
        "Plan the refund before the payment",
    ],
)
def test_the_scan_leaves_the_word_plan_alone_when_it_names_no_document(text):
    assert not PLAN_DOCUMENT.search(text)
