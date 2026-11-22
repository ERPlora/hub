"""«Only mine or all» in Invoicing (INVOICE-F16 to INVOICE-F20): a person without «See all invoices»
(``invoice.view_all_invoices``) lists, opens, prints and touches only their invoices, the ones they issued and the ones
of their sales (the sales they charged or that were attributed to their staff record, with their rectifying ones);
the owner, the administrator and the manager reach everyone's, as Odoo's «own documents only». An invoice a person
does not see does not exist for them: the same 404 as an unknown one.

Over HTTP, as the screens, the assistant and the API ask, with two employees and a manager of the same business.
"""

import json

import pytest
from django.test import Client
from live.context import system_context
from live.meta import all_live_app_configs, permissions_for_role

from apps.invoice.models import Invoice
from apps.invoice.queries.ownership import INVOICES
from apps.invoice.tests.conftest import A, HUB_DB, ctx_for, run
from base.services.sessions import ensure_hub_user
from base.tenancy.tests.business import HOST

pytestmark = HUB_DB

CARD = [{"method": "card"}]
NOT_FOUND = "invoice.not_found"
SALE_NOT_FOUND = "sale.sale_not_found"
LINE = {"description": "Course", "quantity": "1", "unit_price": 10000, "tax_rate": "21"}
RECIPIENT = {"customer_name": "Talleres Pérez SL", "customer_tax_id": "B12345674", "customer_address": "Calle Luna 3"}


def get(client, path, **params):
    return client.get(f"/api{path}", params, HTTP_HOST=HOST)


def post(client, path, data):
    return client.post(f"/api{path}", json.dumps(data), content_type="application/json", HTTP_HOST=HOST)


def missing(response, code: str = NOT_FOUND) -> bool:
    """A 404 that says the invoice (or the sale) does not exist."""
    return response.status_code == 404 and response.json()["error"]["code"] == code


@pytest.fixture
def people(make_user, issuer, product):
    """Ana and Bea, two employees, and Marta, the manager, of a business that invoices: each on their own device."""
    product("Shampoo", "SHA", 1210, "product.generic")
    signed_in = {}
    for username, role in (("ana", "hub_employee"), ("bea", "hub_employee"), ("marta", "hub_manager")):
        user = make_user(username, role=role)
        client = Client()
        client.force_login(user)
        signed_in[username] = (user, client)
    return signed_in


def charge(client, key: str, **more) -> dict:
    body = {"idempotency_key": key, "lines": [{"product": "SHA"}], "payments": CARD, **more}
    response = post(client, "/sale/sales", body)
    assert response.status_code == 201, response.content
    return response.json()


def ticket_of(client, sale: dict) -> dict:
    found = get(client, "/invoice/invoices/by_source", sale_id=sale["id"]).json()
    assert found["found"] is True, found
    return found["invoice"]


def issue(client) -> dict:
    response = post(client, "/invoice/invoices", {"lines": [LINE], **RECIPIENT})
    assert response.status_code == 201, response.content
    return response.json()


def listed(client) -> set[str]:
    response = get(client, "/invoice/invoices")
    assert response.status_code == 200, response.content
    page = response.json()
    assert page["total"] == len(page["rows"])
    return {row["number"] for row in page["rows"]}


@pytest.fixture
def invoices(people):
    """Each employee charges a sale (its ticket is born in the charge) and issues an invoice by hand."""
    made = {}
    for name in ("ana", "bea"):
        client = people[name][1]
        sale = charge(client, f"own-invoices-{name}-0001")
        made[name] = {"sale": sale, "ticket": ticket_of(client, sale), "manual": issue(client)}
    return made


class TestAnEmployeeReachesOnlyTheirOwnInvoices:
    def test_the_list_has_the_ones_they_issued_and_the_ones_of_their_sales(self, people, invoices):
        for name in ("ana", "bea"):
            own = invoices[name]
            assert listed(people[name][1]) == {own["ticket"]["number"], own["manual"]["number"]}

    def test_someone_elses_does_not_open_by_its_number_nor_by_its_id(self, people, invoices):
        ana, theirs = people["ana"][1], invoices["bea"]["manual"]
        assert missing(get(ana, "/invoice/invoices/detail", number=theirs["number"]))
        assert missing(get(ana, "/invoice/invoices/detail", invoice_id=theirs["id"]))
        own = invoices["ana"]["manual"]
        assert get(ana, "/invoice/invoices/detail", number=own["number"]).json()["id"] == own["id"]

    def test_nor_its_document_nor_its_paper(self, people, invoices):
        ana, theirs = people["ana"][1], invoices["bea"]["ticket"]
        assert missing(get(ana, "/invoice/invoices/document", invoice_id=theirs["id"]))
        assert missing(post(ana, "/invoice/invoices/print", {"invoice_id": theirs["id"]}))
        own = invoices["ana"]["ticket"]
        assert get(ana, "/invoice/invoices/document", invoice_id=own["id"]).json()["number"] == own["number"]
        assert post(ana, "/invoice/invoices/print", {"invoice_id": own["id"]}).status_code == 200

    def test_nor_the_invoice_of_someone_elses_sale(self, people, invoices):
        ana = people["ana"][1]
        assert missing(get(ana, "/invoice/invoices/by_source", sale=invoices["bea"]["sale"]["number"]), SALE_NOT_FOUND)
        assert missing(get(ana, "/invoice/invoices/by_source", sale_id=invoices["bea"]["sale"]["id"]), SALE_NOT_FOUND)
        assert ticket_of(ana, invoices["ana"]["sale"])["id"] == invoices["ana"]["ticket"]["id"]

    def test_nor_mark_it_paid_nor_turn_it_into_a_full_invoice(self, people, invoices):
        ana = people["ana"][1]
        assert missing(post(ana, "/invoice/invoices/mark_paid", {"number": invoices["bea"]["manual"]["number"]}))
        assert Invoice.objects.get(pk=invoices["bea"]["manual"]["id"]).status == Invoice.Status.ISSUED
        full = {"invoice_id": invoices["bea"]["ticket"]["id"], **RECIPIENT}
        assert missing(post(ana, "/invoice/invoices/substitute", full))
        assert not Invoice.objects.filter(substitutes_id=invoices["bea"]["ticket"]["id"]).exists()
        own = post(ana, "/invoice/invoices/substitute", {**full, "invoice_id": invoices["ana"]["ticket"]["id"]})
        assert (own.status_code, own.json()["issued"]) == (200, True), own.content


class TestTheDocumentsOfTheirSales:
    def test_a_sale_attributed_to_their_staff_record_gives_them_its_ticket_whoever_charged_it(self, people):
        ana, marta = people["ana"], people["marta"][1]
        record = run(
            "staff.member.create",
            {"first_name": "Ana", "last_name": "Ruiz", "user_id": str(ensure_hub_user(ana[0]).pk)},
            system_context(A),
        )
        served = charge(marta, "own-invoices-served-0001", staff_id=str(record.id))
        ticket = ticket_of(marta, served)
        assert listed(ana[1]) == {ticket["number"]}
        assert get(ana[1], "/invoice/invoices/detail", invoice_id=ticket["id"]).status_code == 200
        assert listed(people["bea"][1]) == set()

    def test_the_rectifying_invoice_of_their_sale_is_theirs_whoever_issued_it(self, people, invoices):
        voided = post(people["marta"][1], "/sale/sales/void", {"sale_id": invoices["ana"]["sale"]["id"], "reason": "Wrong table"})
        assert voided.status_code == 200, voided.content
        rectifying = Invoice.objects.get(source_sale_id=invoices["ana"]["sale"]["id"], source_type=Invoice.Source.VOID)
        assert rectifying.created_by == "marta"
        assert rectifying.number in listed(people["ana"][1])
        assert rectifying.number not in listed(people["bea"][1])


class TestWhoSeesEveryone:
    def test_the_manager_lists_opens_and_prints_everyones(self, people, invoices):
        marta = people["marta"][1]
        everyone = {invoices[name][kind]["number"] for name in ("ana", "bea") for kind in ("ticket", "manual")}
        assert listed(marta) == everyone
        assert get(marta, "/invoice/invoices/detail", invoice_id=invoices["bea"]["manual"]["id"]).status_code == 200
        assert post(marta, "/invoice/invoices/print", {"invoice_id": invoices["bea"]["ticket"]["id"]}).status_code == 200
        assert ticket_of(marta, invoices["bea"]["sale"])["id"] == invoices["bea"]["ticket"]["id"]

    def test_the_owner_the_administrator_and_the_manager_hold_it_the_employee_does_not(self):
        configs = all_live_app_configs()
        assert "invoice.view_all_invoices" in next(c for c in configs if c.label == "invoice").permissions
        assert INVOICES.all_permission == "invoice.view_all_invoices"
        held = {role: ctx_for(role).has("invoice.view_all_invoices") for role in ("hub_owner", "hub_admin", "hub_manager")}
        assert held == {"hub_owner": True, "hub_admin": True, "hub_manager": True}
        assert "invoice.view_all_invoices" not in permissions_for_role(configs, "hub_employee")

    def test_a_caller_that_is_not_a_person_reaches_every_invoice(self, invoices):
        # An API key, an automation or the platform has nothing of its own: its permission opens the invoices.
        page = run("invoice.invoice.list", {}, ctx_for("hub_employee", actor="flow:7"))
        assert {row.number for row in page.rows} == {
            invoices[name][kind]["number"] for name in ("ana", "bea") for kind in ("ticket", "manual")
        }
