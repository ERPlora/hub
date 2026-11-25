"""The series erplora.com numbers on ERPlora's own business (INVOICE-F23): nobody issues in ERP or ERPR by hand, nor makes,
changes or is offered them, by any door; what erplora.com issued is corrected there. In any other business a series of
those codes is one like the rest.

ERPlora's own business is business A here, as in ``test_platform_invoices.py``: real VeriFactu, no mocks.
"""

import copy
import json
from types import SimpleNamespace

import pytest
from django.utils import translation
from live import assistant as shared
from live.context import Scope
from live.errors import Conflict

from apps.flow.tests.conftest import make_flow
from apps.invoice.models import Invoice, InvoiceSeries
from apps.invoice.platform_series import platform_codes, refuse_platform_invoice, refuse_platform_series
from apps.invoice.tests.conftest import B, HUB_DB, HUB_DB_COMMITTED, ISSUER, A, ctx_for, deliver, run
from apps.invoice.tests.manual import LINE, RECIPIENT, manual
from apps.invoice.tests.test_platform import BODY, CREDIT_NOTE, line
from apps.invoice.tests.test_platform_invoices import code_of, committed_platform_hub, issue, platform_hub
from apps.sale.models import Sale
from apps.verifactu.models import Record
from base.tenancy.context import use_hub
from base.tenancy.tests.concurrency import at_once, meanwhile
from base.tests.test_services_assistant import answered

__all__ = ["committed_platform_hub", "platform_hub"]

CLOSED = "invoice.platform_series_closed"
KEPT = "invoice.platform_invoice_closed"
CODES = ["ERP", "ERPR"]

#: A subscription invoice without a tax ID: erplora.com's simplified one.
TICKET = {
    **copy.deepcopy(BODY),
    "id": "019a0000-0000-7000-8000-000000000009",
    "number": "ERP-2026-00130",
    "recipient": {**BODY["recipient"], "tax_id": ""},
}


def credit_note() -> dict:
    return {**copy.deepcopy(BODY), **copy.deepcopy(CREDIT_NOTE)}


def rows() -> dict:
    """What is written of ERPlora's series and documents, and how many series there are."""
    return {
        "series": list(InvoiceSeries.objects.order_by("code", "year").values()),
        "documents": list(Invoice.objects.order_by("number").values_list("series_code", "number")),
    }


def series(code: str) -> InvoiceSeries:
    return InvoiceSeries.objects.get(code=code)


@pytest.fixture
def born(platform_hub):
    """ERP and ERPR as erplora.com leaves them: an invoice and its credit note."""
    issue()
    issue(credit_note())


@pytest.fixture
def original(platform_hub) -> Invoice:
    issue()
    return Invoice.objects.get(platform_ref=BODY["id"])


# ── The rule ──────────────────────────────────────────────────────────────────────────────────────────────────────


def test_only_erploras_own_business_has_series_erplora_com_numbers(settings):
    settings.PLATFORM_HUB_SLUG, settings.PLATFORM_HUB_FORMER_SLUG = "erp", "erplora"
    assert platform_codes(Scope("host", "erp")) == ("ERP", "ERPR")
    assert platform_codes(Scope("host", "erplora")) == ("ERP", "ERPR")
    assert platform_codes(A) == platform_codes(B) == ()


@pytest.mark.parametrize("code", CODES)
def test_a_series_of_erplora_com_is_refused_on_its_own_business_alone(settings, code):
    settings.PLATFORM_HUB_SLUG = A.key
    with pytest.raises(Conflict) as refused:
        refuse_platform_series(A, code)
    assert refused.value.code == CLOSED
    refuse_platform_series(B, code)
    refuse_platform_series(A, "FACT")
    refuse_platform_series(A, f"{code}2")


def test_the_refusal_says_the_field_it_is_about(settings):
    settings.PLATFORM_HUB_SLUG = A.key
    with pytest.raises(Conflict) as refused:
        refuse_platform_series(A, "ERP", field="code")
    assert refused.value.fields == {"code": refused.value.message}


def test_only_an_invoice_of_erplora_com_is_closed_to_hand_corrections():
    with pytest.raises(Conflict) as refused:
        refuse_platform_invoice(SimpleNamespace(platform_ref=BODY["id"]))
    assert refused.value.code == KEPT
    refuse_platform_invoice(SimpleNamespace(platform_ref=None))


@pytest.mark.parametrize(
    ("language", "series_said", "invoice_said"),
    [
        (
            "en",
            "erplora.com numbers the ERP and ERPR series: use another series.",
            "erplora.com issued this invoice and corrects it, in its ERPR series: it cannot be corrected by hand here.",
        ),
        (
            "es",
            "Las series ERP y ERPR las numera erplora.com: usa otra serie.",
            "Esta factura la emitió erplora.com y allí se corrige, en su serie ERPR: aquí no se puede corregir a mano.",
        ),
    ],
)
def test_both_refusals_are_said_in_the_language_of_whoever_asks(settings, language, series_said, invoice_said):
    settings.PLATFORM_HUB_SLUG = A.key
    with translation.override(language):
        with pytest.raises(Conflict) as of_series:
            refuse_platform_series(A, "ERP")
        with pytest.raises(Conflict) as of_invoice:
            refuse_platform_invoice(SimpleNamespace(platform_ref=BODY["id"]))
    assert (of_series.value.message, of_invoice.value.message) == (series_said, invoice_said)


# ── Issuing by hand ───────────────────────────────────────────────────────────────────────────────────────────────


@HUB_DB
@pytest.mark.parametrize("code", ["ERP", "ERPR", "erp", " Erpr "])
def test_a_manual_invoice_cannot_choose_a_series_of_erplora_com_by_its_code(born, code):
    before = rows()
    assert code_of(lambda: manual(series_code=code)) == CLOSED
    assert rows() == before


@HUB_DB
@pytest.mark.parametrize("code", CODES)
def test_a_manual_invoice_cannot_choose_a_series_of_erplora_com_by_its_id(born, code):
    before = rows()
    assert code_of(lambda: manual(series_id=str(series(code).id))) == CLOSED
    assert rows() == before


@HUB_DB
def test_a_manual_invoice_does_not_open_this_years_series_of_erplora_com_from_the_last_ones(platform_hub, today):
    last = today.year - 1
    issue({**copy.deepcopy(BODY), "number": f"ERP-{last}-00123", "issued_on": f"{last}-10-15"})
    before = rows()
    assert code_of(lambda: manual(series_code="ERP")) == CLOSED
    assert rows() == before


@HUB_DB
def test_before_erplora_com_issues_anything_its_codes_are_already_closed(platform_hub):
    assert [code_of(lambda code=code: manual(series_code=code)) for code in CODES] == [CLOSED, CLOSED]
    assert rows() == {"series": [], "documents": []}


@HUB_DB
def test_without_a_series_a_manual_invoice_takes_the_businesss_own_whatever_is_default(born, today):
    # The platform's staff can still mark a row in the admin, which runs no operation.
    InvoiceSeries.objects.filter(code="ERP").update(is_default=True)
    assert manual().number == f"FACT-{today.year}-000001"
    assert series("ERP").current_number == 0


@HUB_DB
def test_every_way_of_issuing_by_hand_numbers_in_the_businesss_own_series(born, product, charge, today):
    """The till's ticket and invoice, the full invoice of a ticket, a refund, a void, a rectification and a manual one."""
    product()
    sale = charge("own-0001")
    ticket = Invoice.objects.get(source_sale_id=sale.id)
    run("invoice.invoice.substitute", {"number": ticket.number, **RECIPIENT})
    run(
        "sale.sale.refund",
        {
            "sale_id": str(sale.id),
            "reason": "Broken",
            "allocations": [{"payment_id": str(Sale.objects.get(pk=sale.id).payments.get().id), "amount": 500}],
        },
    )
    deliver("sale.sale.refunded")
    charge("own-0002", document_type="invoice", **RECIPIENT)
    by_hand = manual()
    run("invoice.invoice.rectify", {"number": by_hand.number, "reason": "Wrong price"})

    of_the_business = Invoice.objects.filter(platform_ref=None)
    assert {(doc.source_type, doc.series_code) for doc in of_the_business} == {
        ("sale", "TICKET"),
        ("sale", "FACT"),
        ("substitution", "FACT"),
        ("refund", "RECT"),
        ("manual", "FACT"),
        ("rectification", "RECT"),
    }
    assert {row.code: row.current_number for row in InvoiceSeries.objects.filter(year=today.year, code__in=CODES)} == {
        "ERP": 0,
        "ERPR": 0,
    }


# ── The series themselves ─────────────────────────────────────────────────────────────────────────────────────────


@HUB_DB
@pytest.mark.parametrize("code", ["ERP", "ERPR", "erp"])
@pytest.mark.parametrize("year", [2026, 2031])
def test_a_series_of_erplora_com_is_not_created_by_hand(platform_hub, code, year):
    with pytest.raises(Conflict) as refused:
        run("invoice.series.create", {"code": code, "invoice_type": "F1", "year": year, "prefix": "MINE"})
    assert (refused.value.code, set(refused.value.fields)) == (CLOSED, {"code"})
    assert rows()["series"] == []


@HUB_DB
@pytest.mark.parametrize("code", CODES)
@pytest.mark.parametrize(
    "change",
    [
        {"name": "Mine"},
        {"is_active": False},
        {"is_active": True},
        {"is_default": True},
        {"prefix": "MINE"},
        {"format": "{prefix}/{year}/{seq}"},
        {"next_number": 500},
        {},
    ],
)
def test_a_series_of_erplora_com_is_not_changed_by_hand(born, code, change):
    InvoiceSeries.objects.filter(code=code).update(is_active=change.get("is_active") is False)
    before = rows()
    assert code_of(lambda: run("invoice.series.update", {"series_id": str(series(code).id), **change})) == CLOSED
    assert rows() == before


@HUB_DB
@pytest.mark.parametrize(
    ("numbering", "field"),
    [
        ({"prefix": "ERP"}, "prefix"),
        ({"prefix": "ERPR"}, "prefix"),
        ({"prefix": "ERP", "format": "{prefix}-{year}-{seq:05d}"}, "format"),
        ({"format": "ERP-{year}-{seq:05d}"}, "format"),
        ({"prefix": "ER", "format": "{prefix}P-{year}-{seq:05d}"}, "format"),
    ],
)
def test_no_series_prints_the_numbers_of_erplora_com(platform_hub, numbering, field, today):
    """ERP-2026-00130 is erplora.com's invoice, whatever the code of the series that would print it."""
    new = {"code": "WEB", "invoice_type": "F1", "year": today.year}
    with pytest.raises(Conflict) as created:
        run("invoice.series.create", {**new, **numbering})
    assert (created.value.code, set(created.value.fields)) == (CLOSED, {field})

    web = run("invoice.series.create", new)
    with pytest.raises(Conflict) as changed:
        run("invoice.series.update", {"series_id": str(web.id), **numbering})
    assert changed.value.code == CLOSED
    assert set(changed.value.fields) <= set(numbering)
    assert (series("WEB").prefix, series("WEB").format) == ("WEB", "")


@HUB_DB
def test_nor_one_left_without_a_prefix(platform_hub, today):
    web = run("invoice.series.create", {"code": "WEB", "invoice_type": "F1", "year": today.year})
    numbering = {"prefix": "", "format": "{prefix}ERP-{year}-{seq:05d}"}
    assert code_of(lambda: run("invoice.series.update", {"series_id": str(web.id), **numbering})) == CLOSED


@HUB_DB
@pytest.mark.parametrize("prefix", ["ERPLORA", "ERP2", "XERP", "ERP-WEB", "WEB"])
def test_a_prefix_that_only_resembles_them_is_the_businesss_own(platform_hub, prefix, today):
    run("invoice.series.create", {"code": "WEB", "invoice_type": "F1", "year": today.year, "prefix": prefix})
    assert manual(series_code="WEB").number == f"{prefix}-{today.year}-000001"


@HUB_DB
@pytest.mark.parametrize("asked", [{}, {"search": "ERP"}, {"code": "ERP"}, {"code": "erpr"}, {"year": 2026}, {"is_active": True}])
def test_the_list_of_series_does_not_offer_the_ones_of_erplora_com(born, asked):
    run("invoice.series.create", {"code": "WEB", "invoice_type": "F1", "year": 2026, "name": "Sales of ERPlora, ERP"})
    listed = run("invoice.series.list", asked)
    assert {row.code for row in listed.rows} == (set() if "code" in asked else {"WEB"})
    assert listed.total == len(listed.rows)


@HUB_DB
@pytest.mark.parametrize("read", ["invoice.series.get", "invoice.series.peek_next"])
def test_the_next_number_of_a_series_of_erplora_com_is_never_made_up(born, read):
    """The Hub's counter of ERP stays at 0: «ERP-2026-00001» would be a number erplora.com gave long ago."""
    for code in CODES:
        assert code_of(lambda code=code: run(read, {"code": code, "year": 2026})) == CLOSED
        assert code_of(lambda code=code: run(read, {"series_id": str(series(code).id)})) == CLOSED


@HUB_DB
def test_the_numbering_of_the_business_is_only_its_own(born):
    status = run("invoice.numbering.status")
    assert (status.ordinary_series, status.rectifying_series, status.total_series, status.configured) == (0, 0, 0, False)
    run("invoice.series.create", {"code": "FACT", "invoice_type": "F1", "year": status.fiscal_year, "is_default": True})
    own = run("invoice.numbering.status")
    assert (own.ordinary_series, own.default_series, own.total_series) == (1, 1, 1)


# ── What erplora.com issued is corrected there ────────────────────────────────────────────────────────────────────


@HUB_DB
@pytest.mark.parametrize("operation", ["invoice.invoice.rectify", "invoice.invoice.rectification_preview"])
def test_an_invoice_of_erplora_com_is_not_rectified_by_hand(original, operation):
    assert code_of(lambda: run(operation, {"number": original.number, "reason": "Wrong price"})) == KEPT
    original.refresh_from_db()
    assert (original.status, Invoice.objects.count()) == (Invoice.Status.ISSUED, 1)
    assert not InvoiceSeries.objects.filter(code="RECT").exists()


@HUB_DB
def test_its_simplified_invoice_is_not_replaced_by_hand_either(platform_hub):
    issue(copy.deepcopy(TICKET))
    ticket = Invoice.objects.get()
    assert (ticket.invoice_type, ticket.series_code) == ("F2", "ERP")
    assert code_of(lambda: run("invoice.invoice.substitute", {"number": ticket.number, **RECIPIENT})) == KEPT
    assert code_of(lambda: run("invoice.invoice.rectify", {"number": ticket.number, "reason": "Wrong price"})) == KEPT
    assert list(Invoice.objects.values_list("number", flat=True)) == [ticket.number]


@HUB_DB
def test_neither_the_list_nor_the_page_of_its_invoices_offers_to_correct_them(platform_hub):
    issue()
    issue(copy.deepcopy(TICKET))
    run("invoice.series.create", {"code": "TICKET", "invoice_type": "F2", "year": 2026, "prefix": "T"})
    own = manual(series_code="TICKET", lines=[LINE])
    offered = {row.number: (row.can_rectify, row.can_substitute) for row in run("invoice.invoice.list").rows}
    assert offered == {"ERP-2026-00123": (False, False), "ERP-2026-00130": (False, False), own.number: (True, True)}
    for number, flags in offered.items():
        page = run("invoice.invoice.get", {"number": number})
        assert (page.can_rectify, page.can_substitute) == flags


@HUB_DB
def test_its_credit_note_still_rectifies_it(original):
    issue(credit_note())
    original.refresh_from_db()
    credit = Invoice.objects.get(series_code="ERPR")
    assert (credit.rectifies, original.status) == (original, Invoice.Status.CANCELLED)
    assert code_of(lambda: run("invoice.invoice.rectify", {"number": credit.number, "reason": "x"})) == KEPT


@pytest.fixture
def served(born, hub_a):
    """ERPlora's own business answers at its address: its row is the platform's."""
    hub_a.is_platform = True
    hub_a.save(update_fields=["is_platform"])


# ── Every door ────────────────────────────────────────────────────────────────────────────────────────────────────


def attempts() -> list[tuple[str, dict]]:
    """What a person, the assistant, a key or an automation could try on ERP and ERPR."""
    return [
        ("invoice.invoice.create", {"lines": [LINE], **RECIPIENT, "series_code": "ERP"}),
        ("invoice.invoice.create", {"lines": [LINE], **RECIPIENT, "series_id": str(series("ERP").id)}),
        ("invoice.series.create", {"code": "ERPR", "invoice_type": "R1", "year": 2027}),
        ("invoice.series.update", {"series_id": str(series("ERP").id), "is_default": True}),
        ("invoice.series.update", {"series_id": str(series("ERPR").id), "name": "Mine"}),
    ]


ROUTES = {
    "invoice.invoice.create": "/api/invoice/invoices",
    "invoice.series.create": "/api/invoice/series",
    "invoice.series.update": "/api/invoice/series/update",
}


def post(client, path: str, data: dict, **headers):
    return client.post(path, json.dumps(data), content_type="application/json", HTTP_HOST=f"{A.key}.localhost", **headers)


@HUB_DB
@pytest.mark.parametrize("role", ["hub_owner", "hub_admin", "hub_manager"])
def test_the_api_refuses_it_to_whoever_signs_in_and_says_why_in_their_language(served, client, make_user, role):
    client.force_login(make_user("boss", role=role))
    before = rows()
    for operation, data in attempts():
        answer = post(client, ROUTES[operation], data, HTTP_ACCEPT_LANGUAGE="es")
        assert (answer.status_code, answer.json()["error"]["code"]) == (409, CLOSED), (operation, answer.content)
        assert answer.json()["error"]["message"] == "Las series ERP y ERPR las numera erplora.com: usa otra serie."
    assert rows() == before


@HUB_DB
def test_an_api_key_issues_and_changes_nothing_there(served, client, make_user):
    client.force_login(make_user("boss", role="hub_owner"))
    made = post(client, "/api/keys", {"name": "Integration", "rate_per_minute": 60, "scopes": {"*": ["read", "create", "update"]}})
    assert made.status_code == 200, made.content
    client.logout()
    key = {"HTTP_AUTHORIZATION": f"Bearer {made.json()['token']}"}
    before = rows()
    for operation, data in attempts():
        assert post(client, ROUTES[operation], data, **key).status_code in (401, 403), operation
    listed = client.get("/api/invoice/series/peek_next", {"code": "ERP", "year": 2026}, HTTP_HOST=f"{A.key}.localhost", **key)
    assert (listed.status_code, listed.json()["error"]["code"]) == (409, CLOSED)
    assert rows() == before


@HUB_DB
def test_the_assistant_is_told_why_and_nothing_changes(born):
    def turn(*calls, decision=None):
        said = {"role": "user", "content": "hazlo en la serie ERP"}
        asked = {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": c["call_id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}} for c in calls
            ],
        }
        data = {"messages": [said, *([asked] if calls else [])], "pending": list(calls), "decision": decision}
        return run("base.assistant.turn", data, ctx_for(language="es")).model_dump(mode="json")

    before = rows()
    for operation, data in attempts():
        call = {"call_id": "c1", "name": shared.tool_name(operation), "arguments": json.dumps(data)}
        with translation.override("es"):
            plan = answered(call, decision={"call_id": "c1", "accepted": True, "typed": "CONFIRMAR"}, turn_of=turn)
        assert [(row["outcome"], row["code"]) for row in plan["executed"]] == [("error", CLOSED)], (operation, plan)
        assert "erplora.com" in plan["append"][0]["content"]
    assert rows() == before


@HUB_DB
@pytest.mark.parametrize(
    ("operation", "params"),
    [
        ("invoice.series.create", {"code": "ERP", "invoice_type": "F1", "year": 2027}),
        ("invoice.series.update", {"is_default": True}),
    ],
)
def test_an_automation_fails_with_the_same_reason(born, operation, params):
    if operation == "invoice.series.update":
        params = {**params, "series_id": str(series("ERP").id)}
    before = rows()
    flow = make_flow(
        trigger_kind="manual",
        steps=[{"id": "s1", "kind": "command", "operation": operation, "params": params}],
        grants=[operation],
    )
    result = run("flow.flow.run", {"id": str(flow.id)})
    assert (result.status, result.error_code) == ("failed", CLOSED)
    assert rows() == before


# ── Any other business ────────────────────────────────────────────────────────────────────────────────────────────


@HUB_DB
def test_in_any_other_business_erp_is_a_series_like_the_rest(issuer, settings, today):
    settings.PLATFORM_HUB_SLUG = "erp"
    made = run("invoice.series.create", {"code": "ERP", "invoice_type": "F1", "year": today.year, "name": "Ours"})
    run("invoice.series.update", {"series_id": str(made.id), "name": "Ours too", "is_default": True})
    by_default = manual()
    by_code = manual(series_code="ERP")
    assert (by_default.number, by_code.number) == (f"ERP-{today.year}-000001", f"ERP-{today.year}-000002")
    assert by_default.can_rectify is True
    assert [row.code for row in run("invoice.series.list", {"code": "ERP"}).rows] == ["ERP"]
    assert run("invoice.series.peek_next", {"code": "ERP"}).next_number == f"ERP-{today.year}-000003"
    assert run("invoice.series.get", {"code": "ERP"}).name == "Ours too"
    assert run("invoice.numbering.status").ordinary_series == 1
    rectified = run("invoice.invoice.rectify", {"number": by_code.number, "reason": "Wrong price"}).invoice
    assert rectified.number == f"RECT-{today.year}-000001"


@HUB_DB
def test_erploras_own_business_and_another_one_never_cross(born, hub_b, today):
    before = rows()
    with use_hub(hub_b):
        theirs = ctx_for(scope=B)
        run("invoice.issuer.update", ISSUER, theirs)
        run("invoice.series.create", {"code": "ERP", "invoice_type": "F1", "year": today.year}, theirs)
        assert manual(theirs, series_code="ERP").number == f"ERP-{today.year}-000001"
    assert rows() == before
    assert code_of(lambda: manual(series_code="ERP")) == CLOSED
    with use_hub(hub_b):
        assert series("ERP").current_number == 1


# ── At once ───────────────────────────────────────────────────────────────────────────────────────────────────────


@HUB_DB_COMMITTED
def test_a_manual_invoice_and_one_of_erplora_com_at_once_number_apart_in_one_chain(committed_platform_hub, today):
    """Each in its own series; the records, one chain, since the issuer is the same."""
    by_hand, automatic, refused = at_once(manual, issue, lambda: manual(series_code="ERP"))
    assert by_hand.number == f"FACT-{today.year}-000001"
    assert automatic.already is False
    assert refused.code == CLOSED
    assert sorted(Invoice.objects.values_list("number", flat=True)) == ["ERP-2026-00123", by_hand.number]
    assert {row.code: row.current_number for row in InvoiceSeries.objects.all()} == {"ERP": 0, "FACT": 1}
    first, second = Record.objects.order_by("sequence")
    assert (first.sequence, second.sequence, second.previous_fingerprint) == (1, 2, first.fingerprint)


@HUB_DB_COMMITTED
def test_a_refused_attempt_waits_for_nothing_of_the_automatic_issue(committed_platform_hub):
    def issuing(sql: str) -> bool:
        return 'INSERT INTO "invoice_invoice"' in sql

    with meanwhile(issuing, lambda: manual(series_code="ERP")) as outcomes:
        assert issue().status == "issued"
    assert outcomes[0].code == CLOSED


@HUB_DB
def test_what_the_automatic_issue_writes_does_not_depend_on_what_was_tried_by_hand(born):
    for operation, data in attempts():
        code_of(lambda operation=operation, data=data: run(operation, data))
    issue({**copy.deepcopy(BODY), "id": "019a0000-0000-7000-8000-00000000000a", "number": "ERP-2026-00124", "lines": [line()]})
    second = Invoice.objects.get(number="ERP-2026-00124")
    erp = series("ERP")
    assert (second.sequence, second.series_id, second.invoice_type) == (124, erp.id, "F1")
    assert (erp.name, erp.prefix, erp.format, erp.current_number, erp.is_active, erp.is_default) == (
        "ERPlora",
        "ERP",
        "{prefix}-{year}-{seq:05d}",
        0,
        True,
        False,
    )
    assert Record.objects.get(invoice=second).invoice_number == "ERP-2026-00124"
