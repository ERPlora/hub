"""A template that turns on apps still to set up loads their data by itself (hub#609; BASE-F31, BASE-F32, BASE-F33).

A template's load turns its apps on (``base.app.enable``); one whose tables its hub's database lacks is ``creating``, and
the worker makes them (``base.app.activation_settle``). What waited for it loads in that same transaction: the app goes
on with its data or, if the worker dies, neither did, and the next pass does both. Nothing but the rows says what waits,
so a restart loses nothing. Whoever loaded it never comes back, and a failure is on the report.

Real databases, committed, and the real worker: the businesses of ``test_worker_activations`` (only the platform's
tables, so every app is one to set up).
"""

import base64
import dataclasses
import datetime as dt
from unittest import mock

import pytest
from django.apps import apps
from django.utils import timezone
from django.utils.translation import override
from live.context import OperationContext, Scope
from live.errors import Conflict
from live.models import OutboxEvent
from live.operations import get

from base import blueprint, events, services, worker
from base.activation import CREATING, FAILED, OFF, ON
from base.models import AppActivation, ImportBatch
from base.tenancy import migrator
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_worker_activations import (  # noqa: F401 (the fixtures)
    business,
    fresh,
    no_test_fallback,
    nothing_checked_yet,
    platform_template,
    row,
    run_pass,
    tables,
    turn_off,
    turn_on,
)
from control.models import HubDue

pytestmark = pytest.mark.usefixtures("no_test_fallback")

SALON = "hair_salon.en"
#: In the seed: 8 services in 4 categories, and 5 products in 1.
SALON_SERVICES, SALON_CATEGORIES, SALON_PRODUCTS = 8, 4, 5
#: In the seed: 16 products in 6 categories.
RESTAURANT, RESTAURANT_PRODUCTS = "restaurant.en", 16


def as_admin(hub, language: str = "en") -> OperationContext:
    return OperationContext(scope=Scope("host", hub.slug), actor="ana", permissions=frozenset({"*"}), language=language)


def call(hub, name: str, language: str = "en", **data) -> dict:
    op = get(name)
    with use_hub(fresh(hub)):
        return op(as_admin(hub, language), op.input.model_validate(data)).model_dump(mode="json")


def load_template(hub, template: str = SALON, choose: tuple[str, ...] = ("service",), language: str = "en") -> dict:
    """The template loaded by who administers the business: only the apps ``choose`` of it, all of them with none."""
    data = {"template": template} | ({"apps": list(choose)} if choose else {})
    return call(hub, "base.blueprint.import", language, **data)


def report_of(hub, load: dict) -> dict:
    return call(hub, "base.import.detail", id=load["id"])


def by_app(load: dict) -> dict[str, dict]:
    return {app["id"]: app for app in load["report"]["apps"]}


def count(hub, app: str, model: str) -> int:
    with use_hub(fresh(hub)):
        return apps.get_model(app, model).objects.count()


def listed(hub, dataset: str) -> int:
    """The rows of ``dataset`` its app shows: undoing a load archives some (a service) rather than deleting them."""
    with use_hub(fresh(hub)):
        return blueprint.dataset(dataset).count(as_admin(hub))


def events_of(hub, name: str) -> list[dict]:
    with use_hub(fresh(hub)):
        return [event.payload for event in OutboxEvent.objects.filter(name=name).order_by("id")]


def internal(hub) -> OperationContext:
    return OperationContext(scope=Scope("host", hub.slug), actor="system", permissions=frozenset({"*"}), language="en")


# ── It says it waits; it loads by itself ────────────────────────────────────────────────────────────────────────


def test_a_load_says_the_app_it_waits_for_is_being_set_up_and_offers_no_retry_meanwhile(business):
    hub = business("a")

    load = load_template(hub)

    assert row(hub, "service").state == CREATING
    assert by_app(load)["service"]["status"] == blueprint.WAITING
    assert by_app(load)["service"]["reason"]
    assert (load["status"], load["retry"], load["retry_blocked"]) == ("partial", False, "waiting")
    assert report_of(hub, load)["report"] == load["report"]


def test_a_load_that_waited_has_its_data_once_the_worker_turns_its_app_on_and_nobody_came_back(business):
    hub = business("a")
    load = load_template(hub)

    run_pass()

    assert row(hub, "service").state == ON
    assert count(hub, "service", "Service") == SALON_SERVICES
    done = report_of(hub, load)
    assert by_app(done)["service"]["status"] == "applied"
    assert by_app(done)["service"]["reason"] == ""
    assert [part["created"] for part in by_app(done)["service"]["datasets"]] == [SALON_CATEGORIES, SALON_SERVICES]
    assert (done["status"], done["rows"], done["retry"]) == ("complete", SALON_CATEGORIES + SALON_SERVICES, False)
    assert done["retry_blocked"] == "complete"
    # Its live notice: Settings › Data and the Home follow this event.
    assert [event["id"] for event in events_of(hub, events.BLUEPRINT_IMPORTED)] == [load["id"], load["id"]]
    assert call(hub, "base.import.list")["unfinished"] is None


def test_what_loads_later_keeps_the_templates_order_the_categories_before_what_names_them(business):
    hub = business("a")
    load_template(hub)

    run_pass()

    with use_hub(fresh(hub)):
        services_loaded = list(apps.get_model("service", "Service").objects.all())
    assert services_loaded and all(service.category_id is not None for service in services_loaded)


def test_the_whole_template_waits_and_loads_with_nothing_chosen(business):
    hub = business("a")

    load = load_template(hub, choose=())
    waited = [app["id"] for app in load["report"]["apps"] if app["status"] == blueprint.WAITING]

    assert {"service", "inventory"} <= set(waited)
    run_pass()

    done = report_of(hub, load)
    assert count(hub, "service", "Service") == SALON_SERVICES
    assert count(hub, "inventory", "Product") == SALON_PRODUCTS
    assert not [app["id"] for app in done["report"]["apps"] if app["status"] == blueprint.WAITING]


def test_what_waited_reads_in_the_language_of_who_loaded_it_though_the_worker_loaded_it(business):
    hub = business("a")
    load = load_template(hub, language="es")

    run_pass()

    with override("es"):
        said = str(blueprint.dataset("service.service").label)
    with override("en"):
        assert said != str(blueprint.dataset("service.service").label)
    assert by_app(report_of(hub, load))["service"]["datasets"][1]["label"] == said


def test_how_its_setup_goes_reads_in_the_language_of_who_asks(business):
    hub = business("a")
    load = load_template(hub, language="en")
    with override("es"):
        said = str(blueprint.BEING_SET_UP)
    with override("en"):
        assert said != str(blueprint.BEING_SET_UP)

    assert by_app(call(hub, "base.import.detail", "es", id=load["id"]))["service"]["reason"] == said


@pytest.mark.parametrize(
    "text",
    [
        blueprint.BEING_SET_UP,
        blueprint.SETUP_FAILING,
        blueprint.FILE_BEING_SET_UP,
        blueprint.STOPPED_TURNED_OFF,
        blueprint.STOPPED_UNDONE,
        blueprint.STOPPED_RETRIED,
        blueprint.STOPPED_RESET,
        blueprint.RETRY_BLOCKED["waiting"][1],
    ],
)
def test_all_it_says_has_its_spanish(text):
    with override("es"):
        spanish = str(text)
    with override("en"):
        assert spanish != str(text)


def test_undoing_a_load_that_waited_removes_what_came_later_too(business):
    hub = business("a")
    load = load_template(hub)
    run_pass()

    assert listed(hub, "service.service") == SALON_SERVICES

    call(hub, "base.import.undo", id=load["id"])

    assert listed(hub, "service.service") == 0
    assert listed(hub, "service.category") == 0


def test_two_loads_waiting_for_one_app_bring_its_data_once(business):
    hub = business("a")
    first, second = load_template(hub), load_template(hub)

    run_pass()

    assert count(hub, "service", "Service") == SALON_SERVICES
    assert by_app(report_of(hub, first))["service"]["status"] == "applied"
    assert by_app(report_of(hub, second))["service"]["status"] == "already"


def test_an_app_loaded_at_once_does_not_wait_and_is_not_loaded_again(business):
    hub = business("a")
    turn_on(hub, "inventory")
    run_pass()

    load = load_template(hub, choose=("inventory", "service"))
    assert by_app(load)["inventory"]["status"] == "applied"
    assert by_app(load)["service"]["status"] == blueprint.WAITING
    run_pass()

    done = report_of(hub, load)
    assert count(hub, "inventory", "Product") == SALON_PRODUCTS
    assert by_app(done)["inventory"]["datasets"][1]["created"] == SALON_PRODUCTS
    assert done["rows"] == 1 + SALON_PRODUCTS + SALON_CATEGORIES + SALON_SERVICES


# ── Two businesses: a load of one never reaches the other (PLAN-DB §14.2) ───────────────────────────────────────


def test_a_load_that_waited_brings_its_data_to_its_own_business_and_never_opens_the_other(business):
    a, b = business("a"), business("b")
    loaded_a = load_template(a)
    loaded_b = load_template(b, RESTAURANT, ("inventory",))
    # B's turn has not come: only A is served in this pass.
    later = timezone.now() + dt.timedelta(hours=1)
    HubDue.objects.filter(hub_id=b.pk).update(due_at=later)

    with hubs.watched() as sent:
        run_pass()

    assert not [alias for alias in sent if b.id.hex in alias]
    assert count(a, "service", "Service") == SALON_SERVICES
    assert report_of(a, loaded_a)["status"] == "complete"
    assert by_app(report_of(b, loaded_b))["inventory"]["status"] == blueprint.WAITING
    assert "service_service" not in tables(b)
    assert "inventory_product" not in tables(a)

    run_pass(later + dt.timedelta(seconds=1))

    assert count(b, "inventory", "Product") == RESTAURANT_PRODUCTS
    assert "service_service" not in tables(b)
    assert "inventory_product" not in tables(a)
    with use_hub(fresh(a)):
        assert [str(load.pk) for load in ImportBatch.objects.all()] == [loaded_a["id"]]
    with use_hub(fresh(b)):
        assert [str(load.pk) for load in ImportBatch.objects.all()] == [loaded_b["id"]]


# ── A restart loses nothing ─────────────────────────────────────────────────────────────────────────────────────


class WorkerDied(BaseException):
    """Not an ``Exception``: nothing in the worker catches it, as nothing catches a killed process."""


def test_a_worker_that_dies_loading_leaves_it_all_to_do_and_a_later_worker_does_it_though_its_ring_was_lost(business):
    hub = business("a")
    load = load_template(hub)

    with mock.patch.object(blueprint, "apply", side_effect=WorkerDied), pytest.raises(WorkerDied):
        run_pass()

    # Nothing committed: the app did not go on without its data, and the load still waits.
    assert row(hub, "service").state == CREATING
    assert by_app(report_of(hub, load))["service"]["status"] == blueprint.WAITING

    # A new process, the hub's ring lost with it: the sweep finds it again.
    HubDue.objects.filter(hub_id=hub.pk).delete()
    now = timezone.now()
    worker._serve_hub(fresh(hub), now, active=True)
    run_pass(now + dt.timedelta(seconds=1))

    assert row(hub, "service").state == ON
    assert count(hub, "service", "Service") == SALON_SERVICES
    assert report_of(hub, load)["status"] == "complete"


# ── A failure is on the screen, and the load still comes ────────────────────────────────────────────────────────


def fail_the_schema():
    return mock.patch.object(worker.migrator, "ensure_schema", side_effect=RuntimeError("the schema broke"))


def test_an_app_that_cannot_be_set_up_says_so_and_its_data_loads_when_the_worker_manages_by_itself(business):
    hub = business("a")
    load = load_template(hub)

    with fail_the_schema():
        run_pass()

    assert row(hub, "service").state == FAILED
    failed = report_of(hub, load)
    assert by_app(failed)["service"]["status"] == blueprint.SETUP_FAILED
    assert by_app(failed)["service"]["reason"]
    assert (failed["status"], failed["retry"], failed["retry_blocked"]) == ("partial", True, "")
    assert count(hub, "base", "ImportBatch") == 1

    run_pass(timezone.now() + dt.timedelta(minutes=2))

    assert row(hub, "service").state == ON
    assert count(hub, "service", "Service") == SALON_SERVICES
    assert report_of(hub, load)["status"] == "complete"


def test_turning_on_again_an_app_that_failed_with_its_tables_made_loads_what_waited_at_once(business):
    hub = business("a")
    load = load_template(hub)
    # The tables got made, and the settle that follows them said they had not: an app on at once when turned on again.
    with mock.patch.object(services, "apps_created", return_value=frozenset()):
        run_pass()
    assert row(hub, "service").state == FAILED

    answer = turn_on(hub, "service")

    assert answer["state"] == ON
    assert count(hub, "service", "Service") == SALON_SERVICES
    assert report_of(hub, load)["status"] == "complete"


def test_a_load_is_not_retried_while_its_app_is_being_set_up(business):
    hub = business("a")
    load = load_template(hub)

    with pytest.raises(Conflict) as refused:
        call(hub, "base.blueprint.import", retry_of=load["id"])

    assert refused.value.code == "base.import_waiting"


def test_retrying_one_that_failed_tries_the_app_again_and_only_the_new_load_waits(business):
    hub = business("a")
    load = load_template(hub)
    with fail_the_schema():
        run_pass()
    assert report_of(hub, load)["retry"] is True

    again = call(hub, "base.blueprint.import", retry_of=load["id"])

    assert row(hub, "service").state == CREATING
    assert by_app(again)["service"]["status"] == blueprint.WAITING
    assert by_app(report_of(hub, load))["service"]["status"] == blueprint.INACTIVE
    assert by_app(report_of(hub, load))["service"]["reason"]

    run_pass(timezone.now() + dt.timedelta(minutes=2))

    assert count(hub, "service", "Service") == SALON_SERVICES
    assert by_app(report_of(hub, again))["service"]["status"] == "applied"
    assert by_app(report_of(hub, load))["service"]["status"] == blueprint.INACTIVE
    assert report_of(hub, load)["rows"] == 0


def test_a_load_that_breaks_turns_its_app_on_all_the_same_and_says_so_and_can_be_retried(business, caplog):
    hub = business("a")
    load = load_template(hub)

    with mock.patch.object(blueprint, "apply", side_effect=RuntimeError("the load broke")):
        run_pass()

    assert row(hub, "service").state == ON
    broken = report_of(hub, load)
    assert by_app(broken)["service"]["status"] == blueprint.FAILED
    assert by_app(broken)["service"]["reason"]
    assert (broken["status"], broken["retry"], broken["retry_blocked"]) == ("failed", True, "")
    assert "the load broke" in caplog.text

    again = call(hub, "base.blueprint.import", retry_of=load["id"])

    assert count(hub, "service", "Service") == SALON_SERVICES
    assert by_app(again)["service"]["status"] == "applied"


def test_a_load_broken_by_the_database_leaves_nothing_of_it_and_its_app_still_goes_on(business):
    """A real error of the database aborts the transaction unless a savepoint holds it: without one the app would never
    go on, the settle failing every time."""
    hub = business("a")
    load = load_template(hub)

    def half_done_then_refused(*args, **kwargs):
        ImportBatch.objects.create(name="half of it", source="catalog", purpose="template", status="partial")
        ImportBatch.objects.create(name=None, source="catalog", purpose="template", status="partial")

    with mock.patch.object(blueprint, "apply", side_effect=half_done_then_refused):
        run_pass()

    assert row(hub, "service").state == ON
    assert by_app(report_of(hub, load))["service"]["status"] == blueprint.FAILED
    assert count(hub, "base", "ImportBatch") == 1


def test_a_template_whose_version_changed_meanwhile_loads_nothing_and_says_why(business):
    hub = business("a")
    load = load_template(hub)
    seed = blueprint.template(SALON)
    newer = dataclasses.replace(seed, version=f"{seed.version}-newer")

    with mock.patch.object(blueprint, "template", return_value=newer):
        run_pass()
        gone = report_of(hub, load)

    assert row(hub, "service").state == ON
    assert count(hub, "service", "Service") == 0
    assert by_app(gone)["service"]["status"] == blueprint.INACTIVE
    assert by_app(gone)["service"]["reason"]
    assert gone["retry_blocked"] == "version_gone"


# ── What ends the wait ──────────────────────────────────────────────────────────────────────────────────────────


def test_an_app_turned_off_meanwhile_stops_the_wait_and_retrying_brings_it(business):
    hub = business("a")
    load = load_template(hub)

    turn_off(hub, "service")
    stopped = report_of(hub, load)

    assert by_app(stopped)["service"]["status"] == blueprint.INACTIVE
    assert by_app(stopped)["service"]["reason"]
    assert (stopped["status"], stopped["retry"]) == ("failed", True)
    run_pass()
    assert row(hub, "service").state == OFF
    assert "service_service" not in tables(hub)

    again = call(hub, "base.blueprint.import", retry_of=load["id"])
    assert by_app(again)["service"]["status"] == blueprint.WAITING
    run_pass()

    assert count(hub, "service", "Service") == SALON_SERVICES


def test_turning_off_one_app_only_stops_the_wait_for_that_app(business):
    hub = business("a")
    load = load_template(hub, choose=("service", "printing"))

    turn_off(hub, "service")

    stopped = report_of(hub, load)
    assert by_app(stopped)["service"]["status"] == blueprint.INACTIVE
    assert by_app(stopped)["printing"]["status"] == blueprint.WAITING
    assert stopped["retry"] is False


def test_a_load_undone_meanwhile_brings_nothing_later(business):
    hub = business("a")
    turn_on(hub, "inventory")
    run_pass()
    load = load_template(hub, choose=("inventory", "service"))

    call(hub, "base.import.undo", id=load["id"])
    run_pass()

    assert row(hub, "service").state == ON
    assert count(hub, "service", "Service") == 0
    assert listed(hub, "inventory.product") == 0
    assert by_app(report_of(hub, load))["service"]["status"] == blueprint.INACTIVE


def test_a_business_reset_meanwhile_brings_nothing_later(business):
    hub = business("a")
    load = load_template(hub)
    op = get("base.hub.reset_apply")

    with use_hub(fresh(hub)):
        op(internal(hub), op.input.model_validate({"apps": ["customer"]}))
    run_pass()

    assert row(hub, "service").state == ON
    assert count(hub, "service", "Service") == 0
    assert by_app(report_of(hub, load))["service"]["status"] == blueprint.INACTIVE


# ── A file ──────────────────────────────────────────────────────────────────────────────────────────────────────


def test_a_file_is_not_kept_so_it_does_not_wait_and_says_to_upload_it_again(business):
    hub = business("a")
    content = base64.b64encode(blueprint.write_zip(blueprint.template(SALON).bundle)).decode("ascii")

    load = call(hub, "base.blueprint.import", file_base64=content, apps=["service"])

    assert row(hub, "service").state == CREATING
    assert by_app(load)["service"]["status"] == blueprint.INACTIVE
    assert by_app(load)["service"]["reason"]
    assert load["retry_blocked"] == "file"
    run_pass()

    assert row(hub, "service").state == ON
    assert count(hub, "service", "Service") == 0
    assert by_app(report_of(hub, load))["service"]["status"] == blueprint.INACTIVE


# ── Only what the report needs is read ──────────────────────────────────────────────────────────────────────────


def test_a_settle_with_nothing_waiting_turns_on_its_app_and_writes_no_load(business):
    hub = business("a")
    turn_on(hub, "printing")

    run_pass()

    assert row(hub, "printing").state == ON
    assert count(hub, "base", "ImportBatch") == 0
    assert events_of(hub, events.BLUEPRINT_IMPORTED) == []


def test_only_the_loads_of_the_apps_that_went_on_load(business):
    hub = business("a")
    salon = load_template(hub)
    with use_hub(fresh(hub)):
        AppActivation.objects.filter(host=hub.slug, app="printing").update(state=CREATING)
    migrator.ensure_schema(fresh(hub), add=["printing"])
    op = get("base.app.activation_settle")

    with use_hub(fresh(hub)):
        op(internal(hub), op.input.model_validate({"apps": ["printing"], "outcome": "created", "error": ""}))

    assert row(hub, "printing").state == ON
    assert by_app(report_of(hub, salon))["service"]["status"] == blueprint.WAITING
    assert "service_service" not in tables(hub)
