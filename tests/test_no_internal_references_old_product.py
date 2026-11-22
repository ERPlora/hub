"""The scan's references to the old product: its numbered decisions, its flows and the migration's register."""

import pytest
from test_no_internal_references import (
    MIGRATION_GAP,
    OLD_DECISION,
    SAAS_AND_APP_FLOW_PREFIXES,
    found_lines,
    internal_references,
    names_an_old_flow,
    workbook_flow_prefixes,
)


@pytest.mark.parametrize(
    "text",
    [
        "0 = the plan includes none (ADR" + "-0474; there is no «unlimited»)",
        "The order the till spends vouchers in (the old module's tie-break, ADR" + "-0386).",
        "# ADR" + "-0183 (old SaaS, fiscal/desglose.py): N1/N2 carry no rate",
        "the shell pins Ionic's ios mode, ADR" + "-0143; md has the same rule",
    ],
)
def test_the_scan_catches_a_numbered_decision_of_the_old_product(text):
    assert OLD_DECISION.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "the hotel's average daily rate (ADR) of 120 € a night",
        "ADR 120 and an occupancy of 80 %",
        "the ADRs of the old product are not in this repository",
        "fixed by hub#781",
        "RD 1619/2012: the rectification of a simplified invoice is simplified",
        "a ticket F2 or its rectification (R5); the keys S1, S2 and E1",
    ],
)
def test_the_scan_leaves_rates_rulings_and_fiscal_keys_alone(text):
    assert not OLD_DECISION.search(text)


def test_a_numbered_decision_is_caught_in_prose_but_not_in_a_string(tmp_path):
    (tmp_path / "apps" / "sale").mkdir(parents=True)
    lines = (
        '"""Vouchers are spent oldest first (ADR' + '-0386)."""',
        'RECORD = "ADR' + '-0386"',
        "# 0 = none (ADR" + "-0474).",
    )
    (tmp_path / "apps" / "sale" / "vouchers.py").write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert found_lines(internal_references(["apps/sale/vouchers.py"], root=tmp_path)) == [1, 3]


def test_the_flows_that_stay_are_the_ones_the_workbooks_define():
    prefixes = workbook_flow_prefixes()
    assert {"BASE", "SALE", "CASH_REGISTER", "WHATSAPP_INBOX", "VERIFACTU"} <= prefixes
    assert not {"HUB", "HUB_SHELL", "APPOINTMENTS", "SCHEDULES"} & prefixes
    for prefix in prefixes | SAAS_AND_APP_FLOW_PREFIXES:
        assert not names_an_old_flow(f"the flow {prefix}-F01 of its WORKBOOK"), prefix


@pytest.mark.parametrize(
    "text",
    [
        "The outbound call of a step (WORKBOOK FLOW-F27; the old hub's HUB" + "-F94).",
        "How far back the notices go (old-hub" + ":HUB_SHELL-F66 told each one as it came).",
        "the manager override (HUB_SHELL" + "-F51; Square and Toast)",
        "The form of «Call another system» (WORKBOOK FLOW-F27; the old module's flows" + "-f16)",
        "the cases of its WORKFLOW (APPOINTMENTS" + "-F02, F13, F14)",
        "nothing of a demo reaches the AEAT (SAAS_PUBLIC" + "-F91)",
        "flow: SALE-F28 (REC_PELUQUERIA" + "-F15): the reproduction of hub#685",
        "the ready-made recipes (WORKBOOK FLOW-F33; the old module's FLOWS" + "-F05 and F06)",
        "the retention of the old Hub (old-hub" + ":crates/runtime/src/retention.rs)",
    ],
)
def test_the_scan_catches_a_flow_of_the_old_product(text):
    assert names_an_old_flow(text)


@pytest.mark.parametrize(
    "text",
    [
        "BASE-F12: a flow of the Hub's WORKBOOK",
        "CASH_REGISTER-F01 and WHATSAPP_INBOX-F13: flows of the apps' WORKBOOKs",
        "A business's own domain (HUBS-F17 of the SaaS) answers here",
        "the business suspended for an unpaid invoice (BILLING-F16 of the SaaS)",
        "the app's `save_download` (HUB_APP-F30), which writes them to the person's Downloads",
        "the capture `APP" + "-CART_CHECKOUT-CART_CHECKOUT-F12-employee-<width>`",
        "BASE-F114-RECOVER-1440, the capture of a recovery",
        "a hex digit, [0-9a-f], and the colour #a-f0",
        "the Wi-Fi network of the shop",
        "the capture `E2E-HUB-F94-<width>` and the file `e2e-flows-f16.png` name files",
    ],
)
def test_the_scan_leaves_the_living_flows_and_other_text_alone(text):
    assert not names_an_old_flow(text)


@pytest.mark.parametrize(
    "text",
    [
        "with the period «7 days», what was sold each day (SALE" + "-G01)",
        "STAFF" + "-G02, G03, G04: the old Home panels «Active staff» and «On leave today»",
        "the figures (STAFF" + "-G02–G04)",
        "# APPOINTMENT" + "-G01 — what the hub tells the team as it happens",
        "VERIFACTU" + "-G23 and G25: nothing of a demo ever reaches the real AEAT",
    ],
)
def test_the_scan_catches_an_entry_of_the_migrations_register(text):
    assert MIGRATION_GAP.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "SALE-F28 charges the ticket",
        "the phone falls back to 4G when the Wi-Fi drops",
        "a 5G modem",
        "the glass G2 of the bar",
        "fixed by hub#781",
        "the capture `E2E-SALE-G01-390` names a file",
    ],
)
def test_the_scan_leaves_flows_and_ordinary_text_alone_when_looking_for_the_register(text):
    assert not MIGRATION_GAP.search(text)


def test_an_old_flow_a_register_entry_and_a_process_note_are_caught_in_prose_but_not_in_data(tmp_path):
    (tmp_path / "apps" / "flow").mkdir(parents=True)
    lines = (
        '"""The outbound call (WORKBOOK FLOW-F27; old hub HUB' + '-F94)."""',
        'ORIGIN = "<!-- origen: old-hub' + ':HUB-F212 -->"',
        "# The figures of the Home (STAFF" + "-G02).",
        'KEY = "STAFF' + '-G02"',
        "# Every name fits (TODO" + ".md).",
        "# A business's own domain (HUBS-F17 of the SaaS), FLOW-F27 and SALE-F28.",
    )
    (tmp_path / "apps" / "flow" / "http.py").write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert found_lines(internal_references(["apps/flow/http.py"], root=tmp_path)) == [1, 3, 5]
