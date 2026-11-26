"""Fixtures of the sale tests: contexts per role and scope, users with a role on a host, and the real
apps sale works with (tax's factory catalogue, inventory's products, customer's cards, services' catalog and
vouchers).

Every test that uses the database sells as production does: inside the business ``A``'s own database
(``in_business_a``), never on control's. A test of two businesses also asks for ``hub_b`` and enters it with
``use_hub``.

The products, the customers, the services and the vouchers are created through their own apps' operations, never
by hand: the integration with ``tax``, ``inventory``, ``customer`` and ``service`` is tested as it runs (no mocks).
"""

import datetime as dt
import json
from decimal import Decimal

import pytest
from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connections
from django.test import Client
from django.utils import timezone, translation
from live.context import OperationContext, Scope, system_context
from live.meta import CheckoutStep, all_live_app_configs, permissions_for_role
from live.models import OutboxEvent
from live.operations import atomic, get, registry
from psycopg.conninfo import make_conninfo

from apps.sale.models.sales import Sale
from base import activation, assistant
from base.models import Membership
from base.services.sessions import ensure_hub_user
from base.tenancy.tests.business import HOST, HUB_DB, A, B, factory_data, factory_data_b, in_business_a
from base.tenancy.tests.concurrency import hub_staff, plan_with_room
from base.tests.test_services_assistant import answered, asked, call


def ctx_for(
    role: str = "hub_admin",
    scope: Scope = A,
    actor: str = "tester",
    language: str = "en",
) -> OperationContext:
    """The context a user with ``role`` on ``scope`` gets (permissions from the apps' AppConfig).

    Owner and admin get every declared permission (base.permissions); the others what each app's
    ``role_permissions`` gives them.
    """
    configs = all_live_app_configs()
    if role in ("hub_owner", "hub_admin"):
        permissions = frozenset(p for config in configs for p in config.permissions)
    else:
        permissions = permissions_for_role(configs, role)
    return OperationContext(
        scope=scope, actor=actor, permissions=permissions, language=language
    )


def run(name: str, data: dict | None = None, ctx: OperationContext | None = None):
    """Runs the operation ``name`` with ``data`` as its input (validated as a route would)."""
    op = get(name)
    return op(ctx or ctx_for(), op.input.model_validate(data or {}))


def charged_by_the_assistant(order):
    """The assistant's charge of the open check ``order`` in cash, said in Spanish, once its card was confirmed: what
    the model hears back from ``sale.sale.complete``, which is ``ok``."""
    outcome = assistant.tools.run(
        ctx_for(language="es"),
        get("sale.sale.complete"),
        json.dumps({"order_id": str(order.id), "idempotency_key": "assistant-0001", "payments": [{"method": "cash"}]}),
    )
    assert outcome.outcome == "ok", outcome.content
    return outcome


def answered_yes_to_the_assistant(name: str, arguments: dict, ctx: OperationContext) -> dict:
    """The turn after ``ctx``'s person said yes to what the assistant asked for: the call ``name`` with ``arguments``."""

    def turn_of(*calls, decision=None):
        data = {"messages": [{"role": "user", "content": "imprímelo"}, asked(*calls)], "pending": list(calls)}
        return run("base.assistant.turn", {**data, "decision": decision}, ctx).model_dump(mode="json")

    return answered(call(name, arguments), decision={"call_id": "c1", "accepted": True}, turn_of=turn_of)


def confirmed_by_the_assistant(name: str, arguments: dict, ctx: OperationContext) -> dict:
    """The receipt's row of the write ``name`` the assistant asked for with ``arguments``, once ``ctx``'s person said
    yes to its card: its outcome, its code and why it was not done, in the person's language."""
    [row] = answered_yes_to_the_assistant(name, arguments, ctx)["executed"]
    return row


#: Bogotá at 23:30 of 2 November 2026, already the 3rd in Madrid, the deployment's clock (hub#771).
ELSEWHERE = "America/Bogota"
NIGHT_THERE = dt.datetime(2026, 11, 3, 4, 30, tzinfo=dt.UTC)


@pytest.fixture
def night_elsewhere(monkeypatch, in_business_a):
    """The business ``A`` in another zone than the deployment's, at night: it is 2 November 2026 there and the 3rd on
    the deployment's clock (hub#771). The root conftest's opens a business without a database of its own."""
    monkeypatch.setattr(timezone, "now", lambda: NIGHT_THERE)
    monkeypatch.setattr(in_business_a, "timezone", ELSEWHERE)


@pytest.fixture(autouse=True)
def without_cash_register(monkeypatch):
    """Sale's own tests sell as a business without Cash register: the till asks an operation nobody
    declares, as when the app is not installed (``UnknownOperation``). Its lock on cash (SALE-F08) is
    tested apart, with Cash register in the business (``test_integration_cash_register.py`` overrides
    this fixture)."""
    monkeypatch.setattr(
        "apps.sale.services.charge_validation.DRAWER_CHECK", "cash_register.session.not_installed"
    )


#: The step the reference app declares at the charge in ``a_step_at_the_charge``, as ``sale.checkout.steps`` gives it.
DECLARED_STEP = {"key": "demo.tip", "app": "demo", "component": "TipStep"}


@pytest.fixture(autouse=True)
def only_the_reference_app_adds_a_step(monkeypatch):
    """Sales' tests stand for an app that adds a step to the charge with the reference app (``a_step_at_the_charge``):
    the steps the real apps declare (Tips, on in the test businesses) are taken away, so Sales is tested on its own."""
    for config in all_live_app_configs():
        if config.label != "demo" and config.checkout:
            monkeypatch.setattr(config, "checkout", [])


@pytest.fixture
def a_step_at_the_charge(monkeypatch):
    """An app on adds a step to the charge, as Tips does with its tip, so what it adds to a tender is taken (SALE-F39):
    the reference app declares one, seen by everyone who charges. Without it no app on declares one, and the charge
    refuses any added amount."""
    monkeypatch.setattr(django_apps.get_app_config("demo"), "checkout", [CheckoutStep(key="tip", component="TipStep")])


@pytest.fixture(autouse=True)
def english():
    """Each test starts in English: a request of an earlier test may have left another language."""
    with translation.override("en"):
        yield


@pytest.fixture
def today():
    """The business day the test runs on, taken when it runs as the operations take it: a date taken at import
    is the day of the collection, and a run that crosses New Year's Eve would expect the numbers of the year
    before (``tests/test_guardrails.py``, ``clock_at_import``)."""
    return timezone.localdate()


@pytest.fixture
def make_user(db):
    def make(
        username: str = "ana",
        *,
        host: str | None = A.key,
        role: str = Membership.Role.ADMIN,
    ):
        user = get_user_model().objects.create_user(username=username, password="pw")
        if host is not None:
            Membership.objects.create(user=user, host=host, role=role)
        # Who they are in the business's database, as their entry makes it: what a record hangs from.
        user.person = ensure_hub_user(user)
        return user

    return make


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


@pytest.fixture
def product(db):
    """``product(name, sku, price, tax_category_key, **more)``: an inventory product, made by inventory."""

    def make(
        name: str = "Coffee",
        sku: str = "COF",
        price: int = 150,
        tax_category_key: str = "restaurant.drink",
        **more,
    ):
        data = {
            "name": name,
            "sku": sku,
            "price": price,
            "tax_category_key": tax_category_key,
            **more,
        }
        return run("inventory.product.create", data, system_context(A))

    return make


@pytest.fixture
def customer(db):
    """``customer(name, **more)``: a customer card, made by customer."""

    def make(name: str = "Ana López", **more):
        return run(
            "customer.customer.create", {"name": name, **more}, system_context(A)
        )

    return make


@pytest.fixture
def db_dsn(django_db_setup):
    """DSN of control's test database, where the live notices go after the COMMIT, for raw psycopg sessions."""
    params = connections["default"].settings_dict
    return make_conninfo(
        dbname=params["NAME"],
        user=params["USER"],
        password=params["PASSWORD"],
        host=params["HOST"],
        port=params["PORT"],
    )


Q = Decimal


# ── Sale and Services together ──────────────────────────────────────────────────────────────────────
# Services' catalog, vouchers and sessions are made by Services, and Sales reserves, releases, delivers and gives
# back the sessions by calling Services' operations inside its own transaction. «Services off» is the app's
# operations missing from the registry, as when it is not installed (the same path as ``app_inactive``).


def svc(name: str, data: dict):
    """Services' own operation, run as the platform: how the business's catalog and vouchers exist."""
    op = get(name)
    return op(system_context(A), op.input.model_validate(data))


@pytest.fixture
def haircut(db):
    return svc(
        "service.service.create",
        {"name": "Haircut", "price": 2500, "tax_category_key": "service.generic"},
    )


@pytest.fixture
def colour(db):
    return svc(
        "service.service.create",
        {
            "name": "Colour",
            "pricing_type": "from",
            "price": 6500,
            "min_price": 4000,
            "max_price": 9000,
            "tax_category_key": "service.generic",
        },
    )


@pytest.fixture
def lucia(customer):
    return customer("Lucía Pérez")


def voucher(owner, service, *, name="Bono 5 cortes", uses=5, validity=None):
    package = svc(
        "service.package.create",
        {
            "name": name,
            "max_uses": uses,
            "validity_days": validity,
            "items": [{"service_id": str(service.id)}],
        },
    )
    return svc(
        "service.grant.create",
        {"package_id": str(package.id), "customer_id": str(owner.id), "amount": 10000},
    )


def check(*services, ctx=None):
    """An open check with one line per service (fixed price)."""
    return run(
        "sale.order.open",
        {"service_lines": [{"service_id": str(service.id)} for service in services]},
        ctx,
    )


def pay_with(order, line_id, grant, ctx=None):
    return run(
        "sale.order.apply_voucher",
        {"order_id": str(order.id), "line_id": str(line_id), "grant_id": str(grant.id)},
        ctx,
    )


def charge(order, key="svc-charge-0001", ctx=None, **more):
    return run(
        "sale.sale.complete",
        {"idempotency_key": key, "order_id": str(order.id), **more},
        ctx,
    )


def last_event(name: str) -> dict:
    return (
        OutboxEvent.objects.filter(name=name)
        .order_by("-created_at", "-id")
        .first()
        .payload
    )


def charged_with_voucher(haircut, lucia, product=None, key="svc-charge-0001", ctx=None):
    grant = voucher(lucia, haircut)
    lines = {"service_lines": [{"service_id": str(haircut.id)}]}
    if product is not None:
        lines["lines"] = [{"product": "SHA"}]
    order = run("sale.order.open", lines, ctx)
    cut = next(line for line in order.lines if line.service_id)
    order = pay_with(order, cut.id, grant, ctx)
    payments = [{"method": "card"}] if product is not None else []
    sale = charge(order, key=key, ctx=ctx, customer_id=str(lucia.id), payments=payments)
    return grant, sale, next(line for line in sale.lines if line.paid_by_voucher)


def refund(sale, *, lines=(), allocations=(), key=None, ctx=None):
    return run(
        "sale.sale.refund",
        {
            "sale_id": str(sale.id),
            "reason": "did not come",
            "allocations": list(allocations),
            "lines": [{"line_id": str(line.id)} for line in lines],
            **({"idempotency_key": key} if key else {}),
        },
        ctx,
    )


@pytest.fixture
def without_kitchen(monkeypatch):
    """A business without Kitchen, as a shop or a salon sells: a charge sends nothing to it first."""
    monkeypatch.setattr(activation, "off_apps", lambda scope: frozenset({"kitchen"}))


@pytest.fixture
def services_off(monkeypatch):
    def turn_off():
        for name in [name for name in registry if name.startswith("service.")]:
            monkeypatch.delitem(registry, name)

    return turn_off


def charged_open(key, *lines, staff=None, ctx=None):
    """A sale charged by card with one open-price line per ``(name, price, professional or None)``: how a voucher is
    charged at the till today (SERVICE-F14)."""
    return run(
        "sale.sale.complete",
        {
            "idempotency_key": key,
            "open_lines": [
                {
                    "name": name,
                    "unit_price": price,
                    "tax_category_key": "service.generic",
                    **({"staff_id": str(member)} if member else {}),
                }
                for name, price, member in lines
            ],
            "payments": [{"method": "card"}],
            **({"staff_id": str(staff)} if staff else {}),
        },
        ctx,
    )


def grant_for(owner, service, *, name="Bono de 100", uses=3, amount=10000, **more):
    package = svc(
        "service.package.create",
        {"name": name, "max_uses": uses, "items": [{"service_id": str(service.id)}]},
    )
    return svc(
        "service.grant.create",
        {"package_id": str(package.id), "customer_id": str(owner.id), "amount": amount, **more},
    )


def voucher_of_100(owner, service, *, uses=3, name="Bono de 100", seller=None, key="sold-0001"):
    """A voucher of ``uses`` sessions, charged at the till for 100.00 (by ``seller``) and granted saying that sale."""
    sold = charged_open(key, (name, 10000, seller))
    return grant_for(owner, service, name=name, uses=uses, sale_id=str(sold.id))


def spend_session(grant, service, owner, key, *, staff=None, sale_staff=None, ctx=None):
    """One session of ``grant`` pays a check of one line of ``service`` that ``staff`` does, charged."""
    order = run(
        "sale.order.open",
        {
            "service_lines": [
                {"service_id": str(service.id), **({"staff_id": str(staff)} if staff else {})}
            ]
        },
        ctx,
    )
    order = pay_with(order, order.lines[0].id, grant, ctx)
    return charge(
        order,
        key=key,
        customer_id=str(owner.id),
        ctx=ctx,
        **({"staff_id": str(sale_staff)} if sale_staff else {}),
    )


def by_staff(**params):
    return {row.staff_id: row for row in run("sale.sale.by_staff", params).rows}


def professional(first_name: str, ctx=None):
    """A member of Staff's team: Services only takes a professional who is on it."""
    return run("staff.member.create", {"first_name": first_name, "last_name": "López"}, ctx).id


def redeem(grant, *, member=None, service=None, ctx=None):
    """One session of ``grant`` spent outside the till (the assistant, the API), saying who did it."""
    return run(
        "service.grant.redeem",
        {
            "id": str(grant.id),
            **({"member_id": str(member)} if member else {}),
            **({"service_id": str(service.id)} if service else {}),
        },
        ctx,
    )


def refused(make):
    with pytest.raises(IntegrityError), atomic():
        make()


def a_sale(**more) -> Sale:
    values = {
        "number": "20261014-0001",
        "business_day": dt.date(2026, 10, 14),
        "sequence": 1,
        "idempotency_key": "key-0001",
        "total": 100,
        "subtotal": 91,
        "tax_total": 9,
    }
    return Sale.objects.create(**(values | more))
