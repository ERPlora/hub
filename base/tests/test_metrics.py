"""The worker's CloudWatch metrics (hub#488; PLAN-AWS §8; PLAN-DB §6 and §8).

Once a minute, in a thread of its own (the worker's tick never waits for it), the worker measures and publishes:

- ``ERPlora/Hubs``: ``HubsRequestedAgeSeconds`` (since when the oldest hub still being prepared waits),
  ``HubsFailed`` (how many failed) and ``DemosDropPending`` (since when the oldest demo that ended waits to be
  dropped), read from control's registry in one query (``control.queries.registry_health``);
- ``ERPlora/Fiscal``: ``OldestPendingAgeSeconds``, since when the oldest production record waits to reach the tax
  authority, asked to every app that keeps such a queue (``fiscal_pending_since`` on its ``LiveAppConfig``: VeriFactu)
  in phase 1's shared database and in each hub with its own database where the app is on, a time budget per pass and
  the hubs in turn, each one's last reading kept.

Every value carries the ``Environment`` dimension (prod, pre). A measure that fails is logged and missing from that
pass (its alarm treats missing data as breaching); CloudWatch refusing a namespace is logged and never stops the
worker. ``METRICS_ENABLED`` off (pre, local, the tests): nothing runs, said once. The DB tests use the real registry and
the session's two hub databases; CloudWatch is botocore's ``Stubber`` on a real client, or a fake that records calls.
"""

import datetime as dt
import logging
import threading

import boto3
import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from botocore.stub import Stubber
from django.db import connections
from django.utils import timezone

from apps.verifactu.models import Environment, Record
from apps.verifactu.tests.test_fiscal_backlog import record
from base import metrics, relay
from base.metrics import FISCAL_NAMESPACE, HUBS_NAMESPACE, Emitter, FiscalBacklog, Metric
from base.tenancy.context import use_hub, use_shared_database
from base.tenancy.tests import hubs
from control.models import Hub

NOW = dt.datetime(2026, 11, 1, 10, 0, tzinfo=dt.UTC)
DIMENSIONS = [{"Name": "Environment", "Value": "prod"}]


@pytest.fixture
def no_test_fallback(monkeypatch):
    """The metrics run in the worker's thread, which has no database context: each read opens its own."""
    from base.tenancy import context

    monkeypatch.setattr(context, "_test_fallback", None)


def never() -> threading.Event:
    return threading.Event()


def by_name(found: list[Metric]) -> dict[str, Metric]:
    return {metric.name: metric for metric in found}


# ── The registry's measures ─────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.usefixtures("no_test_fallback")
def test_with_every_hub_ready_the_registry_measures_zero():
    assert metrics.registry_metrics(timezone.now(), never()) == [
        Metric(HUBS_NAMESPACE, "HubsRequestedAgeSeconds", 0.0, "Seconds"),
        Metric(HUBS_NAMESPACE, "HubsFailed", 0.0, "Count"),
        Metric(HUBS_NAMESPACE, "DemosDropPending", 0.0, "Seconds"),
    ]


@pytest.mark.django_db
@pytest.mark.usefixtures("no_test_fallback")
def test_the_registry_measures_the_stuck_sign_up_the_failed_hubs_and_the_demo_left_to_drop():
    from base.tenancy.context import use_control

    now = timezone.now()
    with use_control():
        stuck = Hub.objects.create(slug="acme", status=Hub.Status.CREATING)
        Hub.objects.filter(pk=stuck.pk).update(created_at=now - dt.timedelta(minutes=11))
        Hub.objects.create(slug="broken", status=Hub.Status.FAILED)
        Hub.objects.create(
            slug="demo-x", status=Hub.Status.EXPIRED, is_demo=True, expires_at=now - dt.timedelta(minutes=40)
        )

    found = by_name(metrics.registry_metrics(now, never()))

    assert found["HubsRequestedAgeSeconds"].value == pytest.approx(660.0, abs=1)
    assert found["HubsFailed"].value == 1.0
    assert found["DemosDropPending"].value == pytest.approx(2400.0, abs=1)


def test_an_age_is_never_negative_nor_measured_when_nothing_waits():
    assert metrics.seconds_since(None, NOW) == 0.0
    assert metrics.seconds_since(NOW - dt.timedelta(seconds=90), NOW) == 90.0
    # A clock a little behind the database's: a wait just begun, never a negative age.
    assert metrics.seconds_since(NOW + dt.timedelta(seconds=2), NOW) == 0.0


# ── The fiscal backlog ──────────────────────────────────────────────────────────────────────────────────────────────

hub_db = pytest.mark.django_db(transaction=True, databases=hubs.HUB_DATABASES)


def pending(created: dt.datetime, **more) -> Record:
    return record(Record.Status.PENDING, created, **more)


def oldest_age(found: list[Metric]) -> float:
    (metric,) = found
    assert (metric.namespace, metric.name, metric.unit) == (FISCAL_NAMESPACE, "OldestPendingAgeSeconds", "Seconds")
    return metric.value


@hub_db
@pytest.mark.usefixtures("no_test_fallback")
def test_with_no_record_to_send_anywhere_the_backlog_is_zero(hub_a, hub_b):
    assert oldest_age(FiscalBacklog()(timezone.now(), never())) == 0.0


@hub_db
@pytest.mark.usefixtures("no_test_fallback")
def test_a_record_waiting_in_phase_1s_shared_database_is_measured(hub_a, hub_b):
    now = timezone.now()
    with use_shared_database():
        pending(now - dt.timedelta(minutes=8))

    assert oldest_age(FiscalBacklog()(now, never())) == pytest.approx(480.0, abs=1)


@hub_db
@pytest.mark.usefixtures("no_test_fallback")
def test_the_oldest_record_of_every_hub_with_its_own_database_is_measured(hub_a, hub_b):
    now = timezone.now()
    with use_hub(hub_a):
        pending(now - dt.timedelta(minutes=6))
    with use_hub(hub_b):
        pending(now - dt.timedelta(minutes=25))
    with use_shared_database():
        pending(now - dt.timedelta(minutes=1))

    assert oldest_age(FiscalBacklog()(now, never())) == pytest.approx(1500.0, abs=1)


@hub_db
@pytest.mark.usefixtures("no_test_fallback")
def test_a_record_of_the_aeats_test_environment_never_pages(hub_a, hub_b):
    now = timezone.now()
    with use_hub(hub_a):
        pending(now - dt.timedelta(hours=3), environment=Environment.TESTING)

    assert oldest_age(FiscalBacklog()(now, never())) == 0.0


@hub_db
@pytest.mark.usefixtures("no_test_fallback")
def test_a_hub_where_the_app_is_off_is_never_asked(hub_a, hub_b, monkeypatch):
    now = timezone.now()
    with use_hub(hub_a):
        pending(now - dt.timedelta(minutes=30))
    real = relay.active_apps
    monkeypatch.setattr(
        relay, "active_apps", lambda scope: real(scope) - {"verifactu"} if scope.key == hub_a.slug else real(scope)
    )

    assert oldest_age(FiscalBacklog()(now, never())) == 0.0


@hub_db
@pytest.mark.usefixtures("no_test_fallback")
def test_a_hub_still_being_prepared_is_never_entered(hub_a, hub_b):
    now = timezone.now()
    with use_hub(hub_a):
        pending(now - dt.timedelta(minutes=30))
    Hub.objects.filter(pk=hub_a.pk).update(status=Hub.Status.MIGRATING)

    assert oldest_age(FiscalBacklog()(now, never())) == 0.0


@hub_db
@pytest.mark.usefixtures("no_test_fallback")
def test_within_its_budget_the_hubs_are_read_in_turn_and_each_ones_last_reading_kept(hub_a, hub_b):
    """A budget of nothing reads one hub per pass: the first pass a, the next b; a's reading counts in both."""
    now = timezone.now()
    with use_hub(hub_a):
        pending(now - dt.timedelta(minutes=20))
    with use_hub(hub_b):
        pending(now - dt.timedelta(minutes=50))
    backlog = FiscalBacklog(budget=0.0)

    assert oldest_age(backlog(now, never())) == pytest.approx(1200.0, abs=1)
    assert oldest_age(backlog(now, never())) == pytest.approx(3000.0, abs=1)
    with use_hub(hub_b):
        Record.objects.update(status=Record.Status.ACCEPTED)
    # The third pass reads a again: b's last reading (50 min) still counts until b is read again.
    assert oldest_age(backlog(now, never())) == pytest.approx(3000.0, abs=1)
    assert oldest_age(backlog(now, never())) == pytest.approx(1200.0, abs=1)


@hub_db
@pytest.mark.usefixtures("no_test_fallback")
def test_a_hub_no_longer_served_is_forgotten(hub_a, hub_b):
    now = timezone.now()
    with use_hub(hub_b):
        pending(now - dt.timedelta(minutes=50))
    backlog = FiscalBacklog()
    assert oldest_age(backlog(now, never())) == pytest.approx(3000.0, abs=1)

    Hub.objects.filter(pk=hub_b.pk).update(status=Hub.Status.PURGED)

    assert oldest_age(backlog(now, never())) == 0.0


@hub_db
@pytest.mark.usefixtures("no_test_fallback")
def test_a_hub_that_cannot_be_read_keeps_its_last_reading_and_is_logged(hub_a, hub_b, monkeypatch, caplog):
    now = timezone.now()
    with use_hub(hub_a):
        pending(now - dt.timedelta(minutes=20))
    backlog = FiscalBacklog()
    assert oldest_age(backlog(now, never())) == pytest.approx(1200.0, abs=1)
    real = relay.active_apps

    def broken(scope):
        if scope.key == hub_a.slug:
            raise RuntimeError("database gone")
        return real(scope)

    monkeypatch.setattr(relay, "active_apps", broken)
    with caplog.at_level(logging.ERROR, logger="base.metrics"):
        assert oldest_age(backlog(now, never())) == pytest.approx(1200.0, abs=1)

    said = f"worker: the fiscal backlog of the hub {hub_a.slug} could not be read; its last reading stays."
    assert said in caplog.messages


@hub_db
@pytest.mark.usefixtures("no_test_fallback")
def test_each_hubs_connection_is_closed_once_read(hub_a, hub_b):
    FiscalBacklog()(timezone.now(), never())

    open_aliases = {connection.alias for connection in connections.all(initialized_only=True) if connection.connection}
    assert not open_aliases & {hubs.HUB_A_ALIAS, hubs.HUB_B_ALIAS}


@hub_db
@pytest.mark.usefixtures("no_test_fallback")
def test_a_stop_ends_the_pass_before_the_next_hub(hub_a, hub_b, monkeypatch):
    stop = threading.Event()
    stop.set()
    entered: list[str] = []
    real = relay.active_apps
    monkeypatch.setattr(relay, "active_apps", lambda scope: entered.append(scope.key) or real(scope))

    FiscalBacklog()(timezone.now(), stop)

    assert entered == []


@hub_db
@pytest.mark.usefixtures("no_test_fallback")
def test_a_shared_database_that_cannot_be_read_leaves_the_measure_out(hub_a, hub_b, monkeypatch):
    """Phase 1's shared database holds every business of prod today: a reading without it would hide them."""

    def broken(apps_on=None):
        raise RuntimeError("database gone")

    monkeypatch.setattr(metrics, "fiscal_pending_since", broken)

    with pytest.raises(RuntimeError):
        FiscalBacklog()(timezone.now(), never())


def test_every_app_that_keeps_a_fiscal_queue_is_asked_and_the_oldest_answer_wins(monkeypatch):
    class Queue:
        def __init__(self, label, since):
            self.label, self.since = label, since

        def fiscal_pending_since(self):
            return self.since

    class NoQueue:
        label = "sale"

    configs = [
        Queue("verifactu", NOW - dt.timedelta(minutes=3)),
        NoQueue(),
        Queue("ticketbai", NOW - dt.timedelta(minutes=9)),
        Queue("other", None),
    ]
    monkeypatch.setattr(metrics, "all_live_app_configs", lambda: configs)

    assert metrics.fiscal_pending_since() == NOW - dt.timedelta(minutes=9)
    assert metrics.fiscal_pending_since({"verifactu", "sale"}) == NOW - dt.timedelta(minutes=3)
    assert metrics.fiscal_pending_since({"sale"}) is None


# ── Publishing ──────────────────────────────────────────────────────────────────────────────────────────────────────


class FakeCloudWatch:
    """Records each ``put_metric_data``; raises the failures it is given, one per call."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.failures: list[Exception] = []

    def put_metric_data(self, **call) -> dict:
        self.calls.append(call)
        if self.failures:
            raise self.failures.pop(0)
        return {}


def denied(operation: str = "PutMetricData") -> ClientError:
    return ClientError({"Error": {"Code": "AccessDenied", "Message": "not authorized"}}, operation)


def hubs_measure(now, stop):
    return [
        Metric(HUBS_NAMESPACE, "HubsFailed", 2.0, "Count"),
        Metric(HUBS_NAMESPACE, "HubsRequestedAgeSeconds", 61.5, "Seconds"),
    ]


def fiscal_measure(now, stop):
    return [Metric(FISCAL_NAMESPACE, "OldestPendingAgeSeconds", 30.0, "Seconds")]


@pytest.fixture(autouse=True)
def prod(settings):
    settings.ERPLORA_ENVIRONMENT = "prod"
    settings.METRICS_ENABLED = True


@pytest.fixture
def released(monkeypatch) -> list[str]:
    """Each release of the thread's connections (``close_old_connections``)."""
    done: list[str] = []
    monkeypatch.setattr(metrics, "close_old_connections", lambda: done.append("closed"))
    return done


def datum(name: str, value: float, unit: str) -> dict:
    """One value as ``PutMetricData`` takes it, at NOW, with prod's dimension."""
    return {"MetricName": name, "Dimensions": DIMENSIONS, "Timestamp": NOW, "Value": value, "Unit": unit}


def test_each_namespace_goes_in_one_call_with_the_environment_dimension(released):
    client = boto3.client("cloudwatch", region_name="eu-west-1", aws_access_key_id="k", aws_secret_access_key="s")
    with Stubber(client) as stub:
        stub.add_response(
            "put_metric_data",
            {},
            {
                "Namespace": "ERPlora/Hubs",
                "MetricData": [
                    datum("HubsFailed", 2.0, "Count"),
                    datum("HubsRequestedAgeSeconds", 61.5, "Seconds"),
                ],
            },
        )
        stub.add_response(
            "put_metric_data",
            {},
            {
                "Namespace": "ERPlora/Fiscal",
                "MetricData": [
                    datum("OldestPendingAgeSeconds", 30.0, "Seconds")
                ],
            },
        )

        published = Emitter(never(), collectors=[hubs_measure, fiscal_measure], client=client).publish(NOW)

        stub.assert_no_pending_responses()
    assert published == 3


def test_the_environment_dimension_is_the_deployments(settings, released):
    settings.ERPLORA_ENVIRONMENT = "pre"
    client = FakeCloudWatch()

    Emitter(never(), collectors=[fiscal_measure], client=client).publish(NOW)

    assert client.calls[0]["MetricData"][0]["Dimensions"] == [{"Name": "Environment", "Value": "pre"}]


def test_a_measure_that_fails_is_logged_and_the_others_are_published(caplog, released):
    def broken(now, stop):
        raise RuntimeError("control is down")

    client = FakeCloudWatch()
    with caplog.at_level(logging.ERROR, logger="base.metrics"):
        published = Emitter(never(), collectors=[broken, fiscal_measure], client=client).publish(NOW)

    assert published == 1
    assert [call["Namespace"] for call in client.calls] == ["ERPlora/Fiscal"]
    assert "worker: the measure broken failed; its metrics are missing from this pass." in caplog.messages


@pytest.mark.parametrize(
    "failure", [denied(), EndpointConnectionError(endpoint_url="https://monitoring")], ids=["denied", "unreachable"]
)
def test_cloudwatch_refusing_a_namespace_is_logged_and_the_next_one_is_still_sent(caplog, released, failure):
    client = FakeCloudWatch()
    client.failures = [failure]

    with caplog.at_level(logging.ERROR, logger="base.metrics"):
        published = Emitter(never(), collectors=[hubs_measure, fiscal_measure], client=client).publish(NOW)

    assert [call["Namespace"] for call in client.calls] == ["ERPlora/Hubs", "ERPlora/Fiscal"]
    assert published == 1
    said = "worker: CloudWatch did not take the ERPlora/Hubs metrics; the next pass sends them again."
    assert said in caplog.messages


def test_the_threads_connections_are_released_after_each_measure(released):
    Emitter(never(), collectors=[hubs_measure, fiscal_measure], client=FakeCloudWatch()).publish(NOW)

    assert released == ["closed", "closed"]


def test_the_cloudwatch_client_is_the_tasks_region_with_short_timeouts(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "eu-south-2")
    client = metrics.cloudwatch_client()
    assert client.meta.region_name == "eu-south-2"
    assert (client.meta.config.connect_timeout, client.meta.config.read_timeout) == (5, 10)

    monkeypatch.delenv("AWS_REGION")
    assert metrics.cloudwatch_client().meta.region_name == "eu-west-1"


def test_the_measures_are_the_registrys_and_the_fiscal_backlog():
    collectors = metrics.default_collectors()

    assert collectors[0] is metrics.registry_metrics
    assert isinstance(collectors[1], FiscalBacklog)
    assert len(collectors) == 2


# ── When a pass starts ──────────────────────────────────────────────────────────────────────────────────────────


class FakeRunner:
    """Stands in for the worker's ``Background("metrics")``: records each piece it is given, runs none of them, and
    says it is busy when told."""

    def __init__(self) -> None:
        self.pieces: list = []
        self.busy = False

    def start(self, piece) -> bool:
        if self.busy:
            return False
        self.pieces.append(piece)
        return True


def test_on_a_pass_starts_at_once_then_once_a_minute_of_the_workers_clock(released):
    client = FakeCloudWatch()
    emitter = Emitter(never(), collectors=[fiscal_measure], client=client)
    runner = FakeRunner()

    started = [emitter.start_due(NOW + dt.timedelta(seconds=second), runner) for second in (0, 5, 55, 60, 65, 125)]

    assert started == [True, False, False, True, False, True]
    for piece in runner.pieces:
        piece()
    assert [call["MetricData"][0]["Timestamp"] for call in client.calls] == [
        NOW,
        NOW + dt.timedelta(seconds=60),
        NOW + dt.timedelta(seconds=125),
    ]


def test_a_pass_still_running_is_not_started_again_and_the_next_tick_tries(released):
    emitter = Emitter(never(), collectors=[fiscal_measure], client=FakeCloudWatch())
    runner = FakeRunner()
    assert emitter.start_due(NOW, runner) is True

    runner.busy = True
    assert emitter.start_due(NOW + dt.timedelta(seconds=60), runner) is False
    runner.busy = False

    assert emitter.start_due(NOW + dt.timedelta(seconds=65), runner) is True
    assert len(runner.pieces) == 2


def test_off_no_pass_ever_starts_and_it_is_said_once(settings, caplog, monkeypatch):
    settings.METRICS_ENABLED = False
    monkeypatch.setattr(metrics, "default_collectors", lambda: pytest.fail("no measure is even built while off"))
    runner = FakeRunner()

    with caplog.at_level(logging.INFO, logger="base.metrics"):
        emitter = metrics.emitter(never())
        started = [emitter.start_due(NOW + dt.timedelta(minutes=minute), runner) for minute in range(3)]

    assert started == [False, False, False]
    assert runner.pieces == []
    assert caplog.messages == ["worker: CloudWatch metrics are off (METRICS_ENABLED): nothing is published."]


def test_on_the_worker_gets_the_default_measures_on_its_stop_request(monkeypatch):
    stop = threading.Event()
    monkeypatch.setattr(metrics, "default_collectors", lambda: ["registry", "fiscal"])

    emitter = metrics.emitter(stop)

    assert (emitter.enabled, emitter.collectors, emitter.stop) == (True, ["registry", "fiscal"], stop)
