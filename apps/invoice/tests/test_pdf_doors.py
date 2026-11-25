"""Who asks for an invoice's PDF from outside its screen (INVOICE-F25): an API key and the assistant get the same file as
the button."""

import json
from types import SimpleNamespace

import pytest
from django.test import Client
from live import assistant as shared
from live.operations import get

from apps.invoice.tests.conftest import A, HUB_DB, ctx_for, run
from apps.invoice.tests.manual import manual
from apps.invoice.tests.printed import content, qr_urls, text
from base.schemas.assistant import A_HANDED_FILE

pytestmark = HUB_DB

HOST = f"{A.key}.localhost"
PDF = "invoice.invoice.pdf"


def key_with(client: Client, scopes: dict) -> dict:
    """A key the owner makes in Employees › API keys, as the header a program sends it in."""
    made = client.post("/api/keys", json.dumps({"name": "Accounting", "rate_per_minute": 60, "scopes": scopes}), content_type="application/json", HTTP_HOST=HOST)
    assert made.status_code == 200, made.content
    client.logout()
    return {"HTTP_AUTHORIZATION": f"Bearer {made.json()['token']}"}


@pytest.fixture
def owner(client, make_user):
    client.force_login(make_user("boss", role="hub_owner"))
    return client


def downloaded(client: Client, header: dict, **params):
    return client.get("/api/invoice/invoices/pdf", params, HTTP_HOST=HOST, **header)


def test_a_key_that_reads_invoices_and_nothing_of_verifactu_gets_it_with_its_qr(issuer, owner):
    invoice = manual()
    header = key_with(owner, {"invoice": ["read"]})

    answer = downloaded(owner, header, number=invoice.number)

    assert answer.status_code == 200, answer.content
    out = SimpleNamespace(**answer.json())
    screen = run("verifactu.record.by_invoice", {"invoice_id": str(invoice.id)}).record
    assert (out.filename, out.content_type) == (f"{invoice.number}.pdf", "application/pdf")
    assert content(out).startswith(b"%PDF-") and qr_urls(out) == [screen.qr_url]


def test_a_key_that_reads_no_invoices_gets_none(issuer, owner):
    invoice = manual()
    header = key_with(owner, {"customer": ["read"]})

    assert downloaded(owner, header, number=invoice.number).status_code == 403


def test_without_a_session_nor_a_key_there_is_none(issuer, client):
    invoice = manual()

    answer = downloaded(client, {}, number=invoice.number)

    assert (answer.status_code, answer.json()["error"]["code"]) == (401, "unauthorized")


def test_an_invoice_that_does_not_exist_says_so(issuer, owner):
    answer = downloaded(owner, key_with(owner, {"invoice": ["read"]}), number="FACT-2026-999999")

    assert (answer.status_code, answer.json()["error"]["code"]) == (404, "invoice.not_found")


def test_the_assistant_hands_the_person_the_file_and_the_model_hears_only_its_name(issuer):
    invoice = manual()
    call = {"call_id": "c1", "name": shared.tool_name(PDF), "arguments": json.dumps({"number": invoice.number})}
    function = {"name": call["name"], "arguments": call["arguments"]}
    asking = {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function", "function": function}]}
    data = {"messages": [{"role": "user", "content": f"dame el PDF de la {invoice.number}"}, asking], "pending": [call]}

    plan = run("base.assistant.turn", data, ctx_for(language="es")).model_dump(mode="json")

    [ran] = plan["executed"]
    assert (ran["name"], ran["outcome"]) == (PDF, "ok")
    assert (ran["file"]["filename"], ran["file"]["content_type"]) == (f"{invoice.number}.pdf", "application/pdf")
    handed = SimpleNamespace(content_base64=ran["file"]["content"])
    assert invoice.number in text(handed) and "FACTURA" in text(handed)
    assert ran["file"]["content"] not in json.dumps(plan["append"]) + json.dumps(plan["messages"])
    assert get(PDF).output.model_fields["content_base64"].json_schema_extra == A_HANDED_FILE
