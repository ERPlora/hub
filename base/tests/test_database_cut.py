"""A business's Hub while the database is cut for a moment (BASE-F111; PLAN-DB round 2026-11-04e, point 5).

The whole chain of the Hub, against the real Postgres, as production runs it (``no_test_fallback``): ``pg_terminate_backend``
is the server cutting a connection right before a statement of the request, ``default_transaction_read_only`` the old
writer refusing writes during a switchover. The piece itself, and what it never repeats, is tested in ``live``
(``tests/test_database_cut.py``); here, that the Hub is wired to it, on control and on a business's own database: control's
pool hands out no dead connection; a read waits and answers, also when the cut comes while the business's database is
being opened; a save of a command that touches nothing but its database (the reference app's) goes in once, in its own
business only; one that numbers is never repeated; a wait holds no place of the business's plan; past the limit a person
reads «come back in a moment» with 503 and ``Retry-After``, never a 500; and the SaaS's ``/internal`` calls get theirs at
once.
"""

import ast
import asyncio
import functools
import importlib
import inspect
import json
import textwrap
import time
import types
from types import SimpleNamespace

import live.database_cut as live_database_cut
import psycopg
import pytest
from django.contrib.auth import get_user_model
from django.db import DatabaseError, connections
from django.test import Client
from django.utils import translation
from live.database_cut import DatabaseCut
from live.models import OutboxEvent
from psycopg import sql

from apps.demo.models import Item
from apps.task.models import Task
from base import middleware
from base.models import Membership
from base.tenancy import context, identity, limits
from base.tenancy.tests import hubs
from base.tests.test_internal import signed

pytestmark = [
    pytest.mark.usefixtures("no_test_fallback"),
    pytest.mark.django_db(databases=hubs.HUB_DATABASES, transaction=True),
]

ITEMS = "/api/demo/items"
TASKS = "/api/task/tasks"
UNAVAILABLE = "database_unavailable"
UNKNOWN = "database_outcome_unknown"
HUB_UNAVAILABLE = "base.hub_unavailable"
ITEM_CREATED = "demo.item.created"
LIMIT_SECONDS = 1


def _admin() -> psycopg.Connection:
    """The connection that cuts the others, on ``postgres``: never read only itself, or it could not undo ``_read_only``."""
    params = connections["default"].settings_dict
    return psycopg.connect(
        dbname="postgres",
        user=params["USER"],
        password=params["PASSWORD"],
        host=params["HOST"],
        port=params["PORT"],
        autocommit=True,
    )


def _terminate(pid: int) -> None:
    with _admin() as admin:
        admin.execute("SELECT pg_terminate_backend(%s)", (pid,))
        deadline = time.monotonic() + 5
        while admin.execute("SELECT 1 FROM pg_stat_activity WHERE pid = %s", (pid,)).fetchone():
            assert time.monotonic() < deadline, "the backend outlived pg_terminate_backend"
            time.sleep(0.01)


def _read_only(database: str, on: bool) -> None:
    """New sessions of ``database`` are read only, as the old writer's are during a switchover."""
    statement = "ALTER DATABASE {} SET default_transaction_read_only = on" if on else "ALTER DATABASE {} RESET default_transaction_read_only"
    with _admin() as admin:
        admin.execute(sql.SQL(statement).format(sql.Identifier(database)))


def _old_writer(hub) -> None:
    """``hub``'s database answers as the old writer does during a switchover: every new session is read only. The
    connection this thread already holds (the suite's client keeps it across requests) is closed, so the request opens
    one of those."""
    _read_only(hub.db_name, True)
    connections[hubs.HUB_A_ALIAS if hub.id == hubs.HUB_A_ID else hubs.HUB_B_ALIAS].close()


class CutOn:
    """Cuts the connection right before the statements that name ``table``: the next ``times`` (``None``: all of them)."""

    def __init__(self, table: str, times: int | None = 1) -> None:
        self.table = table
        self.times = times
        self.done = 0

    def __call__(self, execute, query, params, many, context):
        if self.table in str(query) and (self.times is None or self.done < self.times):
            self.done += 1
            _terminate(context["connection"].connection.info.backend_pid)
        return execute(query, params, many, context)


class Refused:
    """The first statement that writes opens the new sessions of ``database`` again, and is itself refused: this session
    stays read only, as a connection to the old writer does. Keeps the statements Postgres refused."""

    def __init__(self, database: str) -> None:
        self.database = database
        self.statements: list[str] = []

    def __call__(self, execute, query, params, many, context):
        statement = str(query).lstrip().upper()
        if statement.startswith(("INSERT", "UPDATE", "DELETE")) or "FOR UPDATE" in statement or "FOR KEY SHARE" in statement:
            _read_only(self.database, False)
        try:
            return execute(query, params, many, context)
        except DatabaseError:
            self.statements.append(str(query))
            raise


@pytest.fixture(autouse=True)
def quick_limit(settings, hub_a, hub_b):
    """The project's own setting with a short limit; never one the project does not ask for."""
    if (cut := settings.LIVE.get("database_cut")) is not None:
        settings.LIVE = {**settings.LIVE, "database_cut": {**cut, "wait_seconds": LIMIT_SECONDS}}
    yield
    # Before the tables are emptied: no business's database left read only, no connection this test cut.
    for hub in (hub_a, hub_b):
        _read_only(hub.db_name, False)
    connections.close_all()
    connections["default"].close_pool()


@pytest.fixture
def waits(monkeypatch):
    """Each wait of a request for the database, with the places of each business's plan in use at that moment: the
    waits of ``live.database_cut`` alone, from a sync route (``time.sleep``) or an async one (``asyncio.sleep``)."""
    seen: list[dict[str, int]] = []

    def places() -> None:
        seen.append({hub: limits.limiter_for(alias).in_use for hub, alias in (("a", hubs.HUB_A_ALIAS), ("b", hubs.HUB_B_ALIAS))})

    def sleep(seconds):
        places()
        time.sleep(seconds)

    async def asynchronous_sleep(seconds):
        places()
        await asyncio.sleep(seconds)

    monkeypatch.setattr(live_database_cut, "time", SimpleNamespace(monotonic=time.monotonic, sleep=sleep))
    monkeypatch.setattr(live_database_cut, "asyncio", SimpleNamespace(sleep=asynchronous_sleep))
    return seen


def _member(hub, username: str = "boss") -> Client:
    user = get_user_model().objects.create_user(username=username, password="pw")
    with context.use_hub(hub):
        Membership.objects.create(user=user, host=hub.slug, role="hub_admin")
    client = Client(raise_request_exception=False)
    client.force_login(user)
    return client


@pytest.fixture
def boss(hub_a):
    return _member(hub_a)


def _host(hub) -> str:
    return f"{hub.slug}.localhost"


def _create(client, hub, path: str, data: dict):
    return client.post(path, json.dumps(data), content_type="application/json", HTTP_HOST=_host(hub))


_after_view_armed = False


def _after_the_view(get_response):
    def middleware(request):
        response = get_response(request)
        global _after_view_armed
        _after_view_armed = True
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
        return response

    return middleware


def _items(hub) -> list[str]:
    with context.use_hub(hub):
        return sorted(Item.objects.values_list("name", flat=True))


def _created_events(hub) -> int:
    with context.use_hub(hub):
        return OutboxEvent.objects.filter(name=ITEM_CREATED).count()


def _in(hub, alias: str, wrapper):
    """``wrapper`` around every statement of ``hub``'s alias in this thread, for the request the test makes next."""
    return connections[alias].execute_wrapper(wrapper)


def _assert_come_back(response, code: str) -> None:
    assert response.status_code == 503, response.content
    assert response.json()["error"]["code"] == code
    assert int(response["Retry-After"]) > 0
    assert "no-store" in response["Cache-Control"]


# --- Control's pool ---------------------------------------------------------------------------------------------------


def test_controls_pool_hands_out_no_connection_the_server_cut_while_it_was_idle(boss, hub_a, caplog):
    """Nothing waits, nothing fails: the business's read does not even notice that control's connection died."""
    assert boss.get(ITEMS, HTTP_HOST=_host(hub_a)).status_code == 200
    connections["default"].close()
    name = connections["default"].settings_dict["NAME"]
    pids = [session[0] for session in hubs.client_sessions_on(name)]
    assert pids, "the pool keeps its connection: there has to be one to cut"
    for pid in pids:
        _terminate(pid)
    caplog.clear()

    response = boss.get(ITEMS, HTTP_HOST=_host(hub_a))

    assert response.status_code == 200, response.content
    assert [record.getMessage() for record in caplog.records if record.name == "django.request"] == []


# --- Reads ------------------------------------------------------------------------------------------------------------


def test_a_read_cut_in_the_business_database_waits_and_answers(boss, hub_a):
    with context.use_hub(hub_a):
        Item.objects.create(name="Kept")
    cut = CutOn("demo_item")

    with _in(hub_a, hubs.HUB_A_ALIAS, cut):
        response = boss.get(ITEMS, HTTP_HOST=_host(hub_a))

    assert response.status_code == 200, response.content
    assert cut.done == 1
    assert [row["name"] for row in response.json()["rows"]] == ["Kept"]


@pytest.fixture
def unverified(monkeypatch):
    """The business's database is not yet known to be its own in this process: the request checks it first."""
    monkeypatch.setattr(identity, "_verified", set())


def test_a_cut_while_the_business_database_is_opened_waits_and_answers(boss, hub_a, unverified):
    """The first statement of a request on its database is the check that it is its own (``base.tenancy.identity``)."""
    cut = CutOn("base_hub_identity")

    with _in(hub_a, hubs.HUB_A_ALIAS, cut):
        response = boss.get(ITEMS, HTTP_HOST=_host(hub_a))

    assert response.status_code == 200, response.content
    assert cut.done == 1


def test_a_read_that_stays_cut_says_come_back_as_its_envelope(boss, hub_a):
    with _in(hub_a, hubs.HUB_A_ALIAS, CutOn("demo_item", times=None)):
        response = boss.get(ITEMS, HTTP_HOST=_host(hub_a))

    _assert_come_back(response, UNAVAILABLE)


def test_a_business_database_that_stays_cut_while_opened_says_come_back(boss, hub_a, unverified):
    """The same 503 as a business whose database cannot be reached (``base.hub_unavailable``), only after waiting."""
    started = time.monotonic()

    with _in(hub_a, hubs.HUB_A_ALIAS, CutOn("base_hub_identity", times=None)):
        response = boss.get(ITEMS, HTTP_HOST=_host(hub_a))

    _assert_come_back(response, HUB_UNAVAILABLE)
    assert time.monotonic() - started >= LIMIT_SECONDS


@pytest.mark.parametrize("language", ["en", "es"])
def test_a_page_that_stays_cut_says_come_back_in_the_language_of_the_visitor(hub_a, language):
    """With no control at all: the host's business is read before any page, so a page that needed it was a 500."""
    visitor = Client(raise_request_exception=False)

    with connections["default"].execute_wrapper(CutOn("", times=None)):
        response = visitor.get("/", HTTP_HOST=_host(hub_a), HTTP_ACCEPT="text/html", HTTP_ACCEPT_LANGUAGE=language)

    with translation.override(language):
        message = DatabaseCut(repeatable=True).message
    assert response.status_code == 503, response.content
    assert int(response["Retry-After"]) > 0
    assert "base/database_cut.html" in [template.name for template in response.templates]
    assert message in response.content.decode()


def test_a_request_that_waits_counts_as_one_request_of_the_business(boss, hub_a, monkeypatch):
    """The person who asks is read from control once the business was resolved and counted (``SaasLoginRequiredMiddleware``):
    a cut there repeats the whole request (``DatabaseCutMiddleware``), and the business's meter (``base.meter``, BASE-F40)
    counts it once, as the one request the person made, not one per try."""
    counted: list = []
    monkeypatch.setattr(middleware.meter, "count_request", counted.append)
    cut = CutOn("auth_user")

    with connections["default"].execute_wrapper(cut):
        response = boss.get(ITEMS, HTTP_HOST=_host(hub_a))

    assert response.status_code == 200, response.content
    assert cut.done == 1
    assert counted == [hub_a.pk]


# --- Writes -----------------------------------------------------------------------------------------------------------


def test_a_save_cut_while_reading_who_asks_goes_in_once(boss, hub_a):
    """Who asks (the session, the person, their role in the business, on control) is read inside the route, before its
    command: nothing of the save has started."""
    cut = CutOn("base_membership")

    with connections["default"].execute_wrapper(cut):
        response = _create(boss, hub_a, ITEMS, {"name": "Once"})

    assert response.status_code == 201, response.content
    assert cut.done == 1
    assert _items(hub_a) == ["Once"]
    assert _created_events(hub_a) == 1


def test_a_save_refused_as_read_only_goes_in_once(boss, hub_a):
    """The reference app's command touches nothing but its database (``repeatable=True``): the try the old writer
    refused is rolled back, and the next one, on a new session, goes in."""
    _old_writer(hub_a)
    refused = Refused(hub_a.db_name)

    with _in(hub_a, hubs.HUB_A_ALIAS, refused):
        response = _create(boss, hub_a, ITEMS, {"name": "Once"})

    assert response.status_code == 201, response.content
    assert refused.statements
    assert _items(hub_a) == ["Once"]
    assert _created_events(hub_a) == 1


def test_a_customer_save_refused_as_read_only_goes_in_once(boss, hub_a):
    """A customer is only written to its business's database: the refused try leaves nothing behind."""
    from apps.customer.models import Customer

    _old_writer(hub_a)
    refused = Refused(hub_a.db_name)

    with _in(hub_a, hubs.HUB_A_ALIAS, refused):
        response = _create(boss, hub_a, "/api/customer/customers", {"name": "Once"})

    assert response.status_code == 201, response.content
    assert refused.statements
    with context.use_hub(hub_a):
        assert list(Customer.objects.values_list("name", flat=True)) == ["Once"]
        assert OutboxEvent.objects.filter(name="customer.customer.created").count() == 1


APP_SAVES = [
    ("appointment", "/api/appointment/settings", {"cancellation_notice_hours": 48}, "appointment.settings.updated"),
    ("attendance", "/api/attendance/settings", {"auto_close_after_hours": 12}, "attendance.settings.updated"),
    ("cart_checkout", "/api/cart_checkout/carts", {"session_token": "once"}, "cart_checkout.cart.created"),
    ("cash_register", "/api/cash_register/registers", {"name": "Once"}, "cash_register.register.created"),
    (
        "combo",
        "/api/combo/combos",
        {"name": "Once", "supply_kind": "goods", "tax_category_key": "product.generic"},
        "combo.combo.created",
    ),
    ("customer", "/api/customer/groups", {"name": "Once"}, "customer.group.created"),
    ("flow", "/api/flow/secrets", {"name": "ONCE_KEY", "value": "test-value"}, "flow.secret.saved"),
    ("inventory", "/api/inventory/categories", {"name": "Once"}, "inventory.category.created"),
    (
        "invoice",
        "/api/invoice/series",
        {"code": "ONCE", "name": "Once", "invoice_type": "F1", "year": 2026},
        "invoice.series.created",
    ),
    ("kitchen", "/api/kitchen/stations", {"name": "Once", "destination": "display"}, "kitchen.station.created"),
    ("modifier", "/api/modifier/groups", {"name": "Once"}, "modifier.group.created"),
    ("online_booking", "/api/online_booking/settings", {"page_title": "Once"}, "online_booking.settings.updated"),
    ("payment", "/api/payment/methods", {"name": "Once"}, "payment.method.created"),
    ("pricing", "/api/pricing/price_lists", {"code": "ONCE", "name": "Once"}, "pricing.price_list.created"),
    (
        "printing",
        "/api/printing/printers",
        {"name": "Once", "kind": "system", "usage": "receipt"},
        "printing.printer.created",
    ),
    (
        "reservation",
        "/api/reservation/time_slots",
        {"day_of_week": 0, "start_time": "09:00", "end_time": "10:00"},
        "reservation.time_slot.created",
    ),
    ("sale", "/api/sale/payment_methods", {"name": "Once", "type": "other"}, "sale.payment_method.created"),
    ("schedule", "/api/schedule/settings", {"week_starts_on": 7}, "schedule.settings.updated"),
    ("service", "/api/service/categories", {"name": "Once"}, "service.category.created"),
    ("staff", "/api/staff/roles", {"name": "Once"}, "staff.role.created"),
    ("table", "/api/table/zones", {"name": "Once"}, "table.zone.created"),
    ("task", "/api/task/projects", {"code": "once", "name": "Once"}, "task.project.created"),
    ("tax", "/api/tax/categories", {"key": "product.once", "name": "Once"}, "tax.category.created"),
    (
        "website",
        "/api/website/site",
        {"template": "classic", "content": {"hero": {"title": "Once"}}},
        "website.site.updated",
    ),
    ("whatsapp_inbox", "/api/whatsapp_inbox/notes", {"text": "Once"}, "whatsapp_inbox.note.added"),
    (
        "base",
        "/api/me/preferences",
        {"language": "en", "theme_mode": "dark", "palette": "ocean", "ui_scale": 100},
        "base.profile.updated",
    ),
]


@pytest.mark.parametrize(("app", "path", "payload", "event"), APP_SAVES, ids=[case[0] for case in APP_SAVES])
def test_a_local_save_of_each_app_refused_as_read_only_goes_in_once(boss, hub_a, settings, app, path, payload, event):
    """One real route of every changed app: its refused write is rolled back and then lands once, with its event."""
    from cryptography.fernet import Fernet

    settings.FLOW_SECRETS_KEY = Fernet.generate_key().decode()
    cut = settings.LIVE["database_cut"]
    settings.LIVE = {**settings.LIVE, "database_cut": {**cut, "wait_seconds": 5}}
    if app == "whatsapp_inbox":
        from apps.whatsapp_inbox.models import Conversation

        with context.use_hub(hub_a):
            conversation = Conversation.objects.create(phone="+34600111222", contact_name="Ana")
        payload = {"id": str(conversation.id), **payload}
    if app == "combo":
        from apps.tax.models import TaxCategory

        with context.use_hub(hub_a):
            TaxCategory.objects.get_or_create(key="product.generic", defaults={"name": "Generic"})
    _old_writer(hub_a)
    refused = Refused(hub_a.db_name)

    with _in(hub_a, hubs.HUB_A_ALIAS, refused):
        response = _create(boss, hub_a, path, payload)

    assert response.status_code in {200, 201}, (response.content, refused.statements)
    assert refused.statements
    with context.use_hub(hub_a):
        assert OutboxEvent.objects.filter(name=event).count() == 1


def test_a_committed_save_whose_answer_is_lost_says_it_was_saved(boss, hub_a, settings):
    """The command committed; the database read after the view is what the cut stopped."""
    global _after_view_armed
    _after_view_armed = False
    settings.MIDDLEWARE = [*settings.MIDDLEWARE, "base.tests.test_database_cut._after_the_view"]
    cut = CutOn("")

    def after_the_command(execute, query, params, many, context):
        if not _after_view_armed:
            return execute(query, params, many, context)
        return cut(execute, query, params, many, context)

    with connections["default"].execute_wrapper(after_the_command):
        response = _create(boss, hub_a, ITEMS, {"name": "Saved"})
    _after_view_armed = False

    _assert_come_back(response, "database_answer_lost")
    assert response.json()["error"]["message"] == DatabaseCut(repeatable=False, applied=True).message
    assert cut.done == 1
    assert _items(hub_a) == ["Saved"]
    assert _created_events(hub_a) == 1


def test_two_saves_refused_at_once_leave_one_group_and_one_event(boss, hub_a):
    """Two requests racing after the old writer refused both still obey the unique constraint and the outbox."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from apps.customer.models import CustomerGroup

    other = _member(hub_a, username="other")
    _old_writer(hub_a)
    lock = threading.Lock()
    refused = []

    class BothRefused:
        def __call__(self, execute, query, params, many, context):
            try:
                return execute(query, params, many, context)
            except DatabaseError:
                statement = str(query).lstrip().upper()
                if statement.startswith(("INSERT", "UPDATE", "DELETE")) or "FOR UPDATE" in statement or "FOR KEY SHARE" in statement:
                    with lock:
                        refused.append(statement)
                        if len(refused) == 2:
                            _read_only(hub_a.db_name, False)
                raise

    def save(client):
        with _in(hub_a, hubs.HUB_A_ALIAS, BothRefused()):
            return _create(client, hub_a, "/api/customer/groups", {"name": "Once"})

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = [future.result() for future in [pool.submit(save, boss), pool.submit(save, other)]]

    assert sorted(response.status_code for response in responses) == [201, 409]
    assert len(refused) >= 2
    with context.use_hub(hub_a):
        assert CustomerGroup.objects.filter(name="Once").count() == 1
        assert OutboxEvent.objects.filter(name="customer.group.created").count() == 1


def test_every_routed_command_declares_whether_a_cut_may_repeat_it():
    """A new route must be reviewed: local-only commands repeat; the exclusions say why they must not."""
    import ast
    from pathlib import Path

    from live.operations import registry

    root = Path(__file__).resolve().parents[2]
    routed = set()
    for path in [*root.glob("apps/*/api.py"), *root.glob("base/api.py")]:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call) and ast.unparse(node.func) == "bind" and len(node.args) >= 2:
                routed.add(ast.literal_eval(node.args[1]))
    exclusions = {
        "appointment.appointment.create",
        "appointment.appointment.bulk_create",
        "appointment.appointment.charge",
        "appointment.recurring.create",
        "appointment.recurring.materialize",
        "appointment.recurring.update",
        "base.app.enable",
        "base.approval.approve",
        "base.blueprint.import",
        "base.device.prune",
        "base.device.remove",
        "base.failed_event.retry",
        "base.failed_event.retry_all",
        "base.hub.reset",
        "base.person.badge_set",
        "base.pin.set",
        "base.profile.avatar_set",
        "base.saas_pass.create",
        "base.support.report",
        "cart_checkout.checkout.initiate",
        "cash_register.session.open",
        "combo.combo.upload_image",
        "flow.flow.run",
        "flow.question.answer",
        "flow.run.retry",
        "inventory.product.upload_image",
        "invoice.invoice.create",
        "invoice.invoice.create_from_sale",
        "invoice.invoice.mark_paid",
        "invoice.invoice.print",
        "invoice.invoice.rectify",
        "invoice.invoice.rectify_from_refund",
        "invoice.invoice.rectify_from_void",
        "invoice.invoice.substitute",
        "kitchen.item.bump",
        "kitchen.item.recall",
        "kitchen.routing.clear",
        "kitchen.routing.set",
        "kitchen.settings.update",
        "kitchen.station.delete",
        "kitchen.station.update",
        "kitchen.ticket.cancel",
        "kitchen.ticket.create",
        "kitchen.ticket.delete",
        "kitchen.ticket.ready",
        "kitchen.ticket.recall",
        "kitchen.ticket.reprint",
        "kitchen.ticket.send",
        "kitchen.ticket.serve",
        "kitchen.ticket.set_rush",
        "kitchen.ticket.start",
        "online_booking.public.book",
        "payment.payment.create",
        "sale.order.fire",
        "sale.sale.complete",
        "sale.sale.complete_over_limit",
        "sale.sale.issue_documents",
        "sale.sale.print",
        "sale.sale.refund",
        "sale.sale.void",
        "service.service.upload_image",
        "table.table.bulk_create",
        "table.table.create",
        "task.task.create",
        "website.image.upload",
        "whatsapp_inbox.channel.connect",
        "whatsapp_inbox.channel.disconnect",
        "whatsapp_inbox.channel.prepare",
        "whatsapp_inbox.conversation.erase",
        "whatsapp_inbox.message.notify",
        "whatsapp_inbox.message.retry",
        "whatsapp_inbox.message.send",
        "whatsapp_inbox.template.create",
        "whatsapp_inbox.template.delete",
        "whatsapp_inbox.template.retry",
        "whatsapp_inbox.template.update",
        "whatsapp_inbox.template_sample.upload",
    }
    unknown = exclusions - registry.keys()
    assert not unknown
    wrong = []
    for operation in registry.values():
        if operation.kind != "command" or operation.name not in routed:
            continue
        excluded = operation.name in exclusions or operation.name.startswith(
            ("verifactu.", "base.assistant.", "base.file.")
        )
        if operation.repeatable == excluded:
            wrong.append(operation.name)
    assert wrong == []



#: What a try does that the ROLLBACK of its database does not undo, or a number it takes on the way (PLAN-DB, round
#: 2026-11-04e, point 5): a command that may repeat never reaches one of them before its COMMIT (BASE-F111).
NOT_UNDONE_BY_A_ROLLBACK = {
    "apps.appointment.services._next_number": "numbers an appointment",
    "apps.cart_checkout.services._number": "numbers an order",
    "apps.cash_register.services._number": "numbers a till session",
    "apps.invoice.services._take_number": "numbers an invoice",
    "apps.kitchen.services.take_number": "numbers a kitchen ticket",
    "apps.payment.services._number": "numbers a payment",
    "apps.sale.services._number": "numbers a sale",
    "apps.table.services._next_number": "numbers a table",
    "apps.task.services._next_number": "numbers a task",
    "base.images.keep_photo": "keeps a file under a new name",
    "base.throttle.AttemptLimit.failed": "counts a try in the cache",
}
#: Modules whose use is a call to another system: what was sent stays sent.
OTHER_SYSTEMS = ("httpx", "requests", "urllib.request", "smtplib", "django.core.mail")


def _chain(node) -> list[str] | None:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    return [node.id, *reversed(parts)] if isinstance(node, ast.Name) else None


def _ours(obj) -> bool:
    module = getattr(obj, "__module__", None) or ""
    return module.startswith(("apps.", "base.")) and ".tests" not in module


def _dotted(obj) -> str | None:
    if isinstance(obj, types.ModuleType):
        return obj.__name__
    module, name = getattr(obj, "__module__", None), getattr(obj, "__qualname__", None)
    return f"{module}.{name}" if isinstance(module, str) and isinstance(name, str) else None


def _names_of(fn, tree) -> dict:
    """What a name in ``fn`` means: its module's globals, its closure and its own imports (an import inside a function
    is where a call to another system likes to hide)."""
    names = dict(fn.__globals__)
    for name, cell in zip(fn.__code__.co_freevars, fn.__closure__ or ()):
        try:
            names[name] = cell.cell_contents
        except ValueError:
            continue
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            module = importlib.import_module(node.module)
            for alias in node.names:
                found = getattr(module, alias.name, None)
                names[alias.asname or alias.name] = found or importlib.import_module(f"{node.module}.{alias.name}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                importlib.import_module(alias.name)
                names[alias.asname or alias.name.partition(".")[0]] = importlib.import_module(
                    alias.name if alias.asname else alias.name.partition(".")[0]
                )
    return names


def _meant(names: dict, node):
    """The object a name or a dotted name of a function's code stands for, or ``None``."""
    parts = _chain(node)
    if not parts or parts[0] not in names:
        return None
    obj = names[parts[0]]
    for part in parts[1:]:
        try:
            obj = getattr(obj, part)
        except Exception:
            return None
    return obj


@functools.cache
def _steps(fn) -> tuple[frozenset[str], tuple, frozenset[str]]:
    """What ``fn`` touches (by dotted name), the functions of the Hub it goes on to (and the methods its models
    override) and the operations it names. What it leaves for after the COMMIT of its operation
    (``live.operations.on_commit(...)``) is not a step; Django's own ``transaction.on_commit`` on ``default`` would run at
    once in a business's command, so it is."""
    from live.operations import on_commit, registry

    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    except (OSError, TypeError):
        return frozenset(), (), frozenset()
    names = _names_of(fn, tree)
    later = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _meant(names, node.func) is on_commit:
            for argument in [*node.args, *(keyword.value for keyword in node.keywords)]:
                later.update(id(inner) for inner in ast.walk(argument))
    touched, onward, named = set(), [], set()
    for node in ast.walk(tree):
        if id(node) in later:
            continue
        if isinstance(node, ast.Constant) and node.value in registry:
            named.add(node.value)
        obj = _meant(names, node) if isinstance(node, (ast.Name, ast.Attribute)) else None
        if obj is None:
            continue
        if isinstance(obj, str):
            if obj in registry:
                named.add(obj)
            continue
        if isinstance(obj, types.MethodType):
            obj = obj.__func__
        dotted = _dotted(obj)
        if dotted is not None:
            touched.add(dotted)
        if isinstance(obj, types.FunctionType) and _ours(obj):
            onward.append(obj)
        elif isinstance(obj, type) and _ours(obj):
            overrides = (vars(obj).get(key) for key in ("save", "delete", "clean"))
            onward.extend(method for method in overrides if isinstance(method, types.FunctionType))
    return frozenset(touched), tuple(onward), frozenset(named)


def _reached(operation) -> dict[str, tuple[str, ...]]:
    """Everything ``operation`` reaches before its COMMIT, by dotted name, with the way there."""
    from live.operations import registry

    ways: dict[str, tuple[str, ...]] = {}
    pending = [(operation.fn, (operation.name,))]
    seen, named_seen = set(), {operation.name}
    while pending:
        fn, way = pending.pop()
        fn = inspect.unwrap(fn)
        if fn in seen:
            continue
        seen.add(fn)
        touched, onward, named = _steps(fn)
        for dotted in touched:
            ways.setdefault(dotted, way)
        pending.extend((step, (*way, step.__qualname__)) for step in onward)
        for name in named - named_seen:
            named_seen.add(name)
            pending.append((registry[name].fn, (*way, name)))
    return ways


def _resolve(dotted: str):
    """The function ``dotted`` names: a name that is no longer there would leave its check silent."""
    parts = dotted.split(".")
    for cut in range(len(parts) - 1, 0, -1):
        try:
            target = importlib.import_module(".".join(parts[:cut]))
        except ImportError:
            continue
        for part in parts[cut:]:
            target = getattr(target, part)
        return target
    raise LookupError(dotted)


def _never_twice(operation) -> list[str]:
    """What of ``operation`` a repeat would do twice, or a number it would take blindly."""
    found = []
    for dotted, way in sorted(_reached(operation).items()):
        why = NOT_UNDONE_BY_A_ROLLBACK.get(dotted)
        if why is None and any(dotted == module or dotted.startswith(f"{module}.") for module in OTHER_SYSTEMS):
            why = "calls another system"
        if why is not None:
            found.append(f"{operation.name} {why}: {' > '.join(way)} > {dotted}")
    return found


def test_a_command_that_may_repeat_reaches_nothing_its_rollback_leaves_behind():
    """The exclusions above are written by hand (hub#1051 marked a photo upload and the kitchen's numbering): this walks
    every repeatable command's code, and what it calls, to what a ROLLBACK does not undo."""
    from live.operations import registry

    for dotted in NOT_UNDONE_BY_A_ROLLBACK:
        assert callable(_resolve(dotted)), dotted
    # The walk sees what it must: commands that do take a number, keep a photo or call another system.
    assert any("take_number" in line for line in _never_twice(registry["kitchen.ticket.create"]))
    assert any("_take_number" in line for line in _never_twice(registry["invoice.invoice.create"]))
    assert any("keep_photo" in line for line in _never_twice(registry["combo.combo.upload_image"]))
    assert any("another system" in line for line in _never_twice(registry["whatsapp_inbox.message.send"]))

    found = [line for operation in registry.values() if operation.repeatable for line in _never_twice(operation)]

    assert found == []

def test_a_save_that_numbers_is_never_repeated_blindly(boss, hub_a):
    """A task is numbered (TSK-…): its command does not say it may run again, so a cut after it began asks to check."""
    _old_writer(hub_a)
    refused = Refused(hub_a.db_name)

    with _in(hub_a, hubs.HUB_A_ALIAS, refused):
        response = _create(boss, hub_a, TASKS, {"title": "Never twice"})

    _assert_come_back(response, UNKNOWN)
    assert len(refused.statements) == 1
    with context.use_hub(hub_a):
        assert not Task.objects.exists()


def test_a_wait_holds_no_place_of_the_business_plan(boss, hub_a, waits):
    """Free gives one transaction at once: a request holding it while it waits would refuse every other one."""
    _old_writer(hub_a)

    with _in(hub_a, hubs.HUB_A_ALIAS, Refused(hub_a.db_name)):
        response = _create(boss, hub_a, ITEMS, {"name": "Once"})

    assert waits, "the save waited for the database"
    assert all(places == {"a": 0, "b": 0} for places in waits), waits
    assert response.status_code == 201, response.content


def test_a_cut_in_one_business_repeats_in_its_own_database_only(boss, hub_a, hub_b, waits):
    """Its old writer refuses ``a``'s writes: ``a``'s save waits and goes in ``a``; ``b``'s, a moment later, at once."""
    other = _member(hub_b, username="other")
    _old_writer(hub_a)

    with _in(hub_a, hubs.HUB_A_ALIAS, Refused(hub_a.db_name)):
        in_a = _create(boss, hub_a, ITEMS, {"name": "In a"})
    waited_for_a = len(waits)
    in_b = _create(other, hub_b, ITEMS, {"name": "In b"})

    assert (in_a.status_code, in_b.status_code) == (201, 201), (in_a.content, in_b.content)
    assert waited_for_a > 0
    assert len(waits) == waited_for_a
    assert (_items(hub_a), _items(hub_b)) == (["In a"], ["In b"])
    assert (_created_events(hub_a), _created_events(hub_b)) == (1, 1)


# --- What tries again on its own --------------------------------------------------------------------------------------


def test_a_call_of_the_saas_gets_its_503_at_once(hub_a, settings):
    """``/internal`` is the SaaS's, which tries again on its own: it waits for nobody, with ``Retry-After`` all the same."""
    if (cut := settings.LIVE.get("database_cut")) is not None:
        settings.LIVE = {**settings.LIVE, "database_cut": {**cut, "wait_seconds": 5}}
    started = time.monotonic()

    with connections["default"].execute_wrapper(CutOn("base_hub", times=None)):
        response = signed(Client(raise_request_exception=False), "get", f"/internal/hubs/{hub_a.id}", b"")

    _assert_come_back(response, UNAVAILABLE)
    assert time.monotonic() - started < 2
