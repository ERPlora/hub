"""«Only mine or all» in Sales (SALE-F28 to SALE-F31): a person without «See all sales» (``sale.view_all_sales``) reads
and touches only the sales they charged or that were attributed to their staff record; the owner, the administrator
and the manager reach everyone's, as Square's and Toast's «view own / view all sales». A sale a person does not see
does not exist for them: the same 404 as an unknown one, never a 403 that tells it is there.

Over HTTP, as the screens, the assistant and the API ask, with two employees and a manager of the same business; the
commands a manager approves on the spot (void, refund) through their operation, with the approved permission added.
"""

import dataclasses
import json

import pytest
from django.test import Client
from live.context import system_context
from live.errors import NotFound
from live.meta import all_live_app_configs, permissions_for_role

from apps.sale.models import Sale
from apps.sale.queries.ownership import SALES
from apps.sale.tests.conftest import HOST, HUB_DB, A, ctx_for, run

pytestmark = HUB_DB

CARD = [{"method": "card"}]
NOT_FOUND = "sale.sale_not_found"
ISSUER_MISSING = "invoice.issuer_missing"


def get(client, path, **params):
    return client.get(f"/api{path}", params, HTTP_HOST=HOST)


def post(client, path, data):
    return client.post(f"/api{path}", json.dumps(data), content_type="application/json", HTTP_HOST=HOST)


@pytest.fixture
def coffee(product):
    product("Coffee", "COF", 150, "restaurant.drink")


@pytest.fixture
def people(make_user):
    """Ana and Bea, two employees, and Marta, the manager: each signed in on their own device."""
    signed_in = {}
    for username, role in (("ana", "hub_employee"), ("bea", "hub_employee"), ("marta", "hub_manager")):
        user = make_user(username, role=role)
        client = Client()
        client.force_login(user)
        signed_in[username] = (user, client)
    return signed_in


def charge(client, key: str, **more) -> dict:
    body = {"idempotency_key": key, "lines": [{"product": "COF"}], "payments": CARD, **more}
    response = post(client, "/sale/sales", body)
    assert response.status_code == 201, response.content
    return response.json()


def listed(client) -> set[str]:
    response = get(client, "/sale/sales")
    assert response.status_code == 200, response.content
    page = response.json()
    assert page["total"] == len(page["rows"])
    return {row["number"] for row in page["rows"]}


def missing(response) -> bool:
    """A 404 that says the sale does not exist."""
    return response.status_code == 404 and response.json()["error"]["code"] == NOT_FOUND


@pytest.fixture
def sales(coffee, people):
    """One sale charged by each employee."""
    return {name: charge(people[name][1], f"own-sales-{name}-0001") for name in ("ana", "bea")}


class TestAnEmployeeReachesOnlyTheirOwnSales:
    def test_the_list_has_only_the_sales_they_charged(self, people, sales):
        assert listed(people["ana"][1]) == {sales["ana"]["number"]}
        assert listed(people["bea"][1]) == {sales["bea"]["number"]}

    def test_someone_elses_sale_does_not_open_by_its_number_nor_by_its_id(self, people, sales):
        ana = people["ana"][1]
        assert missing(get(ana, "/sale/sales/detail", sale=sales["bea"]["number"]))
        assert missing(get(ana, "/sale/sales/detail", sale_id=sales["bea"]["id"]))
        assert get(ana, "/sale/sales/detail", sale_id=sales["ana"]["id"]).json()["id"] == sales["ana"]["id"]

    def test_nor_by_the_key_of_its_charge(self, people, sales):
        ana = people["ana"][1]
        assert get(ana, "/sale/sales/by_key", idempotency_key="own-sales-bea-0001").json() == {
            "found": False,
            "sale": None,
        }
        assert get(ana, "/sale/sales/by_key", idempotency_key="own-sales-ana-0001").json()["found"] is True

    def test_nor_its_paper_nor_a_reprint(self, people, sales):
        ana = people["ana"][1]
        assert missing(get(ana, "/sale/letterhead", sale_id=sales["bea"]["id"]))
        assert missing(post(ana, "/sale/sales/print", {"sale_id": sales["bea"]["id"]}))
        assert post(ana, "/sale/sales/print", {"sale_id": sales["ana"]["id"]}).status_code == 200

    def test_nor_what_it_could_refund_nor_its_refunds(self, people, sales):
        ana = people["ana"][1]
        assert missing(get(ana, "/sale/refunds/options", sale_id=sales["bea"]["id"]))
        assert missing(get(ana, "/sale/refunds", sale_id=sales["bea"]["id"]))
        assert get(ana, "/sale/refunds/options", sale_id=sales["ana"]["id"]).status_code == 200

    def test_nor_issue_now(self, people, sales):
        ana = people["ana"][1]
        assert missing(post(ana, "/sale/sales/issue_documents", {"sale_id": sales["bea"]["id"]}))
        # Their own reaches Invoicing, which says why it cannot issue it yet: this business has no issuer.
        own = post(ana, "/sale/sales/issue_documents", {"sale_id": sales["ana"]["id"]})
        assert (own.status_code, own.json()["error"]["code"]) == (409, ISSUER_MISSING)

    def test_an_approved_void_or_refund_does_not_reach_it_either(self, people, sales):
        # What a manager's PIN adds to the cashier's request is that one command's permission, never «all sales».
        ana = people["ana"][0]
        approved = dataclasses.replace(
            ctx_for("hub_employee", actor=ana),
            permissions=ctx_for("hub_employee").permissions | {"sale.void_sale", "sale.refund_sale"},
        )
        theirs = sales["bea"]["id"]
        with pytest.raises(NotFound):
            run("sale.sale.void", {"sale_id": theirs, "reason": "Wrong table"}, approved)
        with pytest.raises(NotFound):
            run("sale.sale.refund", {"sale_id": theirs, "reason": "Returned"}, approved)
        assert Sale.objects.get(pk=theirs).status == Sale.Status.COMPLETED
        voided = run("sale.sale.void", {"sale_id": sales["ana"]["id"], "reason": "Wrong table"}, approved)
        assert voided.status == Sale.Status.VOIDED


class TestTheirStaffRecord:
    def test_a_sale_attributed_to_their_staff_record_is_theirs_whoever_charged_it(self, coffee, people):
        ana, bea, marta = people["ana"][0], people["bea"][1], people["marta"][1]
        record = run(
            "staff.member.create",
            {"first_name": "Ana", "last_name": "Ruiz", "user_id": str(ana.person.pk)},
            system_context(A),
        )
        served = charge(marta, "own-sales-served-0001", staff_id=str(record.id))
        assert listed(people["ana"][1]) == {served["number"]}
        assert get(people["ana"][1], "/sale/sales/detail", sale_id=served["id"]).status_code == 200
        assert listed(bea) == set()


class TestWhoSeesEveryone:
    def test_the_manager_lists_opens_and_reprints_everyones(self, people, sales):
        marta = people["marta"][1]
        assert listed(marta) == {sales["ana"]["number"], sales["bea"]["number"]}
        assert get(marta, "/sale/sales/detail", sale_id=sales["bea"]["id"]).status_code == 200
        assert post(marta, "/sale/sales/print", {"sale_id": sales["bea"]["id"]}).status_code == 200

    def test_the_owner_the_administrator_and_the_manager_hold_it_the_employee_does_not(self):
        configs = all_live_app_configs()
        assert "sale.view_all_sales" in next(config for config in configs if config.label == "sale").permissions
        assert SALES.all_permission == "sale.view_all_sales"
        held = {role: ctx_for(role).has("sale.view_all_sales") for role in ("hub_owner", "hub_admin", "hub_manager")}
        assert held == {"hub_owner": True, "hub_admin": True, "hub_manager": True}
        assert "sale.view_all_sales" not in permissions_for_role(configs, "hub_employee")

    def test_a_caller_that_is_not_a_person_reaches_every_sale(self, people, sales):
        # An API key, an automation or the platform has nothing of its own: its permission opens the sales.
        page = run("sale.sale.list", {}, ctx_for("hub_employee", actor="flow:7"))
        assert {row.number for row in page.rows} == {sales["ana"]["number"], sales["bea"]["number"]}
