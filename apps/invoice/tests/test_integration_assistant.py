"""The assistant's card for a write of invoice (FIX-HUB-INVOICE-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is hub#258):
in Spanish, every datum it sends by the name the Facturas screens give it, never by the title pydantic makes up from
the field («Duplicate», «Lines», «Next Number»). The card is base's (``base.assistant.card``); the names are invoice's:
the titles of its schemas and the ``verbose_name`` of its models, with their Spanish in its catalog."""

import datetime as dt
import json
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import timezone, translation
from live.operations import get, registry

from apps.invoice import queries
from apps.invoice.models import Invoice, InvoiceSeries
from apps.invoice.tests.conftest import ctx_for, run
from base import assistant
from base.tests.test_assistant import named_by_the_screen

LOCALE = Path(apps.get_app_config("invoice").path) / "frontend/locale"
SCREENS = json.loads((LOCALE / "es.json").read_text())["invoice"]
SCREENS_EN = json.loads((LOCALE / "en.json").read_text())["invoice"]


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


def invoice_writes() -> list:
    return [op for op in registry.values() if op.app_label == "invoice" and op.kind == "command" and assistant.is_tool(op)]


def test_no_datum_of_a_write_of_invoice_reaches_a_spanish_card_by_its_technical_name():
    """Every write of invoice the assistant may ask for, with all its data: each datum by a name of its own in Spanish,
    never the one pydantic makes up."""
    screen = named_by_the_screen()
    writes = invoice_writes()
    # Positive control: the registry has invoice's writes, those that send the data this fix names among them.
    assert {
        "invoice.invoice.create",
        "invoice.invoice.create_from_sale",
        "invoice.invoice.print",
        "invoice.invoice.rectify",
        "invoice.invoice.rectify_from_refund",
        "invoice.invoice.rectify_from_void",
        "invoice.series.create",
        "invoice.series.update",
    } <= {op.name for op in writes}
    technical: dict[str, list[str]] = {}
    for op in writes:
        props = op.input.model_json_schema().get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            if field["name"] not in screen and field["label"] == field["name"].title().replace("_", " "):
                technical.setdefault(op.name, []).append(field["name"])
    assert technical == {}


def test_the_card_names_a_reprint_as_the_paper_stamps_it():
    print_ = get("invoice.invoice.print")
    assert labels(assistant.card(print_, {"number": "F-1", "duplicate": True}, "es")) == ["Número", SCREENS["paper"]["copy"]]
    assert labels(assistant.card(print_, {"number": "F-1", "duplicate": True}, "en")) == ["Number", SCREENS_EN["paper"]["copy"]]


def test_the_card_names_the_kind_of_a_rectification_as_its_form_does():
    rectify = get("invoice.invoice.rectify")
    arguments = {"invoice_id": "x", "rectification_type": "R4"}
    assert labels(assistant.card(rectify, arguments, "es")) == ["Factura", SCREENS["rectify"]["type"]]
    assert labels(assistant.card(rectify, arguments, "en")) == ["Invoice", SCREENS_EN["rectify"]["type"]]


def test_the_card_names_the_lines_of_a_manual_invoice():
    lines = [{"description": "Corte", "quantity": "1", "unit_price": 1500, "tax_rate": "21"}]
    create = get("invoice.invoice.create")
    assert labels(assistant.card(create, {"lines": lines}, "es")) == ["Líneas"]
    assert labels(assistant.card(create, {"lines": lines}, "en")) == ["Lines"]


def test_the_card_names_a_series_next_number_as_its_form_does():
    for name in ("invoice.series.create", "invoice.series.update"):
        assert labels(assistant.card(get(name), {"next_number": 120}, "es")) == [SCREENS["series"]["form"]["nextNumber"]]
        assert labels(assistant.card(get(name), {"next_number": 120}, "en")) == [SCREENS_EN["series"]["form"]["nextNumber"]]


def test_the_card_names_the_sale_and_the_refund_as_the_record_does():
    for name in ("invoice.invoice.create_from_sale", "invoice.invoice.rectify_from_void"):
        assert labels(assistant.card(get(name), {"sale_id": "x"}, "es")) == [SCREENS["detail"]["fields"]["sale"]]
        assert labels(assistant.card(get(name), {"sale_id": "x"}, "en")) == [SCREENS_EN["detail"]["fields"]["sale"]]
    refund = get("invoice.invoice.rectify_from_refund")
    assert labels(assistant.card(refund, {"refund_id": "x"}, "es")) == [SCREENS["sources"]["refund"]]
    assert labels(assistant.card(refund, {"refund_id": "x"}, "en")) == [SCREENS_EN["sources"]["refund"]]


# ── Rectifying by asking the assistant (INVOICE-F08; PLAN §30, «Cinco acciones de IA pulidas», the second) ────────
# Against the Hub's real assistant turn (``base.assistant.turn``): «rectifica la factura … porque el precio estaba mal»
# offers the preview and the rectification; the preview (``invoice.invoice.rectification_preview``) is a read, so it
# runs by itself and goes back to the model with the rectifying invoice that would be born (no number taken); the
# rectification is a dangerous write: it waits on its card and issues only after the person types the word.

REASON = "el precio estaba mal"


def ask():
    """The person's request, about the first invoice of the year the test runs in."""
    return {"role": "user", "content": f"rectifica la factura FACT-{timezone.localdate().year}-000001 porque {REASON}"}


def call(name, arguments, call_id="c1"):
    return {"call_id": call_id, "name": assistant.tool_name(name), "arguments": json.dumps(arguments)}


def asked(*calls):
    """The model's message that asked for ``calls``, as the browser keeps it."""
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"id": c["call_id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}}
            for c in calls
        ],
    }


def turn(*calls, role="hub_admin", decision=None):
    """A turn of the assistant of a person with ``role``, in Spanish, answering the model's ``calls``."""
    data = {"messages": [ask(), *([asked(*calls)] if calls else [])], "pending": list(calls), "decision": decision}
    return run("base.assistant.turn", data, ctx_for(role, language="es")).model_dump(mode="json")


def an_invoice():
    line = {"description": "Corte", "quantity": "1", "unit_price": 10000, "tax_rate": "21"}
    return run(
        "invoice.invoice.create",
        {"lines": [line], "customer_name": "Talleres Pérez SL", "customer_tax_id": "B12345674", "customer_address": "Calle Luna 3"},
    )


def rectifications():
    return Invoice.objects.filter(invoice_type__startswith="R")


def test_rectifying_an_invoice_offers_the_preview_and_the_rectification(issuer):
    names = [tool["name"] for tool in turn()["tools"]]
    assert {"invoice__invoice__rectification_preview", "invoice__invoice__rectify"} <= set(names)


def test_the_rectification_tells_the_assistant_to_read_its_preview_first_and_to_name_that_invoice():
    rectify = get("invoice.invoice.rectify")
    assert "invoice.invoice.rectification_preview" in assistant.description(rectify)
    assert assistant.risk(rectify) == "high"
    # The preview is a read the assistant may run by itself: never a card, never a change.
    seen = get("invoice.invoice.rectification_preview")
    assert (seen.kind, assistant.is_tool(seen), seen.permission) == ("query", True, rectify.permission)


def test_the_preview_runs_by_itself_and_tells_the_model_the_invoice_that_would_be_born(issuer, today):
    original = an_invoice()
    plan = turn(call("invoice.invoice.rectification_preview", {"number": original.number, "reason": REASON}))
    assert plan["confirm"] is None
    assert [(row["name"], row["kind"], row["outcome"]) for row in plan["executed"]] == [
        ("invoice.invoice.rectification_preview", "query", "ok")
    ]
    told = json.loads(plan["append"][0]["content"])
    assert (told["original"]["number"], told["invoice_type"], told["reason"], told["next_number"]) == (
        original.number,
        "R1",
        REASON,
        f"RECT-{today.year}-000001",
    )
    assert (told["base_amount"], told["tax_amount"], told["total_amount"]) == (-10000, -2100, -12100)
    assert Invoice.objects.get(pk=original.id).status == "issued"
    assert not rectifications().exists()
    assert not InvoiceSeries.objects.filter(code="RECT").exists()


def test_what_cannot_be_rectified_the_preview_says_why_in_the_persons_language_and_no_card_comes(issuer):
    original = an_invoice()
    rect = run("invoice.invoice.rectify", {"number": original.number, "reason": "x"}).invoice
    # The person's request is in Spanish: what the model is told, and says, is why in Spanish.
    with translation.override("es"):
        plan = turn(call("invoice.invoice.rectification_preview", {"number": rect.number, "reason": REASON}))
        why = str(queries.CANNOT_RECTIFY_RECTIFICATION)
    assert plan["confirm"] is None
    assert [(row["outcome"], row["code"]) for row in plan["executed"]] == [
        ("error", "invoice.cannot_rectify_rectification")
    ]
    assert json.loads(plan["append"][0]["content"])["error"]["message"] == why != str(queries.CANNOT_RECTIFY_RECTIFICATION)
    assert rectifications().count() == 1


def test_the_rectification_waits_on_its_dangerous_card_naming_the_invoice_and_the_reason(issuer):
    original = an_invoice()
    rectify = call("invoice.invoice.rectify", {"number": original.number, "reason": REASON})
    plan = turn(rectify)
    card = plan["confirm"]
    assert (card["operation"], card["risk"], card["confirm_word"], card["blocked"]) == (
        "invoice.invoice.rectify",
        "high",
        "CONFIRMAR",
        False,
    )
    assert [(field["name"], field["value"]) for field in card["fields"]] == [
        ("number", original.number),
        ("reason", REASON),
    ]
    assert plan["pending"] == [rectify]
    assert not rectifications().exists()


def test_typing_the_word_issues_the_rectification_the_preview_said(issuer, today):
    original = an_invoice()
    seen = run("invoice.invoice.rectification_preview", {"number": original.number, "reason": REASON})
    rectify = call("invoice.invoice.rectify", {"number": seen.original.number, "reason": REASON})
    plan = turn(rectify, decision={"call_id": "c1", "accepted": True, "typed": " confirmar "})
    assert [(row["outcome"], row["code"]) for row in plan["executed"]] == [("ok", "")]
    rect = rectifications().get()
    assert (rect.rectifies_id, rect.number, rect.invoice_type, rect.total_amount, rect.issue_date, rect.created_by) == (
        original.id,
        seen.next_number,
        seen.invoice_type,
        seen.total_amount,
        today,
        "tester",
    )
    assert Invoice.objects.get(pk=original.id).status == "cancelled"


@pytest.mark.parametrize(
    "decision",
    [
        {"call_id": "c1", "accepted": False},
        {"call_id": "c1", "accepted": True, "typed": "sí"},
        {"call_id": "c1", "accepted": False, "stop": True},
    ],
    ids=["cancel", "wrong-word", "cancel-all"],
)
def test_without_the_word_nothing_is_issued_and_the_original_stays_issued(issuer, decision):
    original = an_invoice()
    plan = turn(call("invoice.invoice.rectify", {"number": original.number, "reason": REASON}), decision=decision)
    assert [row["outcome"] for row in plan["executed"]] == ["cancelled"]
    assert Invoice.objects.get(pk=original.id).status == "issued"
    assert not rectifications().exists()
    assert not InvoiceSeries.objects.filter(code="RECT").exists()


def test_a_rectification_dated_another_day_is_refused_even_with_the_word_typed(issuer, today):
    original = an_invoice()
    yesterday = str(today - dt.timedelta(days=1))
    rectify = call("invoice.invoice.rectify", {"number": original.number, "reason": REASON, "issue_date": yesterday})
    plan = turn(rectify, decision={"call_id": "c1", "accepted": True, "typed": "CONFIRMAR"})
    assert [(row["outcome"], row["code"]) for row in plan["executed"]] == [("error", "invoice.rectify_date_not_allowed")]
    assert Invoice.objects.get(pk=original.id).status == "issued"
    assert not rectifications().exists()
