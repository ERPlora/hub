"""The accountancy firm (``hub_accountant``, «Gestoría») with the invoices issued: it lists and opens everyone's,
downloads each one's document, reads the series, the issuer, the taxes and each invoice's VeriFactu record; it issues,
rectifies and sets up nothing.

Over HTTP, as the screens, the assistant and the API ask, with two employees who issue invoices by hand and the firm
that reads them.
"""

import pytest
from django.test import Client

from apps.invoice.tests.conftest import HUB_DB, ISSUER
from apps.invoice.tests.test_api import LINE, RECIPIENT
from apps.invoice.tests.test_queries_ownership import get, post

pytestmark = HUB_DB

REFUSED = "permission_denied"


def signed_in(make_user, username: str, role: str) -> Client:
    client = Client()
    client.force_login(make_user(username, role=role))
    return client


@pytest.fixture
def gema(make_user):
    """Gema, of the business's accountancy firm, signed in on her own computer."""
    return signed_in(make_user, "gema", "hub_accountant")


@pytest.fixture
def invoices(make_user, issuer):
    """An invoice issued by hand by each of two employees, Ana and Bea."""
    made = []
    for name in ("ana", "bea"):
        response = post(signed_in(make_user, name, "hub_employee"), "/invoice/invoices", {"lines": [LINE], **RECIPIENT})
        assert response.status_code == 201, response.content
        made.append(response.json())
    return made


def test_it_lists_opens_and_downloads_the_invoices_of_everyone(gema, invoices):
    listed = get(gema, "/invoice/invoices")

    assert listed.status_code == 200, listed.content
    assert {row["number"] for row in listed.json()["rows"]} == {invoice["number"] for invoice in invoices}
    for invoice in invoices:
        assert get(gema, "/invoice/invoices/detail", invoice_id=invoice["id"]).json()["id"] == invoice["id"]
        assert invoice["number"] in get(gema, "/invoice/invoices/document", invoice_id=invoice["id"]).json()["html"]


def test_it_reads_each_invoice_s_verifactu_record_the_series_the_issuer_and_the_taxes(gema, invoices):
    reads = [
        get(gema, "/verifactu/records/by_invoice", invoice_id=invoices[1]["id"]),
        get(gema, "/verifactu/records"),
        get(gema, "/invoice/series"),
        get(gema, "/invoice/issuer"),
        get(gema, "/tax/rules"),
    ]

    assert [response.status_code for response in reads] == [200] * len(reads)


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/invoice/invoices", {"lines": [LINE], **RECIPIENT}),
        ("/invoice/invoices/rectify", {"number": "-", "reason": "Wrong price"}),
        ("/invoice/series", {"code": "GEST", "invoice_type": "F1", "year": 2026}),
        ("/invoice/issuer", {**ISSUER, "legal_name": "Otra SL"}),
        ("/tax/settings", {"region_code": "ES-CN"}),
        ("/verifactu/certificate/remove", {}),
    ],
    ids=["issue", "rectify", "add-a-series", "change-the-issuer", "change-the-taxes", "remove-the-certificate"],
)
def test_it_issues_rectifies_and_sets_up_nothing(gema, issuer, path, body):
    response = post(gema, path, body)

    assert response.status_code == 403, response.content
    assert response.json()["error"]["code"] == REFUSED
