"""What the cashier's role does not allow at the till, a manager approves on the spot with their PIN (BASE-F84; the old
hub's HUB_SHELL-F51; Square, Toast, Lightspeed and Shopify's manager override): SALE-F30 and F31 (void and refund a
sale), F20 (void an item sent to the kitchen), F14 (a discount above the maximum, on a line, on the check or at the
charge), F09 (an open price) and F18 (delete an open check with something on it).

The app names those commands in its ``LiveAppConfig.approvals``; the cashier who asks gets «An approval is needed»
(``requires_elevation``) instead of a flat refusal, a manager approves that very request with their PIN and it is done
once, with everything it does when the manager does it: the rectifying invoice in the void itself, the voucher's
sessions back, the event. Who holds the permission is never asked. Over HTTP, as the till asks: the approval's door
sits in front of the routes (``base.approvals``).
"""

import json
from dataclasses import replace

import pytest
from django.apps import apps
from django.core.cache import cache
from django.utils import translation
from live.errors import PermissionDenied
from live.meta import all_live_app_configs, permissions_for_role
from live.models import OutboxEvent
from live.operations import get as operation

from apps.invoice.models import Invoice
from apps.sale.models import Order, OrderLine, Sale, SaleLine
from apps.sale.tests.conftest import run
from apps.sale.tests.test_integration_invoice import ISSUER
from apps.sale.tests.test_integration_service import charged_with_voucher
from apps.service.models import Redemption
from base.models import Credential
from base.tests.test_people import with_pin

pytestmark = pytest.mark.django_db

HOST = "a.localhost"

#: The commands of the till a manager may approve, and what the dialog says is approved.
APPROVABLE = {
    "sale.sale.void": ("Void a sale", "Anular una venta"),
    "sale.sale.refund": ("Refund a sale", "Devolver una venta"),
    "sale.order.void_line": ("Void an item already sent to the kitchen", "Anular un artículo ya enviado a cocina"),
    "sale.order.set_line_discount_over_limit": (
        "Discount a line above the maximum",
        "Descontar una línea por encima del máximo",
    ),
    "sale.order.set_discount_over_limit": (
        "Discount the check above the maximum",
        "Descontar la cuenta por encima del máximo",
    ),
    "sale.sale.complete_over_limit": (
        "Charge with a discount above the maximum",
        "Cobrar con un descuento por encima del máximo",
    ),
    "sale.order.add_open_line": ("Sell at an open price", "Vender a precio libre"),
    "sale.order.void_ordered": (
        "Delete an open check with something on it",
        "Eliminar una cuenta abierta con algo pedido",
    ),
}


def post(client, path, data, **headers):
    return client.post(f"/api{path}", json.dumps(data), content_type="application/json", HTTP_HOST=HOST, **headers)


def code(response) -> str:
    return response.json()["error"]["code"]


def asked(response) -> dict:
    """The approval's question in a refusal: 403 ``requires_elevation`` with what is approved."""
    assert response.status_code == 403, response.content
    assert code(response) == "requires_elevation", response.content
    return response.json()["error"]["approval"]


def approve(client, question: dict, person: str = "mario", pin: str = "1357") -> str:
    """``person`` approves ``question`` with their PIN on the cashier's device: the pass of one use."""
    credential = str(Credential.objects.get(username=person).pk)
    body = {"operation": question["operation"], "fingerprint": question["fingerprint"], "person": credential, "pin": pin}
    response = post(client, "/approvals", body)
    assert response.status_code == 200, response.content
    return response.json()["token"]


def with_pass(token: str) -> dict:
    return {"HTTP_X_ELEVATION_TOKEN": token}


def through_approval(client, path: str, data: dict):
    """The cashier asks, the manager approves with their PIN, the cashier's very request goes again with the pass."""
    question = asked(post(client, path, data))
    return post(client, path, data, **with_pass(approve(client, question)))


def events(name: str) -> list[dict]:
    return list(OutboxEvent.objects.filter(name=name).values_list("payload", flat=True))


@pytest.fixture(autouse=True)
def no_brakes():
    """The PIN pad's brakes live in the cache: each test starts without the attempts of another."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def manager(make_user):
    """Mario, a manager of the business with a PIN: the one who approves."""
    user = make_user("mario", role="hub_manager")
    with_pin("mario", "1357")
    return user


@pytest.fixture
def cashier(client, make_user, manager):
    """Eva, an employee (the old cashier) on the till's device, with Mario there to approve."""
    client.force_login(make_user("eva", role="hub_employee"))
    return client


@pytest.fixture
def coffee(product):
    return product("Coffee", "COF", 150, "restaurant.drink")


def charge(client, key: str = "approval-key-0001", **more) -> dict:
    """The cashier charges a coffee by card, over HTTP."""
    body = {"idempotency_key": key, "lines": [{"product": "COF"}], "payments": [{"method": "card"}], **more}
    response = post(client, "/sale/sales", body)
    assert response.status_code == 201, response.content
    return response.json()


def open_check(client, *lines: dict) -> dict:
    response = post(client, "/sale/orders", {"lines": list(lines or [{"product": "COF"}])})
    assert response.status_code == 201, response.content
    return response.json()


def cap(percent: int) -> None:
    run("sale.settings.update", {"max_discount_percent": percent})


# ── What the till names ──────────────────────────────────────────────────────────────────────────────────────────────


class TestWhatTheTillNames:
    def test_the_till_names_in_words_what_a_manager_may_approve(self):
        named = apps.get_app_config("sale").approvals
        assert set(named) == set(APPROVABLE)
        for name, (english, spanish) in APPROVABLE.items():
            with translation.override("en"):
                assert str(named[name]) == english
            with translation.override("es"):
                assert str(named[name]) == spanish

    def test_each_one_is_a_command_the_cashier_lacks_and_the_manager_holds(self):
        configs = all_live_app_configs()
        cashier, manager = permissions_for_role(configs, "hub_employee"), permissions_for_role(configs, "hub_manager")
        for name in APPROVABLE:
            op = operation(name)
            assert op.kind == "command" and op.permission, name
            assert op.permission not in cashier, name
            assert op.permission in manager or "sale.*" in manager, name


# ── SALE-F30 Void a sale ─────────────────────────────────────────────────────────────────────────────────────────────


class TestVoid:
    def test_the_cashier_who_voids_is_asked_for_an_approval_naming_it_and_nothing_changes(self, cashier, coffee):
        sale = charge(cashier)
        question = asked(post(cashier, "/sale/sales/void", {"sale_id": sale["id"], "reason": "Wrong table"}))
        assert (question["operation"], question["label"]) == ("sale.sale.void", "Void a sale")
        assert Sale.objects.get(pk=sale["id"]).status == "completed"
        assert events("sale.sale.voided") == []

    def test_the_managers_pin_voids_it_once_with_its_rectifying_invoice_in_the_void_itself(self, cashier, coffee):
        run("invoice.issuer.update", ISSUER)
        sale = charge(cashier)
        body = {"sale_id": sale["id"], "reason": "Wrong table"}
        question = asked(post(cashier, "/sale/sales/void", body))
        token = approve(cashier, question)
        voided = post(cashier, "/sale/sales/void", body, **with_pass(token))
        assert voided.status_code == 200, voided.content
        assert (voided.json()["status"], voided.json()["void_invoice_status"]) == ("voided", "issued")
        rectification = Invoice.objects.get(number=voided.json()["void_invoice_number"])
        assert (rectification.invoice_type, rectification.total_amount) == ("R5", -sale["total"])
        [event] = events("sale.sale.voided")
        assert (event["sale_id"], event["voided_by"], event["reason"]) == (sale["id"], "eva", "Wrong table")
        # One use: the same request again is the question again, never a second void.
        assert code(post(cashier, "/sale/sales/void", body, **with_pass(token))) == "requires_elevation"
        assert len(events("sale.sale.voided")) == 1

    def test_an_approved_void_gives_the_vouchers_sessions_back(self, cashier, product, customer):
        haircut = run(
            "service.service.create",
            {"name": "Haircut", "price": 2500, "tax_category_key": "service.generic"},
        )
        grant, sale, line = charged_with_voucher(haircut, customer("Lucía Pérez"))
        voided = through_approval(cashier, "/sale/sales/void", {"sale_id": str(sale.id), "reason": "wrong customer"})
        assert voided.status_code == 200, voided.content
        session = Redemption.objects.get(pk=SaleLine.objects.get(pk=line.id).voucher_session_id)
        assert session.status == "returned"

    def test_who_holds_the_permission_voids_without_a_question(self, client, manager, coffee):
        client.force_login(manager)
        sale = charge(client)
        response = post(client, "/sale/sales/void", {"sale_id": sale["id"], "reason": "Wrong table"})
        assert response.status_code == 200, response.content
        assert response.json()["voided_by"] == "mario"


# ── SALE-F31 Refund a sale ───────────────────────────────────────────────────────────────────────────────────────────


def refund_body(sale: dict, amount: int, key: str = "approval-refund-0001") -> dict:
    payment = Sale.objects.get(pk=sale["id"]).payments.get()
    return {
        "sale_id": sale["id"],
        "reason": "Broken",
        "idempotency_key": key,
        "allocations": [{"payment_id": str(payment.id), "amount": amount}],
    }


class TestRefund:
    def test_the_cashier_who_refunds_is_asked_for_an_approval_naming_it(self, cashier, coffee):
        sale = charge(cashier)
        question = asked(post(cashier, "/sale/sales/refund", refund_body(sale, 150)))
        assert (question["operation"], question["label"]) == ("sale.sale.refund", "Refund a sale")
        assert Sale.objects.get(pk=sale["id"]).refunded_total == 0

    def test_the_managers_pin_refunds_it_once_with_its_rectifying_invoice(self, cashier, coffee):
        run("invoice.issuer.update", ISSUER)
        sale = charge(cashier)
        refunded = through_approval(cashier, "/sale/sales/refund", refund_body(sale, 150))
        assert refunded.status_code == 200, refunded.content
        answer = refunded.json()
        assert (answer["fully_refunded"], answer["invoice_status"], answer["invoice_type"]) == (True, "issued", "R5")
        assert Sale.objects.get(pk=sale["id"]).status == "refunded"
        assert len(events("sale.sale.refunded")) == 1

    def test_an_approved_refund_gives_the_voucher_session_back(self, cashier, customer):
        haircut = run(
            "service.service.create",
            {"name": "Haircut", "price": 2500, "tax_category_key": "service.generic"},
        )
        grant, sale, line = charged_with_voucher(haircut, customer("Lucía Pérez"))
        body = {"sale_id": str(sale.id), "reason": "did not come", "lines": [{"line_id": str(line.id)}]}
        refunded = through_approval(cashier, "/sale/sales/refund", body)
        assert refunded.status_code == 200, refunded.content
        session = Redemption.objects.get(pk=SaleLine.objects.get(pk=line.id).voucher_session_id)
        assert session.status == "returned"


# ── SALE-F20 Void an item already sent to the kitchen ────────────────────────────────────────────────────────────────


class TestVoidLine:
    def test_the_managers_pin_voids_an_item_sent_to_the_kitchen_with_its_reason(self, cashier, coffee):
        order = open_check(cashier)
        fired = post(cashier, "/sale/orders/fire", {"order_id": order["id"]})
        assert fired.status_code == 200, fired.content
        line_id = order["lines"][0]["id"]
        body = {"order_id": order["id"], "line_id": line_id, "reason": "Agotado"}
        assert asked(post(cashier, "/sale/orders/void_line", body))["label"] == "Void an item already sent to the kitchen"
        voided = through_approval(cashier, "/sale/orders/void_line", body)
        assert voided.status_code == 200, voided.content
        assert voided.json()["lines"] == []
        line = OrderLine.objects.get(pk=line_id)
        # The line keeps who authorised it: the manager who approved it with their PIN.
        assert (line.removed_at is not None, line.void_reason, line.voided_by) == (True, "Agotado", "mario")
        assert [event["reason"] for event in events("sale.order.line_voided")] == ["Agotado"]


# ── SALE-F14 A discount above the maximum ────────────────────────────────────────────────────────────────────────────


class TestDiscountAboveTheMaximum:
    def test_a_line_discount_above_the_maximum_is_approved_and_keeps_who_approved_it(self, cashier, coffee):
        cap(10)
        order = open_check(cashier)
        body = {"order_id": order["id"], "line_id": order["lines"][0]["id"], "discount_percent": "50"}
        refused = post(cashier, "/sale/orders/set_line_discount", body)
        assert code(refused) == "sale.discount_over_limit"
        approved = through_approval(cashier, "/sale/orders/set_line_discount_over_limit", body)
        assert approved.status_code == 200, approved.content
        line = OrderLine.objects.get(pk=order["lines"][0]["id"])
        assert (str(line.discount_percent), line.discount_approved_by) == ("50.00", "mario")

    def test_a_check_discount_above_the_maximum_is_approved_and_the_charge_does_not_ask_again(self, cashier, coffee):
        cap(10)
        order = open_check(cashier)
        body = {"order_id": order["id"], "discount_percent": "50"}
        assert code(post(cashier, "/sale/orders/set_discount", body)) == "sale.discount_over_limit"
        approved = through_approval(cashier, "/sale/orders/set_discount_over_limit", body)
        assert approved.status_code == 200, approved.content
        assert Order.objects.get(pk=order["id"]).discount_approved_by == "mario"
        charged = post(
            cashier,
            "/sale/sales",
            {
                "idempotency_key": "approval-key-0002",
                "order_id": order["id"],
                "order_version": approved.json()["version"],
                "payments": [{"method": "card"}],
            },
        )
        assert charged.status_code == 201, charged.content
        assert charged.json()["total"] == 75

    def test_a_charge_with_a_discount_above_the_maximum_is_approved(self, cashier, coffee):
        cap(10)
        body = {
            "idempotency_key": "approval-key-0003",
            "lines": [{"product": "COF"}],
            "discount_percent": "50",
            "payments": [{"method": "card"}],
        }
        assert code(post(cashier, "/sale/sales", body)) == "sale.discount_over_limit"
        question = asked(post(cashier, "/sale/sales/complete_over_limit", body))
        assert question["label"] == "Charge with a discount of 50%"
        charged = post(cashier, "/sale/sales/complete_over_limit", body, **with_pass(approve(cashier, question)))
        assert charged.status_code == 201, charged.content
        assert charged.json()["total"] == 75


# ── SALE-F09 Sell at an open price ───────────────────────────────────────────────────────────────────────────────────


class TestOpenPrice:
    def test_the_managers_pin_lets_the_cashier_add_an_open_price(self, cashier, coffee):
        order = open_check(cashier)
        body = {"order_id": order["id"], "unit_price": 420, "tax_category_key": "restaurant.food"}
        assert asked(post(cashier, "/sale/orders/add_open_line", body))["label"] == "Sell at an open price of €4.20"
        added = through_approval(cashier, "/sale/orders/add_open_line", body)
        assert added.status_code == 200, added.content
        assert [line["unit_price"] for line in added.json()["lines"]] == [150, 420]


# ── SALE-F14 and F09 What is approved, with its figure ───────────────────────────────────────────────────────────────
# sales#398, sales#403, hub#2180: the manager read «Discount a line above the maximum» and approved blind. «An
# approval is needed» says how much they approve, as Square, Toast and Lightspeed print it («Discount 50% requires
# manager»): the sentences of ``approval_figures`` (BASE-F84), filled with the figures of that very request in the
# language of whoever asks; an amount in the business's currency. A figure in zero or empty fills no hole: the next
# sentence, or the words of always, never half a sentence. Void, refund, void an item and delete a check say no
# figure: their input has none on its first level (an amount of a refund lives in its tenders).


def asked_in(client, path: str, data: dict, language: str) -> str:
    """What «An approval is needed» says is approved for that very request, in ``language``."""
    return asked(post(client, path, data, HTTP_ACCEPT_LANGUAGE=language))["label"]


@pytest.fixture
def menu(product):
    return product("Menu", "MEN", 2500, "restaurant.food")


LINE_OVER = "/sale/orders/set_line_discount_over_limit"
CHECK_OVER = "/sale/orders/set_discount_over_limit"
CHARGE_OVER = "/sale/sales/complete_over_limit"


class TestWhatIsApprovedWithItsFigure:
    def test_only_the_commands_with_a_figure_in_their_request_say_one_and_the_platform_s_check_passes(self):
        from django.core import checks

        sale = apps.get_app_config("sale")
        assert set(sale.approval_figures) == {
            "sale.order.set_line_discount_over_limit",
            "sale.order.set_discount_over_limit",
            "sale.sale.complete_over_limit",
            "sale.order.add_open_line",
        }
        assert [error.msg for error in checks.run_checks(tags=["base"]) if error.id == "base.E008"] == []

    def test_a_line_discount_says_its_percentage(self, cashier, coffee):
        cap(10)
        order = open_check(cashier)
        body = {"order_id": order["id"], "line_id": order["lines"][0]["id"], "discount_percent": "50"}
        assert asked_in(cashier, LINE_OVER, body, "en") == "Discount a line by 50%"
        assert asked_in(cashier, LINE_OVER, body, "es") == "Descontar una línea un 50\xa0%"
        assert asked_in(cashier, LINE_OVER, {**body, "discount_percent": "12.5"}, "es") == "Descontar una línea un 12,5\xa0%"

    def test_a_check_discount_says_its_percentage_or_its_amount_in_the_business_s_currency(self, cashier, menu):
        cap(10)
        order = open_check(cashier, {"product": "MEN"})
        percent = {"order_id": order["id"], "discount_percent": "50", "discount_amount": 0}
        assert asked_in(cashier, CHECK_OVER, percent, "en") == "Discount the check by 50%"
        assert asked_in(cashier, CHECK_OVER, percent, "es") == "Descontar la cuenta un 50\xa0%"
        amount = {"order_id": order["id"], "discount_percent": "0", "discount_amount": 1250}
        assert asked_in(cashier, CHECK_OVER, amount, "en") == "Discount the check by €12.50"
        assert asked_in(cashier, CHECK_OVER, amount, "es") == "Descontar 12,50\xa0€ de la cuenta"
        both = {"order_id": order["id"], "discount_percent": "5", "discount_amount": 1000}
        assert asked_in(cashier, CHECK_OVER, both, "en") == "Discount the check by 5% and €10.00"
        assert asked_in(cashier, CHECK_OVER, both, "es") == "Descontar la cuenta un 5\xa0% y 10,00\xa0€"

    def test_a_figure_in_zero_or_empty_never_leaves_half_a_sentence(self, cashier, menu):
        order = open_check(cashier, {"product": "MEN"})
        # Neither a percentage nor an amount: the words of always, never «Discount the check by ».
        nothing = {"order_id": order["id"], "discount_percent": "0"}
        assert asked_in(cashier, CHECK_OVER, nothing, "en") == "Discount the check above the maximum"
        assert asked_in(cashier, CHECK_OVER, {**nothing, "discount_amount": 0}, "es") == (
            "Descontar la cuenta por encima del máximo"
        )

    def test_a_charge_above_the_maximum_says_the_discount_it_charges(self, cashier, menu):
        cap(10)
        body = {"idempotency_key": "approval-figure-0001", "lines": [{"product": "MEN"}], "payments": [{"method": "card"}]}
        assert asked_in(cashier, CHARGE_OVER, {**body, "discount_percent": "50"}, "en") == "Charge with a discount of 50%"
        assert asked_in(cashier, CHARGE_OVER, {**body, "discount_percent": "50"}, "es") == "Cobrar con un descuento del 50\xa0%"
        assert asked_in(cashier, CHARGE_OVER, {**body, "discount_amount": 1250}, "en") == "Charge with a discount of €12.50"
        assert asked_in(cashier, CHARGE_OVER, {**body, "discount_amount": 1250}, "es") == "Cobrar con un descuento de 12,50\xa0€"
        both = {**body, "discount_percent": "5", "discount_amount": 1000}
        assert asked_in(cashier, CHARGE_OVER, both, "en") == "Charge with a discount of 5% and €10.00"
        assert asked_in(cashier, CHARGE_OVER, both, "es") == "Cobrar con un descuento del 5\xa0% y 10,00\xa0€"

    def test_the_charge_of_a_check_says_the_words_of_always(self, cashier, menu):
        # The check's own discount is not in the charge's request: no figure is read, so no half a sentence either.
        order = open_check(cashier, {"product": "MEN"})
        body = {"idempotency_key": "approval-figure-0002", "order_id": order["id"], "payments": [{"method": "card"}]}
        assert asked_in(cashier, CHARGE_OVER, body, "en") == "Charge with a discount above the maximum"

    def test_a_check_charge_with_a_discount_figure_in_its_body_is_refused_before_any_approval(self, cashier, menu):
        # The charge of a check takes no discount of its own (it lives in the check), so a figure in its body would be
        # said by the dialog and ignored by the charge: a crafted request could show the manager a figure the check does
        # not have. The dialog says the words of always (the body is no valid request, so no figure is read) and the
        # charge itself refuses that body.
        order = open_check(cashier, {"product": "MEN"})
        body = {"idempotency_key": "approval-figure-0003", "order_id": order["id"], "payments": [{"method": "card"}]}
        for figure in ({"discount_percent": "1"}, {"discount_amount": 100}):
            assert asked_in(cashier, CHARGE_OVER, {**body, **figure}, "en") == "Charge with a discount above the maximum"
            response = through_approval(cashier, CHARGE_OVER, {**body, **figure})
            assert response.status_code == 422, response.content
            assert "set on the check itself" in response.content.decode(), response.content

    def test_an_open_price_says_its_amount(self, cashier, coffee):
        order = open_check(cashier)
        body = {"order_id": order["id"], "unit_price": 420, "tax_category_key": "restaurant.food"}
        assert asked_in(cashier, "/sale/orders/add_open_line", body, "en") == "Sell at an open price of €4.20"
        assert asked_in(cashier, "/sale/orders/add_open_line", body, "es") == "Vender a precio libre por 4,20\xa0€"

    def test_the_manager_approves_that_figure_and_the_record_says_it(self, client, cashier, coffee, make_user):
        cap(10)
        order = open_check(cashier)
        body = {"order_id": order["id"], "line_id": order["lines"][0]["id"], "discount_percent": "50"}
        question = asked(post(cashier, LINE_OVER, body, HTTP_ACCEPT_LANGUAGE="es"))
        assert question["label"] == "Descontar una línea un 50\xa0%"
        done = post(cashier, LINE_OVER, body, **with_pass(approve(cashier, question)))
        assert done.status_code == 200, done.content
        line = OrderLine.objects.get(pk=order["lines"][0]["id"])
        assert (str(line.discount_percent), line.discount_approved_by) == ("50.00", "mario")
        # Employees › Approvals (BASE-F85): the owner reads what Mario approved, with its figure, in their language.
        client.force_login(make_user("ana", role="hub_owner"))
        rows = client.get("/api/approvals", HTTP_HOST=HOST, HTTP_ACCEPT_LANGUAGE="en").json()["approvals"]
        assert [(row["action"], row["operation_label"]) for row in rows] == [
            ("Discount a line by 50%", "Discount a line above the maximum")
        ]


# ── SALE-F18 Delete an open check ────────────────────────────────────────────────────────────────────────────────────


class TestDeleteAnOpenCheck:
    def test_an_empty_check_is_still_deleted_by_whoever_builds_checks(self, cashier, coffee):
        order = open_check(cashier)
        removed = post(cashier, "/sale/orders/remove_line", {"order_id": order["id"], "line_id": order["lines"][0]["id"]})
        assert removed.status_code == 200, removed.content
        voided = post(cashier, "/sale/orders/void", {"order_id": order["id"]})
        assert voided.status_code == 200, voided.content
        assert voided.json()["status"] == "voided"

    def test_one_with_something_on_it_is_refused_flat_by_the_ordinary_door(self, cashier, coffee):
        order = open_check(cashier)
        assert code(post(cashier, "/sale/orders/void", {"order_id": order["id"]})) == "permission_denied"

    def test_the_managers_pin_deletes_one_with_something_on_it(self, cashier, coffee):
        order = open_check(cashier)
        body = {"order_id": order["id"]}
        question = asked(post(cashier, "/sale/orders/void_ordered", body))
        assert question["label"] == "Delete an open check with something on it"
        voided = post(cashier, "/sale/orders/void_ordered", body, **with_pass(approve(cashier, question)))
        assert voided.status_code == 200, voided.content
        assert Order.objects.get(pk=order["id"]).status == "voided"
        assert events("sale.order.voided") == [{"order_id": order["id"]}]

    def test_the_manager_deletes_it_through_either_door(self, client, manager, coffee):
        client.force_login(manager)
        first, second = open_check(client), open_check(client)
        assert post(client, "/sale/orders/void", {"order_id": first["id"]}).json()["status"] == "voided"
        assert post(client, "/sale/orders/void_ordered", {"order_id": second["id"]}).json()["status"] == "voided"


# ── What goes with an approved command, and nothing more ─────────────────────────────────────────────────────────────


#: What the cashier may not do in Invoicing and Services, and an approved void or refund does on the way.
RECTIFY, RETURN_SESSION = "invoice.rectify_invoice", "service.return_session"


@pytest.fixture
def platform_rule(monkeypatch):
    """Every operation of another app the till runs through the platform's one door (``base.operations.call``), as
    ``(operation, the command running, whether it went with an approval)``: what ``base.approvals.consequence_context``
    gave it. Sales has no rule of its own."""
    from live.operations import current_operation

    from base import operations as platform

    rule, seen = platform.consequence_context, []

    def spy(ctx, op):
        given = rule(ctx, op)
        running = current_operation.get()
        seen.append((op.name, running.name if running else None, given is not ctx))
        return given

    monkeypatch.setattr(platform, "consequence_context", spy)
    return seen


def while_running(seen: list, name: str) -> list:
    """The calls of ``seen`` made by the command ``name`` itself (not by what it calls in turn)."""
    return [(called, carried) for called, running, carried in seen if running == name]


@pytest.fixture
def haircut_with_shampoo(product, customer):
    """A haircut paid with a voucher session and a shampoo by card, charged with Invoicing's ticket: Lucía's sale."""
    run("invoice.issuer.update", ISSUER)
    product("Shampoo", "SHA", 1200, "product.generic")
    haircut = run("service.service.create", {"name": "Haircut", "price": 2500, "tax_category_key": "service.generic"})
    _grant, sale, line = charged_with_voucher(haircut, customer("Lucía Pérez"), product=True)
    return sale, line


def the_cashiers_context(*, approved: str | None = None):
    """Eva's context, with the one permission more of ``approved`` and its mark on the request, as the platform builds
    it for a command a manager approved; ``None``: no approval and no request."""
    from types import SimpleNamespace

    from apps.sale.tests.conftest import ctx_for
    from base.approvals import Approved

    ctx = ctx_for("hub_employee", actor="eva")
    if approved is None:
        return replace(ctx, permissions=ctx.permissions | {"sale.void_sale"})
    op = operation(approved)
    mark = Approved(operation=op.name, permission=op.permission, token="elev_x", fingerprint="f" * 64)
    return replace(ctx, permissions=ctx.permissions | {op.permission}, request=SimpleNamespace(approved=mark))


class TestWhatGoesWithIt:
    """What a command a manager approved asks of another app goes with it, by the platform's rule (BASE-F84): only the
    commands of another app the approved command itself runs, a read never, and without an approval the caller's own
    permissions decide."""

    def test_the_cashier_may_not_rectify_nor_give_sessions_back_on_their_own(self):
        cashier = permissions_for_role(all_live_app_configs(), "hub_employee")
        assert RECTIFY not in cashier and RETURN_SESSION not in cashier

    def test_an_approved_void_takes_the_rectifying_invoice_and_the_sessions_with_it(
        self, cashier, haircut_with_shampoo, platform_rule
    ):
        sale, line = haircut_with_shampoo
        voided = through_approval(cashier, "/sale/sales/void", {"sale_id": str(sale.id), "reason": "wrong customer"})
        assert voided.status_code == 200, voided.content
        assert voided.json()["void_invoice_status"] == "issued"
        assert Redemption.objects.get(pk=SaleLine.objects.get(pk=line.id).voucher_session_id).status == "returned"
        assert while_running(platform_rule, "sale.sale.void") == [
            ("service.session.return", True),
            ("invoice.invoice.rectify_from_void", True),
        ]

    def test_an_approved_refund_takes_its_rectifying_invoice_and_the_session_with_it(
        self, cashier, haircut_with_shampoo, platform_rule
    ):
        sale, line = haircut_with_shampoo
        card = Sale.objects.get(pk=sale.id).payments.get()
        body = {
            "sale_id": str(sale.id),
            "reason": "did not come",
            "idempotency_key": "approval-refund-0002",
            "lines": [{"line_id": str(line.id)}],
            "allocations": [{"payment_id": str(card.id), "amount": 1200}],
        }
        refunded = through_approval(cashier, "/sale/sales/refund", body)
        assert refunded.status_code == 200, refunded.content
        assert refunded.json()["invoice_status"] == "issued"
        assert Redemption.objects.get(pk=SaleLine.objects.get(pk=line.id).voucher_session_id).status == "returned"
        assert while_running(platform_rule, "sale.sale.refund") == [
            ("service.session.return", True),
            ("invoice.invoice.rectify_from_refund", True),
        ]

    def test_a_read_and_what_the_cashier_already_may_keep_the_cashiers_own(
        self, cashier, coffee, platform_rule, monkeypatch
    ):
        # Cash register in the business (the conftest takes it out), charging cash without an open drawer.
        monkeypatch.setattr("apps.sale.services.DRAWER_CHECK", "cash_register.session.current")
        run("cash_register.settings.update", {"enable_cash_register": False})
        run("invoice.issuer.update", ISSUER)
        cap(10)
        body = {
            "idempotency_key": "approval-key-0004",
            "lines": [{"product": "COF"}],
            "discount_percent": "50",
            "payments": [{"method": "cash"}],
        }
        charged = through_approval(cashier, "/sale/sales/complete_over_limit", body)
        assert charged.status_code == 201, charged.content
        ran = while_running(platform_rule, "sale.sale.complete_over_limit")
        # The drawer and the catalog are reads; the ticket, a command of Invoicing the cashier may already issue.
        assert {"cash_register.session.current", "inventory.unit.list", "invoice.invoice.create_from_sale"} <= {
            name for name, _carried in ran
        }
        assert [name for name, carried in ran if carried] == []

    def test_only_the_approved_command_carries_never_another_of_the_till(self, haircut_with_shampoo):
        """The assistant marks its turn's request with the approval: another command of the till with the very same
        permission (a void, under the approval of voiding an item) takes nothing of other apps with it."""
        sale, line = haircut_with_shampoo
        ctx = the_cashiers_context(approved="sale.order.void_line")
        with pytest.raises(PermissionDenied):
            run("sale.sale.void", {"sale_id": str(sale.id), "reason": "wrong customer"}, ctx)
        assert Sale.objects.get(pk=sale.id).status == "completed"
        assert Redemption.objects.get(pk=SaleLine.objects.get(pk=line.id).voucher_session_id).status != "returned"

    def test_without_an_approval_the_callers_own_permissions_decide(self, haircut_with_shampoo):
        sale, _line = haircut_with_shampoo
        with pytest.raises(PermissionDenied):
            run("sale.sale.void", {"sale_id": str(sale.id), "reason": "wrong customer"}, the_cashiers_context())
        assert Sale.objects.get(pk=sale.id).status == "completed"
