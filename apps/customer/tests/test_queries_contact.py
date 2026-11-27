"""A customer's email and phone, and the address a consent was given for, reach only whoever sees the customers'
contact details (``base.view_customer_contact``). Anyone else gets the customers by their name, without them, on every
door (the API, the assistant, the live list, the export), and cannot find, filter or sort the customers by them. The
address, city, postal code and country are the tax details a sale copies for its invoice: everyone keeps them.

No basic role lacks the permission today (an employee serves the customers by it): these tests take the employee's and
the manager's roles without it, as a role the business makes may be."""

import csv
import io
import json

import pytest
from django.apps import apps
from django.test import RequestFactory
from live.assistant.running import run_tool
from live.executor import Stream, Subscription, executor
from live.operations import get as operation

from apps.customer.models import Customer
from apps.flow.tests.test_api import get
from base.operations import HubContextBuilder
from base.sensitive import VIEW_CUSTOMER_CONTACT
from base.tenancy.tests.business import A

from .conftest import HOST, HUB_DB, ctx_for

pytestmark = HUB_DB

EMAIL = "marta@example.com"
PHONE = "+34600111222"
TAX = {"tax_id": "12345678Z", "company_name": "Ruiz Peluqueros", "address": "Calle Mayor 1", "city": "Madrid",
       "postal_code": "28001", "country": "ES"}


@pytest.fixture
def marta(db):
    card = Customer.objects.create(name="Marta Ruiz", email=EMAIL, phone=PHONE, total_purchases=1, **TAX)
    grant = operation("customer.consent.grant")
    grant(ctx_for(), grant.input(customer_id=card.id, channel="email"))
    return card


@pytest.fixture
def lacking(monkeypatch):
    """The employee's and the manager's roles without «View customer contact details»."""
    roles = apps.get_app_config("base").role_permissions
    for role in ("hub_employee", "hub_manager"):
        monkeypatch.setitem(roles, role, [name for name in roles[role] if name != VIEW_CUSTOMER_CONTACT])


@pytest.fixture
def as_role(client, make_user):
    def sign_in(role: str):
        user = make_user(role, host=A.key, role=role)
        client.force_login(user)
        return user

    return sign_in


def contact(rows: list[dict]) -> list[tuple]:
    return [(row["name"], row["email"], row["phone"]) for row in rows]


def detail(client, **ref):
    return get(client, "/customer/customers/detail", **ref)


# ── What comes out ────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("role", ["hub_owner", "hub_manager", "hub_employee"])
def test_whoever_sees_the_contact_gets_the_customers_with_their_email_and_phone(marta, as_role, client, role):
    as_role(role)
    assert contact(get(client, "/customer/customers").json()["rows"]) == [("Marta Ruiz", EMAIL, PHONE)]
    card = detail(client, id=str(marta.id)).json()
    assert (card["email"], card["phone"], card["consent"][0]["contact_point"]) == (EMAIL, PHONE, EMAIL)


def test_without_it_the_list_and_the_card_come_without_email_or_phone_but_with_the_tax_details(
    marta, lacking, as_role, client
):
    as_role("hub_employee")
    assert contact(get(client, "/customer/customers").json()["rows"]) == [("Marta Ruiz", None, None)]
    card = detail(client, id=str(marta.id)).json()
    assert (card["email"], card["phone"], card["consent"][0]["contact_point"]) == (None, None, None)
    assert {field: card[field] for field in TAX} == TAX


def test_without_it_the_consent_comes_without_the_address_it_was_given_for(marta, lacking, as_role, client):
    as_role("hub_employee")
    state = get(client, "/customer/consents/state", customer_id=str(marta.id)).json()["rows"]
    history = get(client, "/customer/consents", customer_id=str(marta.id)).json()["rows"]
    assert [row["contact_point"] for row in state + history] == [None, None]


def test_the_assistant_gives_the_card_without_contact_to_whoever_lacks_it(marta, monkeypatch):
    def card() -> tuple:
        outcome = run_tool(ctx_for("hub_employee"), operation("customer.customer.detail"), json.dumps({"id": str(marta.id)}))
        assert outcome.outcome == "ok", outcome.content
        answer = json.loads(outcome.content)
        return answer["email"], answer["phone"], answer["tax_id"]

    assert card() == (EMAIL, PHONE, TAX["tax_id"])
    roles = apps.get_app_config("base").role_permissions
    monkeypatch.setitem(roles, "hub_employee", [name for name in roles["hub_employee"] if name != VIEW_CUSTOMER_CONTACT])
    assert card() == (None, None, TAX["tax_id"])


def test_the_live_list_answers_without_contact_to_whoever_lacks_it(marta, make_user, monkeypatch):
    # The executor's own run of one subscription, as an open stream does it; the test's transaction must stay open.
    monkeypatch.setattr("live.executor.close_old_connections", lambda: None)
    employee = make_user("eva", host=A.key, role="hub_employee")

    def rows() -> list[tuple]:
        request = RequestFactory().get("/api/live", HTTP_HOST=HOST)
        request.user, request.LANGUAGE_CODE = employee, "en"
        stream = Stream(HubContextBuilder().from_request(request))
        op = operation("customer.customer.list")
        sub = Subscription(id="customers", op=op, params=op.input.model_validate({}))
        frame = executor._run_one(stream, sub).decode()
        return contact(json.loads(frame.split("data: ", 1)[1])["data"]["rows"])

    assert rows() == [("Marta Ruiz", EMAIL, PHONE)]
    roles = apps.get_app_config("base").role_permissions
    monkeypatch.setitem(roles, "hub_employee", [name for name in roles["hub_employee"] if name != VIEW_CUSTOMER_CONTACT])
    assert rows() == [("Marta Ruiz", None, None)]


# ── Finding, filtering and sorting by them ────────────────────────────────────────────────────────────────────────


def test_asking_whose_a_number_is_is_refused_without_it(marta, lacking, as_role, client):
    as_role("hub_manager")
    refused = get(client, "/customer/customers/by_phone", phone="600 111 222")
    assert (refused.status_code, refused.json()["error"]["code"]) == (403, "permission_denied")
    as_role("hub_owner")
    assert contact(get(client, "/customer/customers/by_phone", phone="600 111 222").json()["rows"]) == [
        ("Marta Ruiz", EMAIL, PHONE)
    ]


@pytest.mark.parametrize(("field", "value"), [("email", "example.com"), ("phone", "600111")])
def test_filtering_by_email_or_phone_is_refused_without_it(marta, lacking, as_role, client, field, value):
    as_role("hub_owner")
    assert get(client, "/customer/customers", **{field: value}).json()["total"] == 1
    as_role("hub_employee")
    refused = get(client, "/customer/customers", **{field: value})
    assert (refused.status_code, refused.json()["error"]["code"]) == (403, "permission_denied")


@pytest.mark.parametrize("sort", ["email", "phone"])
def test_the_customers_are_not_sorted_by_email_or_phone(marta, as_role, client, sort):
    as_role("hub_owner")
    assert get(client, "/customer/customers", sort=sort).status_code == 422


def test_without_it_the_customers_are_still_sorted_by_the_other_columns(marta, lacking, as_role, client):
    Customer.objects.create(name="Ana Soto", total_spent=900)
    as_role("hub_employee")
    answer = get(client, "/customer/customers", sort="total_spent", descending="true")
    assert [row["name"] for row in answer.json()["rows"]] == ["Ana Soto", "Marta Ruiz"]


@pytest.mark.parametrize("text", ["600 111", "+34 600", "example.com", "marta@"])
def test_the_search_looks_into_email_and_phone_only_for_whoever_sees_them(marta, lacking, as_role, client, text):
    as_role("hub_owner")
    assert get(client, "/customer/customers", search=text).json()["total"] == 1
    as_role("hub_employee")
    assert get(client, "/customer/customers", search=text).json()["total"] == 0


@pytest.mark.parametrize("text", ["marta", "12345678z", "peluqueros"])
def test_without_it_the_search_still_finds_by_name_tax_id_and_company(marta, lacking, as_role, client, text):
    as_role("hub_employee")
    assert get(client, "/customer/customers", search=text).json()["total"] == 1


def test_the_audit_of_figures_searches_the_contact_only_for_whoever_sees_it(marta, lacking, as_role, client):
    # Marta's card counts a purchase its history does not have: she is among the cards whose figures disagree.
    as_role("hub_owner")
    assert get(client, "/customer/purchases/divergences", search="600111").json()["total"] == 1
    as_role("hub_employee")
    assert get(client, "/customer/purchases/divergences", search="600111").json()["total"] == 0
    assert get(client, "/customer/purchases/divergences", search="marta").json()["total"] == 1


def test_the_consent_history_searches_the_address_only_for_whoever_sees_it(marta, lacking, as_role, client):
    params = {"customer_id": str(marta.id), "search": "example.com"}
    as_role("hub_owner")
    assert get(client, "/customer/consents", **params).json()["total"] == 1
    as_role("hub_employee")
    assert get(client, "/customer/consents", **params).json()["total"] == 0


READS_BY_REFERENCE = [
    "/customer/customers/detail",
    "/customer/activity",
    "/customer/purchases",
    "/customer/consents",
    "/customer/consents/state",
    "/customer/orders",
    "/customer/health",
]


@pytest.mark.parametrize("path", READS_BY_REFERENCE)
@pytest.mark.parametrize("reference", [PHONE, "600 111 222", EMAIL])
def test_a_card_named_by_its_phone_or_email_is_found_only_by_whoever_sees_them(
    marta, lacking, as_role, client, path, reference
):
    as_role("hub_owner")
    assert get(client, path, customer=reference).status_code == 200
    as_role("hub_manager")
    missing = get(client, path, customer=reference)
    assert (missing.status_code, missing.json()["error"]["code"]) == (404, "customer.customer_unavailable")
    assert get(client, path, customer="Marta Ruiz").status_code == 200


# ── The export ────────────────────────────────────────────────────────────────────────────────────────────────────


def exported(client, **params) -> list[dict]:
    answer = get(client, "/customer/customers/export", **params)
    assert answer.status_code == 200, answer.content
    return list(csv.DictReader(io.StringIO(answer.json()["csv"])))


def test_the_export_carries_the_email_and_phone_to_whoever_sees_them(marta, as_role, client):
    as_role("hub_manager")
    [row] = exported(client)
    assert (row["email"], row["phone"].lstrip("'"), row["address"]) == (EMAIL, PHONE, TAX["address"])


def test_without_it_the_export_has_no_email_or_phone_column(marta, lacking, as_role, client):
    as_role("hub_manager")
    [row] = exported(client)
    assert "email" not in row and "phone" not in row
    assert (row["name"], row["tax_id"], row["address"]) == ("Marta Ruiz", TAX["tax_id"], TAX["address"])


def test_without_it_the_export_does_not_search_the_contact(marta, lacking, as_role, client):
    as_role("hub_manager")
    assert exported(client, search="600 111") == []
    assert len(exported(client, search="marta")) == 1
