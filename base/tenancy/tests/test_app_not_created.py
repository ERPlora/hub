"""A model of an app a business has not created yet, touched where no operation's gate is (hub#608; PLAN-DB §4, spec
2026-10-11 «tablas al activar» §9): an ``events.py``, the admin, a task. The ``TenantRouter`` answers the 404
``app_inactive`` an app that is off answers, before any SQL, never a ``relation … does not exist``.

Real databases, committed (no test case: the migrator registers its own aliases): two businesses cloned from a template
with the platform alone, both confirmed by the migrator as every ready hub is, A with Printing's tables and B without.
The admin's tests go through a request and need a test case: there the row in control says what B lacks.
"""

import datetime as dt
import logging
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.http import HttpRequest
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from live.context import OperationContext, Scope
from live.errors import AppInactive
from live.models import OutboxEvent
from live.operations import atomic, get

from apps.printing.models import Printer, PrintJob
from apps.tax.models import TaxCategory
from base import activation, services
from base.activation import ON
from base.middleware import HubDatabaseMiddleware
from base.models import AppActivation, EventDelivery, HubUser, TaskSchedule
from base.tenancy import migrator, offboarding
from base.tenancy.context import AppNotCreated, use_hub
from base.tenancy.router import TenantRouter
from base.tenancy.tests import hubs
from base.tests.test_worker_activations import (  # noqa: F401 (fixtures)
    APP,
    business,
    fresh,
    nothing_checked_yet,
    platform_template,
    row,
    run_pass,
    turn_on,
)
from control.models import Hub

pytestmark = pytest.mark.usefixtures("no_test_fallback")

HUB_DB = pytest.mark.django_db(databases=hubs.HUB_DATABASES)

router = TenantRouter()


@pytest.fixture
def two_businesses(business):  # noqa: F811
    """A, with Printing's tables, and B, with the platform's alone: rows as the migrator left them."""
    with_it, without_it = business("with-printing"), business("without-printing")
    migrator.ensure_schema(with_it, add=[APP])
    migrator.ensure_schema(without_it)
    return fresh(with_it), fresh(without_it)


def assert_refused(model=PrintJob) -> AppInactive:
    with pytest.raises(AppInactive) as refused:
        model.objects.count()
    return refused.value


# ── The refusal, and the other business ─────────────────────────────────────────────────────────────────────────────


def test_reading_a_model_of_an_app_it_lacks_is_404_app_inactive_and_the_business_that_has_it_is_served(two_businesses):
    with_it, without_it = two_businesses

    with use_hub(without_it):
        refused = assert_refused()
    with use_hub(with_it):
        served = PrintJob.objects.count()

    assert (refused.status, refused.envelope()["error"]["code"]) == (404, "app_inactive")
    assert served == 0


def test_writing_a_model_of_an_app_it_lacks_is_refused_and_the_business_that_has_it_writes(two_businesses):
    with_it, without_it = two_businesses

    with use_hub(without_it), pytest.raises(AppInactive) as refused:
        Printer(name="Bar", kind="system", usage="receipt").save()
    with use_hub(with_it):
        Printer(name="Bar", kind="system", usage="receipt").save()
        written = Printer.objects.count()

    assert refused.value.code == "app_inactive"
    assert written == 1


@pytest.mark.parametrize("language", ["en", "es"])
def test_it_says_what_an_operation_of_an_app_that_is_off_says_in_the_language_running(two_businesses, language):
    from django.utils import translation

    _, without_it = two_businesses
    op = get("printing.job.list")
    ctx = OperationContext(
        scope=Scope("host", without_it.slug), actor="ana", permissions=frozenset({"*"}), language=language
    )

    with use_hub(without_it):
        with pytest.raises(AppInactive) as by_the_operation:
            op(ctx, op.input())
        with translation.override(language):
            refused = assert_refused()

    assert refused.message == by_the_operation.value.message


def test_no_sql_reaches_the_database_so_the_transaction_goes_on(two_businesses):
    _, without_it = two_businesses

    with use_hub(without_it), atomic():
        assert_refused()
        asked_after = AppActivation.objects.filter(host=without_it.slug).exists()

    assert asked_after is True


def test_an_operation_whose_row_says_on_without_its_tables_answers_the_same_404(two_businesses):
    """A row or a cache behind what the database has (PLAN-DB §9, «caché atrasada sin tablas») never reaches the SQL."""
    _, without_it = two_businesses
    op = get("printing.job.list")
    ctx = OperationContext(scope=Scope("host", without_it.slug), actor="ana", permissions=frozenset({"*"}), language="en")
    with use_hub(without_it):
        AppActivation.objects.filter(host=without_it.slug, app=APP).update(state=ON)
        activation.forget(without_it.slug)

        with pytest.raises(AppInactive) as refused:
            op(ctx, op.input())

    assert refused.value.code == "app_inactive"


# ── What it costs: nothing for what a business has ──────────────────────────────────────────────────────────────────


def counted_cache(monkeypatch) -> list[str]:
    """Every call of ``base.activation``'s cache, by name, still answered by the real one."""
    real, calls = activation.cache, []

    def counted(name):
        def call(*args, **kwargs):
            calls.append(name)
            return getattr(real, name)(*args, **kwargs)

        return call

    monkeypatch.setattr(activation, "cache", SimpleNamespace(get=counted("get"), set=counted("set"), delete=counted("delete")))
    return calls


def test_what_a_business_has_asks_neither_control_nor_the_cache_on_any_query(two_businesses, monkeypatch):
    with_it, _ = two_businesses
    cache_calls = counted_cache(monkeypatch)

    with use_hub(with_it), CaptureQueriesContext(connections["default"]) as on_control:
        for _ in range(20):
            PrintJob.objects.count()
            Printer.objects.exists()

    assert len(on_control) == 0
    assert cache_calls == []


def test_refused_again_and_again_it_reads_control_once_and_then_the_cache(two_businesses, monkeypatch):
    _, without_it = two_businesses
    cache_calls = counted_cache(monkeypatch)

    with use_hub(without_it), CaptureQueriesContext(connections["default"]) as on_control:
        for _ in range(5):
            assert_refused()

    assert len(on_control) == 1
    assert cache_calls == ["get", "set", "get", "get", "get", "get"]


# ── Whoever makes the tables, and whoever held the business from before ─────────────────────────────────────────────


def test_an_app_just_created_is_served_to_a_context_that_held_the_business_from_before(two_businesses):
    """The kept list said «not yet» a moment ago: ``ensure_schema`` forgets it, whoever holds an old row is served."""
    _, without_it = two_businesses
    held = fresh(without_it)
    with use_hub(held):
        assert_refused()

    migrator.ensure_schema(fresh(without_it), add=[APP])

    assert APP not in held.schema_apps
    with use_hub(held):
        assert PrintJob.objects.count() == 0


def test_forgetting_a_business_s_apps_forgets_what_it_has_created_too(two_businesses):
    """What every change's COMMIT does (``base.app.activation_settle``): read again, the row has the app."""
    _, without_it = two_businesses
    held = fresh(without_it)
    with use_hub(held):
        assert_refused()
    Hub.objects.filter(pk=without_it.pk).update(schema_apps=fresh(without_it).schema_apps | {APP: "0001_initial"})

    activation.forget(without_it.slug)

    assert activation.has_tables(held, APP) is True


def test_turned_on_the_worker_makes_its_tables_and_its_models_answer(business):  # noqa: F811
    hub = business("turned-on")
    migrator.ensure_schema(hub)
    held = fresh(hub)
    with use_hub(held):
        assert_refused()

    assert turn_on(hub)["state"] == "creating"
    with use_hub(fresh(hub)):
        assert_refused()
    run_pass()

    assert row(hub).state == ON
    with use_hub(fresh(hub)):
        assert PrintJob.objects.count() == 0
    with use_hub(held):
        assert PrintJob.objects.count() == 0


def test_the_migrator_makes_tables_and_runs_their_migrations_from_inside_the_business_s_context(two_businesses):
    """Tax's migrations load its catalogue (``RunPython``): the migrator's alias is never asked what the hub has."""
    _, without_it = two_businesses

    with use_hub(without_it):
        assert_refused(TaxCategory)
        migrator.ensure_schema(without_it, add=["tax"])

        assert TaxCategory.objects.count() > 0


def test_a_hub_s_object_on_its_alias_is_refused_and_one_on_the_migrator_s_alias_is_not(two_businesses):
    """A reverse relation (``instance`` hint) goes where its object is: on the hub's alias, what the hub lacks is
    refused; on the migrator's, a migration's ``RunPython`` is making it, with or without a context."""
    _, without_it = two_businesses
    related = HubUser()
    ddl = f"{without_it.db_name}__ddl"

    with use_hub(without_it) as active:
        related._state.db = active.alias
        with pytest.raises(AppInactive):
            router.db_for_read(PrintJob, instance=related)
        with pytest.raises(AppInactive):
            router.db_for_write(PrintJob, instance=related)

        related._state.db = ddl
        assert router.db_for_read(PrintJob, instance=related) == ddl
        assert router.db_for_write(PrintJob, instance=related) == ddl

    assert router.db_for_read(PrintJob, instance=related) == ddl


# ── What is never refused ───────────────────────────────────────────────────────────────────────────────────────────


def test_a_business_the_migrator_never_confirmed_is_not_refused(two_businesses):
    """``schema_apps`` empty (never confirmed: ``migrator.is_behind``) says nothing of what its database has: the next
    ``migrate_hubs`` confirms it; meanwhile a business with its tables is not refused them."""
    with_it, _ = two_businesses
    Hub.objects.filter(pk=with_it.pk).update(schema_apps={})

    with use_hub(fresh(with_it)):
        assert PrintJob.objects.count() == 0


def test_a_row_read_again_that_was_never_confirmed_is_not_refused_either(two_businesses):
    with_it, _ = two_businesses
    held = fresh(with_it)
    held.schema_apps = {label: "0001_initial" for label in migrator.platform_apps()}
    Hub.objects.filter(pk=with_it.pk).update(schema_apps={})

    with use_hub(held):
        assert PrintJob.objects.count() == 0


def test_the_platform_is_never_refused_whatever_the_row_lists(two_businesses):
    """Only a module is created or not: the platform's tables (``base``, ``live``) are in every hub's database."""
    _, without_it = two_businesses
    Hub.objects.filter(pk=without_it.pk).update(schema_apps={"base": "0001_initial"})

    with use_hub(fresh(without_it)):
        assert HubUser.objects.count() == 0
        assert OutboxEvent.objects.count() == 0


# ── Where no operation's gate is: an events.py, a task, the admin ───────────────────────────────────────────────────


def test_a_reaction_that_touches_it_fails_as_a_refusal_of_the_business_and_is_tried_again(two_businesses, caplog):
    _, without_it = two_businesses
    now = timezone.now()

    with use_hub(without_it), caplog.at_level(logging.WARNING, logger="base.services"):
        event = OutboxEvent.objects.create(
            scope_kind="host", scope_key=without_it.slug, name="sale.sale.paid", actor="ana"
        )
        delivery = EventDelivery.objects.create(event=event, app_label="inventory", next_attempt_at=now)
        outcome = services.relay_deliver_next(
            now,
            deliver=lambda app_label, event: PrintJob.objects.count(),
            listeners=lambda event: [],
            max_depth=3,
            max_attempts=3,
            backoff=lambda attempts: dt.timedelta(seconds=2),
        )
        delivery.refresh_from_db()

    assert outcome[1] is False
    assert delivery.status == EventDelivery.Status.PENDING
    assert delivery.last_error.startswith("AppNotCreated:")
    logged = [record for record in caplog.records if "app_inactive" in record.getMessage()]
    assert [record.levelno for record in logged] == [logging.WARNING]


def test_a_task_that_touches_it_is_logged_with_the_refusal_and_moves_to_its_next_time(two_businesses, caplog):
    _, without_it = two_businesses
    now = timezone.now()
    later = now + dt.timedelta(hours=1)

    with use_hub(without_it), caplog.at_level(logging.ERROR, logger="base.services"):
        schedule = TaskSchedule.objects.create(
            app_label="demo", name="touches", operation="demo.touches", cron="0 * * * *", next_run=now
        )
        outcome = services.run_next_due_task(
            now, execute=lambda name: PrintJob.objects.count(), reschedule=lambda cron, at: later
        )
        schedule.refresh_from_db()

    assert outcome[1] is False
    assert schedule.next_run == later
    assert [record.exc_info[1].code for record in caplog.records if record.exc_info] == ["app_inactive"]


def test_at_a_business_s_baja_an_app_it_lacks_has_no_documents_to_keep(two_businesses):
    """Every app that keeps fiscal documents is asked, on or not (``base.tenancy.offboarding``): a real hook on an app
    whose tables the business never had is «none», not a refusal that would keep its database for ever."""
    _, without_it = two_businesses

    assert offboarding.fiscal_documents_kept(without_it) == []


def platform_only() -> dict[str, str]:
    return {label: "0001_initial" for label in migrator.platform_apps()}


def admin_on(client, hub) -> None:
    client.force_login(get_user_model().objects.create_superuser("root", "root@example.com", "pw"))
    client.get(f"/admin/hub/{hub.slug}/", HTTP_HOST="hubs.localhost")


@HUB_DB
def test_the_admin_s_page_of_an_app_not_created_goes_back_to_its_index_saying_so(client, hub_b):
    Hub.objects.filter(pk=hub_b.pk).update(schema_apps=platform_only())
    admin_on(client, hub_b)

    page = client.get("/admin/printing/printjob/", HTTP_HOST="hubs.localhost", HTTP_ACCEPT="text/html", follow=True)

    assert page.status_code == 200
    assert page.redirect_chain == [("/admin/", 302)]
    with use_hub(fresh(hub_b)):
        refused = assert_refused()
    assert refused.message in page.content.decode()


@HUB_DB
def test_a_call_that_does_not_ask_for_a_page_gets_the_404_envelope(client, hub_b):
    Hub.objects.filter(pk=hub_b.pk).update(schema_apps=platform_only())
    admin_on(client, hub_b)

    answer = client.get("/admin/printing/printjob/", HTTP_HOST="hubs.localhost")

    assert answer.status_code == 404
    assert answer.json()["error"]["code"] == "app_inactive"


@HUB_DB
def test_the_admin_s_page_of_an_app_the_business_has_is_served(client, hub_b):
    Hub.objects.filter(pk=hub_b.pk).update(schema_apps=platform_only() | {APP: "0001_initial"})
    admin_on(client, hub_b)

    page = client.get("/admin/printing/printjob/", HTTP_HOST="hubs.localhost", HTTP_ACCEPT="text/html")

    assert page.status_code == 200


@HUB_DB
def test_the_admin_s_index_lists_what_the_business_has_and_never_asks_what_it_lacks(client, hub_b):
    """Its list runs every model's ``has_add_permission``, and Tax's reads its table: without Tax's tables, every page of
    the admin would fail. What the business lacks is left out, as a hub's model is while no business is chosen."""
    Hub.objects.filter(pk=hub_b.pk).update(schema_apps=platform_only() | {APP: "0001_initial"})
    admin_on(client, hub_b)

    index = client.get("/admin/", HTTP_HOST="hubs.localhost", HTTP_ACCEPT="text/html")

    assert index.status_code == 200
    listed = {app["app_label"] for app in index.context["app_list"]}
    assert APP in listed
    assert "base" in listed
    assert "tax" not in listed


@HUB_DB
def test_a_business_never_confirmed_lists_every_app_in_the_admin(client, hub_b):
    Hub.objects.filter(pk=hub_b.pk).update(schema_apps={})
    admin_on(client, hub_b)

    index = client.get("/admin/", HTTP_HOST="hubs.localhost", HTTP_ACCEPT="text/html")

    assert {APP, "tax"} <= {app["app_label"] for app in index.context["app_list"]}


def page_request(path: str, **attributes) -> HttpRequest:
    request = RequestFactory().get(path, HTTP_ACCEPT="text/html")
    for name, value in attributes.items():
        setattr(request, name, value)
    return request


def test_the_admin_s_index_itself_refused_answers_its_404_and_never_redirects_to_itself():
    """Going back to the index is what a page does; the index going back to itself would be a loop in the browser."""
    refused = AppNotCreated("Printing is turned off in this business.")

    answer = HubDatabaseMiddleware(lambda request: None).process_exception(
        page_request("/admin/", platform_host=True), refused
    )

    assert answer.status_code == 404
    assert answer.content.decode() == refused.message


def test_a_page_of_a_business_s_own_host_answers_its_404_with_its_message():
    refused = AppNotCreated("Printing is turned off in this business.")

    answer = HubDatabaseMiddleware(lambda request: None).process_exception(page_request("/", platform_host=False), refused)

    assert answer.status_code == 404
    assert answer.content.decode() == refused.message
