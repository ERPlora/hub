"""The assistant's card for a write of invoice (FIX-HUB-INVOICE-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is hub#258):
in Spanish, every datum it sends by the name the Facturas screens give it, never by the title pydantic makes up from
the field («Duplicate», «Lines», «Next Number»). The card is base's (``base.assistant.card``); the names are invoice's:
the titles of its schemas and the ``verbose_name`` of its models, with their Spanish in its catalog."""

import datetime as dt
import json
import uuid
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import timezone, translation
from live.context import OperationContext, Scope, system_context
from live.operations import get, registry

from apps.invoice import queries
from apps.invoice.models import Invoice, InvoiceSeries
from apps.invoice.tests.conftest import ISSUER, ctx_for, run
from base import assistant
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_assistant import named_by_the_screen
from base.tests.test_assistant_card_values import AN_ID

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
    # The invoice by its number: one named by its id is said by its number, read as the person (below).
    rectify = get("invoice.invoice.rectify")
    arguments = {"number": "FACT-2026-000001", "rectification_type": "R4"}
    assert labels(assistant.card(rectify, arguments, "es")) == ["Número", SCREENS["rectify"]["type"]]
    assert labels(assistant.card(rectify, arguments, "en")) == ["Number", SCREENS_EN["rectify"]["type"]]


def test_the_card_names_the_lines_of_a_manual_invoice():
    lines = [{"description": "Corte", "quantity": "1", "unit_price": 1500, "tax_rate": "21"}]
    create = get("invoice.invoice.create")
    assert labels(assistant.card(create, {"lines": lines}, "es")) == ["Líneas"]
    assert labels(assistant.card(create, {"lines": lines}, "en")) == ["Lines"]


def test_the_card_names_a_series_next_number_as_its_form_does():
    for name in ("invoice.series.create", "invoice.series.update"):
        assert labels(assistant.card(get(name), {"next_number": 120}, "es")) == [SCREENS["series"]["form"]["nextNumber"]]
        assert labels(assistant.card(get(name), {"next_number": 120}, "en")) == [SCREENS_EN["series"]["form"]["nextNumber"]]


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


# ── What rectifying will do, on its card (FIX-HUB-INVOICE-ASSISTANT-RECTIFY-CARD-WITHOUT-PREVIEW; BASE-F98's hook) ─
# The card of the rectification listed only what it sends (the number and the reason), never the rectifying invoice it
# issues. Through base's hook it shows, before the word is typed, what invoice.invoice.rectification_preview answers
# for the person: the type, the next number of the series (NOT taken) and the amounts in negative, as money.

PREVIEWED = ["invoice_type", "next_number", "base_amount", "tax_amount", "total_amount"]


def preview_of(number: str, language: str) -> list[dict]:
    failure, preview = assistant.preview(
        ctx_for(language=language), get("invoice.invoice.rectify"), {"number": number, "reason": REASON}
    )
    assert failure is None
    return preview


def card_labels(screens: dict) -> list[str]:
    """The five data by the names the Facturas screens give them: the form of Rectificar, the series and the paper."""
    return [
        screens["rectify"]["type"],
        screens["series"]["form"]["nextNumber"],
        screens["paper"]["taxBase"],
        screens["paper"]["tax"],
        screens["detail"]["totals"]["total"],
    ]


def test_the_rectification_card_shows_the_rectifying_invoice_with_its_amounts_in_negative_as_money(issuer, today):
    original = an_invoice()
    preview = preview_of(original.number, "es")
    assert [(field["name"], field["kind"], field["value"]) for field in preview] == [
        ("invoice_type", "text", "R1"),
        ("next_number", "text", f"RECT-{today.year}-000001"),
        ("base_amount", "money", -10000),
        ("tax_amount", "money", -2100),
        ("total_amount", "money", -12100),
    ]
    assert [field["label"] for field in preview] == card_labels(SCREENS)
    assert [field["label"] for field in preview_of(original.number, "en")] == card_labels(SCREENS_EN)
    assert assistant.preview_of(get("invoice.invoice.rectify"))["fields"] == PREVIEWED


def test_the_card_the_person_sees_carries_that_preview_and_takes_no_number(issuer, today):
    original = an_invoice()
    plan = turn(call("invoice.invoice.rectify", {"number": original.number, "reason": REASON}))
    card = plan["confirm"]
    assert (card["operation"], card["confirm_word"]) == ("invoice.invoice.rectify", "CONFIRMAR")
    assert [(field["name"], field["value"]) for field in card["preview"]] == [
        ("invoice_type", "R1"),
        ("next_number", f"RECT-{today.year}-000001"),
        ("base_amount", -10000),
        ("tax_amount", -2100),
        ("total_amount", -12100),
    ]
    # Numbering is never optimistic: reading it takes no number, nor even creates this year's RECT series.
    assert not InvoiceSeries.objects.filter(code="RECT").exists()
    assert not rectifications().exists()


def test_typing_the_word_issues_exactly_the_number_the_card_said(issuer, today):
    original = an_invoice()
    rectify = call("invoice.invoice.rectify", {"number": original.number, "reason": REASON})
    said = {field["name"]: field["value"] for field in turn(rectify)["confirm"]["preview"]}
    turn(rectify, decision={"call_id": "c1", "accepted": True, "typed": "CONFIRMAR"})
    rect = rectifications().get()
    assert (rect.number, rect.invoice_type, rect.base_amount, rect.tax_amount, rect.total_amount) == (
        said["next_number"],
        said["invoice_type"],
        said["base_amount"],
        said["tax_amount"],
        said["total_amount"],
    )


def test_another_rectification_issued_after_the_card_takes_its_number_and_this_one_the_next(issuer, today):
    """The card says the next number, not one kept for it (INVOICE-F08, «Si falla»)."""
    original, other = an_invoice(), an_invoice()
    rectify = call("invoice.invoice.rectify", {"number": original.number, "reason": REASON})
    said = {field["name"]: field["value"] for field in turn(rectify)["confirm"]["preview"]}["next_number"]
    first = run("invoice.invoice.rectify", {"number": other.number, "reason": "otro"}).invoice
    turn(rectify, decision={"call_id": "c1", "accepted": True, "typed": "CONFIRMAR"})
    mine = rectifications().get(rectifies_id=original.id)
    assert (first.number, mine.number) == (said, f"RECT-{today.year}-000002")


def test_asked_straight_to_rectify_what_cannot_be_the_card_does_not_come_and_says_why(issuer):
    """Without reading the preview first, a rectifying invoice asked to be rectified: the card's preview cannot be read,
    so no card (nothing is confirmed blind) and the model hears why, in the person's language."""
    original = an_invoice()
    rect = run("invoice.invoice.rectify", {"number": original.number, "reason": "x"}).invoice
    with translation.override("es"):
        plan = turn(call("invoice.invoice.rectify", {"number": rect.number, "reason": REASON}))
        why = str(queries.CANNOT_RECTIFY_RECTIFICATION)
    assert (plan["confirm"], plan["pending"]) == (None, [])
    assert [(row["name"], row["outcome"], row["code"]) for row in plan["executed"]] == [
        ("invoice.invoice.rectify", "error", "invoice.cannot_rectify_rectification")
    ]
    assert json.loads(plan["append"][0]["content"])["error"]["message"] == why
    assert rectifications().count() == 1


# ── The record a write names by its id, by its name (FIX-HUB-INVOICE-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS; base's half
# is hub#416) ──
# Since hub#416 the card leaves out an id its schema does not mark: «marca como pagada esa factura», «emite la factura de
# esa venta» or «rectifica esa devolución» said no invoice, no sale and no refund. Now each record is named as the
# Facturas screens show it: an invoice and a sale by their numbers, a refund by its sale and what it gave back, a series
# by its code, its year and its name, and the customer by the name on their card. Read as whoever asks, in the hub they
# ask in: never by the id, and left out when nobody, or somebody who may not see them, is behind the request. The product
# of a manual line is Inventory's, which Invoicing does not require: it is left out, and the line's description says it.

#: Every record a write of invoice names by its id: the data that name one, by write.
NAMED = {
    "invoice.invoice.create": ("customer_id", "series_id"),
    "invoice.invoice.create_from_sale": ("sale_id",),
    "invoice.invoice.mark_paid": ("invoice_id",),
    "invoice.invoice.print": ("invoice_id",),
    "invoice.invoice.rectify": ("invoice_id",),
    "invoice.invoice.rectify_from_refund": ("refund_id",),
    "invoice.invoice.rectify_from_void": ("sale_id",),
    "invoice.invoice.substitute": ("customer_id", "invoice_id"),
    "invoice.series.update": ("series_id",),
}
#: What each write sends besides its records, as the model would.
BESIDES = {"invoice.invoice.rectify": {"reason": REASON}}
#: The roles a business gives that run invoice's writes: each runs those its permissions let it.
ROLES = ("hub_employee", "hub_manager", "hub_admin", "hub_owner")


def references(op) -> set[str]:
    """The data of ``op``'s input its schema declares an id of (``format: uuid``)."""
    schema = op.input.model_json_schema()
    props = schema.get("properties", {})
    return {name for name, prop in props.items() if assistant._resolved(prop, schema.get("$defs", {})).get("format") == "uuid"}


def values(card: dict) -> dict:
    return {field["name"]: field["value"] for field in card["fields"]}


def no_id(card: dict) -> bool:
    return not AN_ID.search(json.dumps(card, ensure_ascii=False))


def in_hub(hub, role: str = "hub_admin", language: str = "es") -> OperationContext:
    return ctx_for(role, scope=Scope("host", hub.slug), language=language)


def a_business(scope: Scope) -> dict:
    """What the Facturas screens of a salon show: its issuer, the customer card «Talleres Pérez SL», a sale of the
    shampoo charged by card with 5,00 € of it given back, and the manual invoice of that customer, this year's first of
    the series FACT. Made with each app's own operations."""
    from apps.sale.models import Sale

    admin, system = ctx_for(scope=scope), system_context(scope)
    run("invoice.issuer.update", ISSUER, admin)
    customer = run(
        "customer.customer.create", {"name": "Talleres Pérez SL", "tax_id": "B12345674", "address": "Calle Luna 3"}, system
    )
    run("inventory.product.create", {"name": "Champú", "sku": "CH-1", "price": 1210, "tax_category_key": "product.generic"}, system)
    sale = run(
        "sale.sale.complete",
        {"idempotency_key": "inv-card-0001", "lines": [{"product": "CH-1"}], "payments": [{"method": "card"}]},
        admin,
    )
    payment = Sale.objects.get(pk=sale.id).payments.get()
    refund = run(
        "sale.sale.refund",
        {"sale_id": str(sale.id), "reason": "Roto", "allocations": [{"payment_id": str(payment.id), "amount": 500}]},
        admin,
    )
    line = {"description": "Corte", "quantity": "1", "unit_price": 10000, "tax_rate": "21"}
    invoice = run("invoice.invoice.create", {"customer_id": str(customer.id), "lines": [line]}, admin)
    series = InvoiceSeries.objects.get(code="FACT", year=timezone.localdate().year)
    return {
        "ids": {"customer_id": customer.id, "series_id": series.id, "sale_id": sale.id, "refund_id": refund.refund_id, "invoice_id": invoice.id},
        "sale": sale.number,
        "invoice": invoice.number,
    }


def said(business: dict, language: str = "es") -> dict:
    """How the card names each record of ``a_business``, as the Facturas screens show it."""
    year = timezone.localdate().year
    return {
        "customer_id": "Talleres Pérez SL",
        "series_id": f"FACT · {year} · {'Facturas' if language == 'es' else 'Invoices'}",
        "sale_id": business["sale"],
        "refund_id": f"{business['sale']} · {'5,00\u00a0€' if language == 'es' else '€5.00'}",  # money as every screen writes it (CLDR)
        "invoice_id": business["invoice"],
    }


def cards(business: dict, ctx: OperationContext | None, language: str = "es") -> dict:
    """The card of each write of ``NAMED`` naming every record it names by its id, as ``ctx``'s person would confirm it."""
    return {
        write: assistant.card(
            get(write), {**{datum: str(business["ids"][datum]) for datum in data}, **BESIDES.get(write, {})}, language, ctx
        )
        for write, data in NAMED.items()
    }


def named_as_the_screens(business: dict, language: str = "es") -> dict:
    names = said(business, language)
    return {write: {**{datum: names[datum] for datum in data}, **BESIDES.get(write, {})} for write, data in NAMED.items()}


def left_out() -> dict:
    return {write: BESIDES.get(write, {}) for write in NAMED}


def test_every_record_a_write_of_invoice_names_by_its_id_is_listed_here():
    """Positive control of the tests below: a new reference of a write of invoice comes in here, with its name."""
    assert {op.name: references(op) for op in invoice_writes() if references(op)} == {
        write: set(data) for write, data in NAMED.items()
    }


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.parametrize("language", ["es", "en"])
def test_a_write_of_invoice_names_each_record_as_the_invoices_screens_do(language, hub_a, no_fallback):
    """«Marca como pagada esa factura», «emite la factura de esa venta», «rectifica esa devolución»: the card says which
    invoice, sale, refund, series or customer as the Facturas screens show them, in the person's language, never by its
    id."""
    with use_hub(hub_a):
        business = a_business(Scope("host", hub_a.slug))
        shown = cards(business, in_hub(hub_a, language=language), language)
    assert {write: values(card) for write, card in shown.items()} == named_as_the_screens(business, language)
    assert [write for write, card in shown.items() if not no_id(card)] == []


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.parametrize(
    ("language", "titles"),
    [
        ("es", {"customer_id": "Cliente", "series_id": "Serie", "invoice_id": "Factura"}),
        ("en", {"customer_id": "Customer", "series_id": "Series", "invoice_id": "Invoice"}),
    ],
)
def test_each_record_is_titled_as_the_invoice_titles_it(language, titles, hub_a, no_fallback):
    """«Factura: FACT-2026-000001», «Venta: 20261031-0001», «Devolución de venta: …»: each record by the name its screens
    give it, never by its field («Invoice Id», «Refund Id»)."""
    screens = SCREENS if language == "es" else SCREENS_EN
    titles = {**titles, "sale_id": screens["detail"]["fields"]["sale"], "refund_id": screens["sources"]["refund"]}
    with use_hub(hub_a):
        shown = cards(a_business(Scope("host", hub_a.slug)), in_hub(hub_a, language=language), language)
    assert {
        write: {field["name"]: field["label"] for field in card["fields"] if field["name"] in NAMED[write]}
        for write, card in shown.items()
    } == {write: {datum: titles[datum] for datum in data} for write, data in NAMED.items()}


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_nobody_behind_the_request_reads_no_record_of_invoice(hub_a, no_fallback):
    """An automation's card (no person at hand) names no record: nothing is read for anybody."""
    with use_hub(hub_a):
        shown = cards(a_business(Scope("host", hub_a.slug)), None)
    assert {write: values(card) for write, card in shown.items()} == left_out()
    assert all(no_id(card) for card in shown.values())


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_who_may_not_see_them_reads_none_of_them_on_the_card(hub_a, no_fallback):
    """Whoever may issue, rectify and keep the series but see neither invoices, nor sales, nor customers (a key that only
    writes, say) gets every record left out, never its id."""
    writes_only = frozenset({"invoice.add_invoice", "invoice.rectify_invoice", "invoice.manage_series"})
    with use_hub(hub_a):
        business = a_business(Scope("host", hub_a.slug))
        shown = cards(business, OperationContext(scope=Scope("host", hub_a.slug), actor="key", permissions=writes_only, language="es"))
    assert {write: values(card) for write, card in shown.items()} == left_out()
    assert all(no_id(card) for card in shown.values())


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_record_that_is_not_there_is_left_out_never_by_its_id(hub_a, no_fallback):
    gone = {"ids": {datum: uuid.uuid7() for datum in ("customer_id", "series_id", "sale_id", "refund_id", "invoice_id")}}
    with use_hub(hub_a):
        shown = cards(gone, in_hub(hub_a))
    assert {write: values(card) for write, card in shown.items()} == left_out()
    assert all(no_id(card) for card in shown.values())


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_record_of_hub_b_is_never_named_on_a_card_of_hub_a(hub_a, hub_b, no_fallback):
    """The read runs in the hub the person asks in: hub B's invoice, sale, refund, series or customer is nobody in hub A."""
    with use_hub(hub_b):
        theirs = a_business(Scope("host", hub_b.slug))
        named_in_b = cards(theirs, in_hub(hub_b))
    with use_hub(hub_a):
        shown = cards(theirs, in_hub(hub_a))
    assert {write: values(card) for write, card in shown.items()} == left_out()
    assert all(no_id(card) for card in shown.values())
    # Positive control: in hub B the same cards name them.
    assert {write: values(card) for write, card in named_in_b.items()} == named_as_the_screens(theirs)


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_the_product_of_a_manual_line_is_left_out_never_by_its_id(hub_a, no_fallback):
    """Inventory is no requirement of Invoicing: its product on a manual line is left out of the card, whose line says
    what is invoiced by its description."""
    line = {"description": "Champú", "quantity": "1", "unit_price": 1000, "tax_rate": "21"}
    with use_hub(hub_a):
        shampoo = run(
            "inventory.product.create",
            {"name": "Champú", "sku": "CH-1", "price": 1210, "tax_category_key": "product.generic"},
            system_context(Scope("host", hub_a.slug)),
        )
        card = assistant.card(get("invoice.invoice.create"), {"lines": [{**line, "product_id": str(shampoo.id)}]}, "es", in_hub(hub_a))
    assert [{key: value for key, value in row.items() if key != "unit_price"} for row in values(card)["lines"]] == [
        {"description": "Champú", "quantity": "1", "tax_rate": "21"}
    ]
    assert no_id(card)


@pytest.mark.parametrize("write", ["invoice.invoice.create", "invoice.invoice.create_from_sale", "invoice.invoice.substitute"])
@pytest.mark.parametrize("language", ["es", "en"])
def test_the_kind_of_a_foreign_recipient_s_document_is_said_as_the_recipient_form_says_it(write, language):
    """«Hazle la factura con su pasaporte»: the kind of document of a foreign recipient by the words the recipient form
    gives it («Pasaporte», «NIF-IVA de la UE»), never its AEAT code («03»)."""
    screens = SCREENS if language == "es" else SCREENS_EN
    kinds = screens["recipient"]["idTypes"]
    assert set(kinds) == {"02", "03", "04", "05", "06", "07"}  # positive control: every kind the form offers
    assert {
        code: values(assistant.card(get(write), {"customer_id_type": code}, language))["customer_id_type"]
        for code in kinds
    } == kinds


def test_whoever_may_run_a_write_reads_the_record_its_card_names():
    """The read runs as the person: a role that may run a write and not read what its card names would get a card with
    nothing to recognise, just in the common case. Every role a business gives, every write that names a record."""
    unread: list[tuple[str, str, str]] = []
    checked = 0
    for role in ROLES:
        mine = ctx_for(role)
        for name, data in NAMED.items():
            op = get(name)
            if not mine.has(op.permission):
                continue
            schema = op.input.model_json_schema()
            for datum in data:
                checked += 1
                marked = assistant.refers_of(assistant._resolved(schema["properties"][datum], schema.get("$defs", {})))
                if marked is None or not mine.has(registry[marked["read"]].permission):
                    unread.append((role, name, datum))
    # Positive control: the employee issues, prints and marks as paid (7 records); the manager, the admin and the owner
    # run every one of the 11.
    assert checked == 7 + 11 * 3
    assert unread == []
