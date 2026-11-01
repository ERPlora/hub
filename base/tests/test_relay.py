"""The outbox relay, phase 1 (PLAN-HUB «Eventos entre módulos», round 2026-10-20; ``base.relay``).

Every tick of the worker hands each new outbox event to the reactions of the apps that listen to it (their
``events.py``), each in its own transaction, exactly once, as the system and in the scope of the hub that
recorded it. These tests drive the worker's real loop (``base.worker.run``) on the real database and the real
apps, without mocks: a sale charged at the till lowers the stock once and keeps one invoice and one VeriFactu
record (the till already issued them; the reaction is the backup), a round fired reaches the kitchen once, a
second tick repeats nothing, the events from before the relay existed (the backlog) are never applied, an
event of hub B runs in B and is heard in B only, and an app that is off receives nothing (nor the history once
it is turned on).
"""

import datetime as dt
import json
import logging
import threading
from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace

import psycopg
import pytest
from django.apps import apps as global_apps
from django.db import connection, connections, transaction
from django.db.backends.base.base import BaseDatabaseWrapper
from django.utils import timezone, translation
from live.context import OperationContext, Scope, system_context
from live.errors import Conflict, NotFound
from live.meta import all_live_app_configs
from live.models import OutboxEvent
from live.operations import get
from live.outbox import channel_for
from psycopg.conninfo import make_conninfo

from apps.customer.models import Customer
from apps.inventory.models import Product, StockMovement
from apps.invoice.models import Invoice
from apps.kitchen.models import Ticket
from apps.printing.models import PrintJob
from apps.verifactu.models import Record
from base import catalog, relay, services, worker
from base.catalog import RegisterResult
from base.models import EventDelivery

A = Scope("host", "a")
B = Scope("host", "b")
ISSUER = {
    "legal_name": "Peluquería Ana SL",
    "tax_id": "B12345674",
    "address": "Calle Mayor 1",
    "postal_code": "28001",
    "city": "Madrid",
    "province": "Madrid",
}
REGISTERED = RegisterResult(written=0, retired=0, docs_changed=0, skipped=True)


def ctx_for(scope: Scope = A, actor: str = "tester") -> OperationContext:
    """An owner of ``scope``: every permission the apps declare."""
    permissions = frozenset(p for config in all_live_app_configs() for p in config.permissions)
    return OperationContext(scope=scope, actor=actor, permissions=permissions, language="en")


def run(name: str, data: dict | None = None, ctx: OperationContext | None = None):
    op = get(name)
    return op(ctx or ctx_for(), op.input.model_validate(data or {}))


@pytest.fixture(autouse=True)
def english():
    with translation.override("en"):
        yield


@pytest.fixture
def worker_loop(monkeypatch):
    """The worker's real loop, without the SaaS (``register_apps``) and, inside a test's transaction, without
    releasing the connections (that would close the test's own); ``tick(n)`` runs ``n`` ticks at ``now``."""
    monkeypatch.setattr(catalog, "register_apps", lambda: REGISTERED)
    monkeypatch.setattr(BaseDatabaseWrapper, "close_if_unusable_or_obsolete", lambda self: None)
    now = timezone.now()

    def tick(times: int = 1, *, at: dt.datetime | None = None) -> None:
        stop, waits = threading.Event(), []

        def wait(seconds: float) -> bool:
            waits.append(seconds)
            if len(waits) == times:
                stop.set()
            return stop.is_set()

        moment = at or now
        assert worker.run(stop, tick_seconds=0, wait=wait, clock=lambda: moment) == 0

    tick.now = now
    return tick


@pytest.fixture
def till(db):
    """An issuer, a shampoo with 10 units on the shelf and Ana's card, all made by their own apps."""
    run("invoice.issuer.update", ISSUER)
    run(
        "inventory.product.create",
        {
            "name": "Shampoo",
            "sku": "SHA",
            "price": 1210,
            "tax_category_key": "product.generic",
            "initial_stock": "10",
        },
        system_context(A),
    )
    return run("customer.customer.create", {"name": "Ana López"}, system_context(A))


def charge(key: str, quantity: str = "2", *, customer=None, scope: Scope = A):
    data = {
        "idempotency_key": key,
        "lines": [{"product": "SHA", "quantity": quantity}],
        "payments": [{"method": "card"}],
    }
    if customer is not None:
        data["customer_id"] = str(customer.id)
    return run("sale.sale.complete", data, ctx_for(scope))


def stock() -> Decimal:
    return Product.objects.get(sku="SHA", is_deleted=False).stock


def card(customer) -> tuple[int, int]:
    found = Customer.objects.get(pk=customer.id)
    return found.total_purchases, found.total_spent


def documents() -> tuple[int, int]:
    """(invoices, VeriFactu records): every document issued has exactly one record."""
    return Invoice.objects.count(), Record.objects.count()


def newest(name: str) -> OutboxEvent:
    return OutboxEvent.objects.filter(name=name).order_by("-created_at", "-id").first()


def deliveries(name: str) -> dict[str, tuple[str, int]]:
    """``{app: (status, attempts)}`` of the deliveries of the newest ``name`` event."""
    rows = EventDelivery.objects.filter(event=newest(name))
    return {row.app_label: (row.status, row.attempts) for row in rows}


# ── The tick: money, fiscal and stock, exactly once (trap 2) ──────────────────────────────────


def test_a_paid_sale_lowers_the_stock_once_and_keeps_one_invoice_and_one_record(worker_loop, till):
    sale = charge("relay-0001", customer=till)
    # The till issued the ticket and its record in the charge; the stock and the card wait for the relay.
    assert (stock(), documents(), card(till)) == (Decimal("10"), (1, 1), (0, 0))

    worker_loop()

    assert stock() == Decimal("8")
    assert card(till) == (1, 2420)
    assert documents() == (1, 1)
    assert Invoice.objects.get().source_sale_id == sale.id
    assert StockMovement.objects.filter(movement_type="sale").count() == 1
    # Each listener got the charge once, and said so in the same transaction.
    assert deliveries("sale.sale.completed") == {
        "customer": ("delivered", 1),
        "flow": ("delivered", 1),
        "inventory": ("delivered", 1),
        "invoice": ("delivered", 1),
    }
    # The ticket the till issued reached Sales (its number, already kept) and VeriFactu (its record, the same).
    assert deliveries("invoice.invoice.issued") == {
        "flow": ("delivered", 1),
        "sale": ("delivered", 1),
        "verifactu": ("delivered", 1),
    }

    worker_loop()

    assert (stock(), card(till), documents()) == (Decimal("8"), (1, 2420), (1, 1))
    assert deliveries("sale.sale.completed")["inventory"] == ("delivered", 1)


def test_a_voided_sale_gives_the_stock_back_once_with_one_rectification(worker_loop, till):
    sale = charge("relay-0002", customer=till)
    worker_loop()
    assert (stock(), card(till)) == (Decimal("8"), (1, 2420))
    run("sale.sale.void", {"sale_id": str(sale.id), "reason": "Wrong ticket"})

    worker_loop()

    assert stock() == Decimal("10")
    assert card(till) == (0, 0)
    # The ticket and its rectification, each with its record: the reaction answered the void's own.
    assert documents() == (2, 2)
    assert Invoice.objects.filter(rectifies__source_sale_id=sale.id).count() == 1

    worker_loop()

    assert (stock(), card(till), documents()) == (Decimal("10"), (0, 0), (2, 2))


def test_a_refund_puts_its_units_back_once_with_one_rectification(worker_loop, till):
    sale = charge("relay-0003", customer=till)
    worker_loop()
    run(
        "sale.sale.refund",
        {
            "sale_id": str(sale.id),
            "reason": "One bottle back",
            "allocations": [{"payment_id": str(sale.payments[0].id), "amount": 1210}],
            "lines": [{"line_id": str(sale.lines[0].id), "quantity": "1"}],
        },
    )

    worker_loop()

    assert stock() == Decimal("9")
    assert card(till) == (1, 1210)
    assert documents() == (2, 2)

    worker_loop()

    assert (stock(), card(till), documents()) == (Decimal("9"), (1, 1210), (2, 2))


def test_a_round_fired_at_the_till_reaches_the_kitchen_once(worker_loop, db):
    burger = run(
        "inventory.product.create",
        {"name": "Burger", "sku": "BURGER", "price": 1200, "tax_category_key": "restaurant.food"},
        system_context(A),
    )
    order = run("sale.order.open", {"label": "Table 4"}, system_context(A))
    run(
        "sale.order.add_line",
        {"order_id": str(order.id), "product_id": str(burger.id), "quantity": "1"},
        ctx_for(actor="waiter"),
    )
    run("sale.order.fire", {"order_id": str(order.id), "priority": "urgent"}, ctx_for(actor="waiter"))
    assert (Ticket.objects.count(), PrintJob.objects.count()) == (0, 0)

    worker_loop()

    ticket = Ticket.objects.get()
    # What only the send knows reaches the ticket, and its paper is queued once.
    assert (ticket.priority, ticket.waiter) == ("rush", "waiter")
    assert PrintJob.objects.filter(document_type="kitchen_order").count() == 1

    worker_loop()

    assert (Ticket.objects.count(), PrintJob.objects.count()) == (1, 1)


# ── The backlog: what was recorded before the relay existed is never applied (trap 1) ─────────


class _SchemaEditor:
    """What a ``RunPython`` function reads from the schema editor: the connection."""

    connection = connection


def _relay_migration():
    return import_module("base.migrations.0006_event_delivery")


def test_the_events_recorded_before_the_relay_are_never_applied(worker_loop, till):
    charge("relay-0004", customer=till)
    old = OutboxEvent.objects.get(name="sale.sale.completed")

    # The migration that brings the relay marks the backlog as handed over, without delivering it.
    _relay_migration().hold_back_the_backlog(global_apps, _SchemaEditor())
    worker_loop()

    assert (stock(), card(till)) == (Decimal("10"), (0, 0))
    assert not EventDelivery.objects.filter(event=old).exists()
    # What comes after it is delivered (the positive control).
    charge("relay-0005", quantity="3", customer=till)
    worker_loop()
    assert (stock(), card(till)) == (Decimal("7"), (1, 3630))


def test_reverting_the_migration_gives_back_only_the_events_it_held_back(worker_loop, till):
    charge("relay-0006")
    _relay_migration().hold_back_the_backlog(global_apps, _SchemaEditor())
    held = OutboxEvent.objects.get(name="sale.sale.completed")
    charge("relay-0007")
    worker_loop()
    relayed = OutboxEvent.objects.filter(name="sale.sale.completed").exclude(pk=held.pk).get()

    _relay_migration().release_the_backlog(global_apps, _SchemaEditor())

    held.refresh_from_db()
    relayed.refresh_from_db()
    assert held.delivered_at is None
    assert relayed.delivered_at is not None


# ── Only the apps that are on (trap 4) ────────────────────────────────────────────────────────


@pytest.mark.django_db  # which apps are on is the business's: its rows (base.activation)
def test_listeners_of_an_event():
    def event(name: str) -> OutboxEvent:
        return OutboxEvent(scope_kind="host", scope_key="a", name=name)

    # The apps whose REACTIONS name it, and Flows («*»), which hears every event but its own app's.
    assert relay.listeners(event("sale.sale.completed")) == ["customer", "flow", "inventory", "invoice"]
    assert relay.listeners(event("sale.order.fired")) == ["flow", "kitchen"]
    assert relay.listeners(event("flow.run.finished")) == []
    assert relay.listeners(event("demo.item.created")) == ["flow"]


@pytest.mark.django_db
def test_an_event_of_the_platform_is_heard_by_no_app_of_a_hub():
    """Verification of hub#471 in pre: ``base.demo.created`` (control's outbox, the registry's scope) reached Flows
    («*»), whose reaction ran on control and failed 8 times with ``HubContextMissing``. An event of no hub has no hub
    to enter: the apps of a hub never hear it."""
    for name in ("base.demo.created", "base.demo.code_created", "base.hub.registered"):
        assert relay.listeners(OutboxEvent(scope_kind="platform", scope_key="registry", name=name)) == []


def test_the_worker_takes_a_platform_event_without_handing_it_to_any_app(worker_loop, db):
    from base.registry import REGISTRY_SCOPE
    from base.tenancy.context import use_control

    with use_control():
        event = OutboxEvent.objects.create(
            scope_kind=REGISTRY_SCOPE.kind,
            scope_key=REGISTRY_SCOPE.key,
            name="base.demo.created",
            payload={"slug": "demo-x1234567"},
            actor="platform",
        )

    worker_loop()

    event.refresh_from_db()
    assert event.delivered_at is not None
    assert not EventDelivery.objects.filter(event=event).exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("no_test_fallback")
def test_on_control_the_relay_takes_the_platform_s_events_and_leaves_what_phase_1_left_of_a_business_alone():
    """S5: control's outbox keeps the events a business of phase 1 recorded there before its cut; reading the apps on
    of that business would need its database, so on control the relay never takes one, nor runs its deliveries
    (the cut copies a business's own into its database: ``base.tenancy.cut``)."""
    from base.registry import REGISTRY_SCOPE
    from base.tenancy.context import use_control

    with use_control():
        platform = OutboxEvent.objects.create(
            scope_kind=REGISTRY_SCOPE.kind, scope_key=REGISTRY_SCOPE.key, name="base.hub.registered", actor="platform"
        )
        left = OutboxEvent.objects.create(scope_kind="host", scope_key="elpa", name="sale.sale.paid", actor="ana")
        pending = EventDelivery.objects.create(event=left, app_label="inventory", next_attempt_at=timezone.now())

        done = relay.run(timezone.now(), of_hubs=False)

        platform.refresh_from_db()
        left.refresh_from_db()
        pending.refresh_from_db()
    assert done.taken == 1 and done.failed == 0
    assert platform.delivered_at is not None
    assert left.delivered_at is None
    assert (pending.status, pending.attempts) == (EventDelivery.Status.PENDING, 0)


class TestTheMigrationThatClosesControlDeliveries:
    """``base/migrations/0021_close_control_deliveries``: the deliveries of an event of no hub written before the relay
    stopped handing them to any app (hub#471) would fail on every attempt until given up, each with its traceback;
    they are closed ``dead`` at once, with why. A hub's own deliveries, and the ones already closed, stay as
    they are."""

    migration = import_module("base.migrations.0021_close_control_deliveries")

    @staticmethod
    def delivery(scope_kind, scope_key, *, status=EventDelivery.Status.PENDING, last_error=""):
        event = OutboxEvent.objects.create(
            scope_kind=scope_kind, scope_key=scope_key, name="base.demo.created", payload={}, actor="platform"
        )
        return EventDelivery.objects.create(
            event=event, app_label="flow", status=status, next_attempt_at=timezone.now(), last_error=last_error
        )

    @pytest.mark.django_db
    def test_a_pending_delivery_of_an_event_of_no_hub_is_closed_dead_with_why(self):
        from base.tenancy.context import use_control

        with use_control():
            control = self.delivery("platform", "registry")
            business = self.delivery("host", "a")
            done = self.delivery("platform", "registry", status=EventDelivery.Status.DEAD, last_error="Boom")

            self.migration.close_control_deliveries(
                global_apps, SimpleNamespace(connection=SimpleNamespace(alias=connection.alias))
            )

            for row in (control, business, done):
                row.refresh_from_db()
        assert (control.status, control.last_error.split(":")[0]) == (EventDelivery.Status.DEAD, "control_scope")
        assert (business.status, business.last_error) == (EventDelivery.Status.PENDING, "")
        assert (done.status, done.last_error) == (EventDelivery.Status.DEAD, "Boom")

    def test_reverting_it_leaves_them_closed(self):
        (close,) = self.migration.Migration.operations
        assert close.reversible
        assert close.reverse_code is close.noop


@pytest.mark.django_db
def test_a_business_that_never_turned_an_app_off_has_every_installed_app_on():
    # base.session.me lists every module as «on»: no right is missing and nothing was turned off (base.activation).
    assert relay.active_apps(A) == frozenset(config.label for config in all_live_app_configs())


def test_an_app_that_is_off_receives_nothing_nor_the_history_once_it_is_on(worker_loop, till, monkeypatch):
    every = relay.active_apps(A)
    monkeypatch.setattr(relay, "active_apps", lambda scope: every - {"inventory"})
    charge("relay-0008", customer=till)

    worker_loop()

    assert stock() == Decimal("10")
    assert card(till) == (1, 2420)
    assert "inventory" not in deliveries("sale.sale.completed")

    # Turned on again: the sale of before stays as it was; the next one lowers the stock.
    monkeypatch.setattr(relay, "active_apps", lambda scope: every)
    worker_loop()
    assert stock() == Decimal("10")
    charge("relay-0009", quantity="1")
    worker_loop()
    assert stock() == Decimal("9")


# ── Depth: a reaction that records events does not loop (trap 5) ──────────────────────────────


def test_what_a_reaction_records_is_handed_over_in_its_own_transaction_one_level_deeper(worker_loop, till):
    charge("relay-0010")

    worker_loop()

    # Inventory's reaction recorded the stock change; Flows heard it, one level deeper, in the same tick.
    changed = newest("inventory.stock.changed")
    assert changed.payload["movement_type"] == "sale"
    assert changed.delivered_at is not None
    row = EventDelivery.objects.get(event=changed, app_label="flow")
    assert (row.depth, row.status) == (1, "delivered")


class _Undone(Exception):
    pass


def test_an_event_a_reaction_records_and_then_undoes_is_not_handed_over(worker_loop, till, monkeypatch):
    # A reaction may try something in a savepoint and give it up (Kitchen's paper when Printing refuses it): the
    # event recorded there is gone, and a delivery pointing at it would fail the whole COMMIT on every tick.
    real = relay.deliver

    def deliver(app_label, event):
        outcome = real(app_label, event)
        if app_label == "inventory":
            try:
                with transaction.atomic():
                    run("customer.customer.create", {"name": "Never kept"}, system_context(A))
                    raise _Undone
            except _Undone:
                pass
        return outcome

    monkeypatch.setattr(relay, "deliver", deliver)
    charge("relay-0013")

    worker_loop()

    assert stock() == Decimal("8")
    # Only Ana's card, from the till: the one the reaction undid left no event.
    assert OutboxEvent.objects.filter(name="customer.customer.created").count() == 1
    assert not EventDelivery.objects.exclude(event_id__in=OutboxEvent.objects.values("id")).exists()
    assert deliveries("sale.sale.completed")["inventory"] == ("delivered", 1)


def test_past_the_deepest_level_an_event_is_not_delivered_and_says_why(worker_loop, till, monkeypatch, caplog):
    monkeypatch.setattr(relay, "MAX_EVENT_DEPTH", 0)

    with caplog.at_level(logging.ERROR, logger="base.services"):
        charge("relay-0011")
        worker_loop()

    assert stock() == Decimal("8")
    row = EventDelivery.objects.get(event=newest("inventory.stock.changed"), app_label="flow")
    assert (row.depth, row.status, row.attempts) == (1, "dead", 0)
    assert "depth" in row.last_error
    assert any("depth" in record.getMessage() for record in caplog.records)


# ── A failing reaction: retried a few times, never in a loop, never blocking the others (trap 5)


def test_a_reaction_that_fails_is_retried_with_a_growing_wait_then_given_up_and_the_rest_flows(
    worker_loop, till, caplog
):
    OutboxEvent.objects.create(scope_kind="host", scope_key="a", name="sale.sale.completed", payload={"bogus": 1})
    charge("relay-0012")
    now = worker_loop.now

    with caplog.at_level(logging.ERROR, logger="base.services"):
        worker_loop()

    # The good sale went through; the broken one waits 2 s for its second attempt.
    assert stock() == Decimal("8")
    broken = EventDelivery.objects.get(event__payload={"bogus": 1}, app_label="inventory")
    assert (broken.status, broken.attempts) == ("pending", 1)
    assert broken.next_attempt_at == now + dt.timedelta(seconds=2)
    assert "ValidationError" in broken.last_error
    assert any(str(broken.event_id) in record.getMessage() for record in caplog.records)

    # Not before its time; then 4 s, 8 s… until the eighth attempt, which gives up.
    worker_loop(at=now + dt.timedelta(seconds=1))
    broken.refresh_from_db()
    assert broken.attempts == 1
    moment = now
    for attempt in range(2, relay.MAX_ATTEMPTS + 1):
        moment = broken.next_attempt_at
        worker_loop(at=moment)
        broken.refresh_from_db()
        assert broken.attempts == attempt
        if attempt < relay.MAX_ATTEMPTS:
            # The wait grows with the attempts of this delivery: 4 s after the second, 8 s after the third…
            assert broken.next_attempt_at == moment + relay.backoff(attempt)
    assert broken.status == "dead"
    worker_loop(at=moment + dt.timedelta(days=1))
    broken.refresh_from_db()
    assert (broken.status, broken.attempts) == ("dead", relay.MAX_ATTEMPTS)


def test_the_wait_doubles_and_stops_growing_at_an_hour():
    assert [relay.backoff(n).total_seconds() for n in (1, 2, 3, 11, 12, 20)] == [2, 4, 8, 2048, 3600, 3600]


# ── What the relay logs: a refusal of the business is a warning; the unexpected and the given up, errors ─────


@pytest.fixture
def one_delivery(db):
    """A ``sale.sale.completed`` taken for Invoicing, due now: ``(event, now)``."""
    now = timezone.now()
    event = OutboxEvent.objects.create(scope_kind="host", scope_key="a", name="sale.sale.completed", payload={})
    services.relay_take_events(now, listeners=lambda _: ["invoice"], limit=10, max_depth=relay.MAX_EVENT_DEPTH)
    return event, now


def deliver_once(error: Exception, at: dt.datetime) -> EventDelivery:
    """One delivery due at ``at`` whose reaction raises ``error``."""

    def deliver(app_label, event):
        raise error

    delivery, delivered = services.relay_deliver_next(
        at,
        deliver=deliver,
        listeners=lambda _: [],
        max_depth=relay.MAX_EVENT_DEPTH,
        max_attempts=relay.MAX_ATTEMPTS,
        backoff=relay.backoff,
    )
    assert not delivered
    return delivery


def relay_logs(caplog) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == "base.services"]


@pytest.mark.parametrize(
    ("refusal", "code"),
    [
        (Conflict("Set up the issuer first.", code="invoice.issuer_missing"), "invoice.issuer_missing"),
        (NotFound("No such sale."), "not_found"),
    ],
)
def test_a_reaction_the_business_refuses_is_a_warning_with_its_code_and_no_traceback(
    one_delivery, caplog, refusal, code
):
    event, now = one_delivery

    with caplog.at_level(logging.DEBUG, logger="base.services"):
        delivery = deliver_once(refusal, now)

    [logged] = relay_logs(caplog)
    assert logged.levelno == logging.WARNING
    assert not logged.exc_info, "a refusal of the business is logged without a traceback"
    message = logged.getMessage()
    for part in ("invoice", "sale.sale.completed", str(event.id), code, f"attempt 1 of {relay.MAX_ATTEMPTS}"):
        assert part in message
    # The retry is the same as for any failure.
    delivery.refresh_from_db()
    assert (delivery.status, delivery.attempts, delivery.next_attempt_at, delivery.last_error) == (
        "pending",
        1,
        now + dt.timedelta(seconds=2),
        f"{type(refusal).__name__}: {refusal}",
    )


def test_a_reaction_that_fails_unexpectedly_is_an_error_with_its_traceback(one_delivery, caplog):
    event, now = one_delivery

    with caplog.at_level(logging.DEBUG, logger="base.services"):
        delivery = deliver_once(RuntimeError("the printer driver crashed"), now)

    [logged] = relay_logs(caplog)
    assert logged.levelno == logging.ERROR
    assert logged.exc_info is not None and logged.exc_info[0] is RuntimeError
    assert str(event.id) in logged.getMessage()
    delivery.refresh_from_db()
    assert (delivery.status, delivery.attempts, delivery.next_attempt_at, delivery.last_error) == (
        "pending",
        1,
        now + dt.timedelta(seconds=2),
        "RuntimeError: the printer driver crashed",
    )


def test_a_refusal_given_up_at_the_last_attempt_is_an_error_with_its_code(one_delivery, caplog):
    event, now = one_delivery
    EventDelivery.objects.filter(event=event).update(attempts=relay.MAX_ATTEMPTS - 1)
    refusal = Conflict("Set up the issuer first.", code="invoice.issuer_missing")

    with caplog.at_level(logging.DEBUG, logger="base.services"):
        delivery = deliver_once(refusal, now)

    [logged] = relay_logs(caplog)
    assert logged.levelno == logging.ERROR
    assert logged.exc_info is not None and logged.exc_info[0] is Conflict
    message = logged.getMessage()
    for part in ("invoice", str(event.id), "invoice.issuer_missing", f"after {relay.MAX_ATTEMPTS} attempts"):
        assert part in message
    delivery.refresh_from_db()
    assert (delivery.status, delivery.attempts, delivery.last_error) == (
        "dead",
        relay.MAX_ATTEMPTS,
        "Conflict: Set up the issuer first.",
    )


# ── Two hubs and two workers (traps 3 and 5), on committed data ───────────────────────────────


@pytest.fixture
def committed_till(transactional_db):
    """``till`` on a flushed database: tax's factory catalogue and the payment methods are planted again, as
    their migrations do."""
    with connections["default"].schema_editor() as editor:
        for module in (
            "apps.tax.migrations.0002_factory_catalogue",
            "apps.tax.migrations.0005_retail_alcohol",
            "apps.sale.migrations.0002_factory_payment_methods",
        ):
            import_module(module).plant(global_apps, editor)
    run("invoice.issuer.update", ISSUER)
    run(
        "inventory.product.create",
        {
            "name": "Shampoo",
            "sku": "SHA",
            "price": 1210,
            "tax_category_key": "product.generic",
            "initial_stock": "10",
        },
        system_context(A),
    )


@pytest.fixture
def listen():
    params = connections["default"].settings_dict
    dsn = make_conninfo(
        dbname=params["NAME"],
        user=params["USER"],
        password=params["PASSWORD"],
        host=params["HOST"],
        port=params["PORT"],
    )
    sessions = []

    def open_session(scope: Scope):
        session = psycopg.connect(dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def heard(session, timeout: float = 0.5) -> set[str]:
    return {name for note in session.notifies(timeout=timeout) for name in json.loads(note.payload)["events"]}


def test_an_event_of_hub_b_runs_in_b_and_is_heard_in_b_only(committed_till, listen, monkeypatch):
    monkeypatch.setattr(catalog, "register_apps", lambda: REGISTERED)
    on_a, on_b = listen(A), listen(B)
    charge("relay-b-0001", scope=B)
    heard(on_b)  # the charge's own notice

    stop = threading.Event()
    assert worker.run(stop, tick_seconds=0, wait=lambda seconds: stop.set()) == 0

    assert stock() == Decimal("8")
    assert "inventory.stock.changed" in heard(on_b)
    assert heard(on_a) == set()
    # The positive control: a charge of A is heard in A.
    charge("relay-a-0001", scope=A)
    heard(on_a)
    stop.clear()
    worker.run(stop, tick_seconds=0, wait=lambda seconds: stop.set())
    assert "inventory.stock.changed" in heard(on_a)


def test_two_workers_never_deliver_the_same_event_to_the_same_app(committed_till, monkeypatch):
    # The deploy starts the new worker before stopping the old one: both relay the same outbox.
    seen: list[tuple[str, str]] = []
    waited: list[bool] = []
    real = relay.deliver

    def deliver(app_label, event):
        seen.append((app_label, str(event.id)))
        if app_label == "inventory" and not waited:
            # While this worker holds inventory's delivery, the other one relays: it skips it, never waits.
            other = threading.Thread(target=other_worker)
            other.start()
            other.join(timeout=10)
            waited.append(other.is_alive())
        return real(app_label, event)

    def other_worker():
        try:
            relay.run(timezone.now())
        finally:
            connection.close()

    monkeypatch.setattr(relay, "deliver", deliver)
    charge("relay-two-0001")

    relay.run(timezone.now())

    assert waited == [False]
    assert len(seen) == len(set(seen))
    assert stock() == Decimal("8")
    assert StockMovement.objects.filter(movement_type="sale").count() == 1
