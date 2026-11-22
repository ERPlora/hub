"""What Sales answers by the data permissions (BASE-F119), on every door: the route, the assistant and the live screens.

A comp is charged at 0 and the sale keeps what it cost the business (``gift_total``, SALE-F15), whoever sells it; only
whoever sees the costs (``base.view_costs``: the owner, an administrator and a manager) reads it, on the sale, on the
answer of its charge and on the preview of the charge. A charge names its customer by their name, or by their email or
phone only for whoever sees the customers' contact details (``base.view_customer_contact``, SALE-F04): naming them by
it would tell whose it is.

No basic role lacks the customers' contact today (an employee serves the customers by it): those tests take the
employee's role without it, as a role the business makes may be.
"""

import json

import pytest
from django.apps import apps
from django.test import RequestFactory
from live.assistant.running import run_tool
from live.context import system_context
from live.executor import Stream, Subscription, executor
from live.operations import get as operation

from apps.flow.tests.test_api import get, post
from apps.sale.models import Sale
from apps.sale.tests.conftest import HOST, HUB_DB, A, ctx_for, run
from base.operations import HubContextBuilder
from base.sensitive import VIEW_CUSTOMER_CONTACT

pytestmark = HUB_DB

EMAIL = "lucia@example.com"
PHONE = "+34600111222"
#: The cost of the wax: what its comp costs the business.
COST = 400


@pytest.fixture
def wax(product):
    product("Wax", "WAX", 900, "product.generic", cost=COST)


def charge(client, key: str, **more):
    """Charges a wax given as a comp and another one paid, by card."""
    lines = [{"product": "WAX", "is_gift": True}, {"product": "WAX"}]
    return post(client, "/sale/sales", {"idempotency_key": key, "lines": lines, "payments": [{"method": "card"}], **more})


def live_answer(user, name: str, params: dict) -> dict:
    """The data of ``name``'s live query for ``user``, as an open stream runs it."""
    request = RequestFactory().get("/api/live", HTTP_HOST=HOST)
    request.user, request.LANGUAGE_CODE = user, "en"
    op = operation(name)
    sub = Subscription(id="sensitive", op=op, params=op.input.model_validate(params))
    frame = executor._run_one(Stream(HubContextBuilder().from_request(request)), sub).decode()
    return json.loads(frame.split("data: ", 1)[1])["data"]


# ── What a comp cost ──────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("who", "cost"), [("ana", None), ("marta", COST)])
def test_a_sale_and_its_charge_carry_what_its_comps_cost_only_to_who_sees_the_costs(wax, people, who, cost):
    _, client = people[who]
    charged = charge(client, f"comp-cost-{who}-0001")
    assert charged.status_code == 201, charged.content
    sale = charged.json()
    detail = get(client, "/sale/sales/detail", sale=sale["number"]).json()
    by_key = get(client, "/sale/sales/by_key", idempotency_key=f"comp-cost-{who}-0001").json()["sale"]
    assert [sale["gift_total"], detail["gift_total"], by_key["gift_total"]] == [cost, cost, cost]
    assert Sale.objects.get(pk=sale["id"]).gift_total == COST


@pytest.mark.parametrize(("who", "cost"), [("ana", None), ("marta", COST)])
def test_the_preview_of_the_charge_carries_it_only_to_who_sees_the_costs(wax, people, who, cost):
    _, client = people[who]
    opened = post(client, "/sale/orders", {"lines": [{"product": "WAX", "is_gift": True}]})
    assert opened.status_code == 201, opened.content
    preview = get(client, "/sale/checkout/preview", order_id=opened.json()["id"])
    assert (preview.status_code, preview.json()["gift_total"], preview.json()["total"]) == (200, cost, 0)


@pytest.mark.parametrize(("role", "cost"), [("hub_employee", None), ("hub_manager", COST)])
def test_the_assistant_answers_it_only_to_who_sees_the_costs(wax, role, cost):
    sale = run("sale.sale.complete", {"idempotency_key": "comp-cost-tool-0001", "lines": [{"product": "WAX", "is_gift": True}],
                                      "payments": [{"method": "card"}]}, system_context(A))
    outcome = run_tool(ctx_for(role), operation("sale.sale.get"), json.dumps({"sale": sale.number}))
    assert outcome.outcome == "ok", outcome.content
    assert json.loads(outcome.content)["gift_total"] == cost


@pytest.mark.parametrize(("who", "cost"), [("ana", None), ("marta", COST)])
def test_the_live_sale_and_the_live_preview_answer_it_only_to_who_sees_the_costs(wax, people, monkeypatch, who, cost):
    # The executor's own run of one subscription; the test's transaction must stay open.
    monkeypatch.setattr("live.executor.close_old_connections", lambda: None)
    user, client = people[who]
    sale = charge(client, f"comp-cost-live-{who}-0001").json()
    order = post(client, "/sale/orders", {"lines": [{"product": "WAX", "is_gift": True}]}).json()
    seen = live_answer(user, "sale.sale.get", {"sale_id": sale["id"]}), live_answer(user, "sale.checkout.preview", {"order_id": order["id"]})
    assert [answer["gift_total"] for answer in seen] == [cost, cost]


# ── A customer named by their contact ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def lucia(customer):
    return customer("Lucía Gómez", email=EMAIL, phone=PHONE)


@pytest.fixture
def lacking(monkeypatch):
    """The employee's role without «View customer contact details»."""
    roles = apps.get_app_config("base").role_permissions
    monkeypatch.setitem(roles, "hub_employee", [name for name in roles["hub_employee"] if name != VIEW_CUSTOMER_CONTACT])


@pytest.mark.parametrize("reference", [EMAIL, PHONE, "600 111 222"])
def test_whoever_sees_the_contact_names_the_customer_of_a_charge_by_their_email_or_phone(wax, lucia, people, reference):
    charged = charge(people["ana"][1], "contact-seen-0001", customer=reference)
    assert (charged.status_code, charged.json()["customer_id"]) == (201, str(lucia.id)), charged.content


@pytest.mark.parametrize("reference", [EMAIL, PHONE, "600 111 222"])
def test_without_it_a_charge_cannot_name_its_customer_by_them_and_nothing_is_charged(wax, lucia, lacking, people, reference):
    refused = charge(people["ana"][1], "contact-hidden-0001", customer=reference)
    assert (refused.status_code, refused.json()["error"]["code"]) == (404, "customer.customer_unavailable")
    assert not Sale.objects.exists()


def test_without_it_the_customer_of_a_charge_is_still_named_by_their_name(wax, lucia, lacking, people):
    charged = charge(people["ana"][1], "contact-name-0001", customer="Lucía Gómez")
    assert (charged.status_code, charged.json()["customer_id"]) == (201, str(lucia.id)), charged.content


def test_nor_by_the_assistant(wax, lucia, lacking):
    data = {"idempotency_key": "contact-tool-0001", "lines": [{"product": "WAX"}], "payments": [{"method": "card"}]}
    refused = run_tool(ctx_for("hub_employee"), operation("sale.sale.complete"), json.dumps({**data, "customer": EMAIL}))
    assert (refused.outcome, refused.code) == ("error", "customer.customer_unavailable")
    charged = run_tool(ctx_for("hub_employee"), operation("sale.sale.complete"), json.dumps({**data, "customer": "Lucía Gómez"}))
    assert (charged.outcome, json.loads(charged.content)["customer_id"]) == ("ok", str(lucia.id)), charged.content
