"""The worker's CloudWatch metrics (hub#488; PLAN-AWS §8 «Observabilidad mínima»; PLAN-DB §6 and §8).

Once a minute of its clock, in a thread of its own (the worker's ``Background("metrics")``, ``worker-metrics``: the tick
never waits for it), the worker measures and publishes with ``PutMetricData``, every value with the ``Environment``
dimension (``ERPLORA_ENVIRONMENT``):

- ``ERPlora/Hubs`` (:func:`registry_metrics`, control's registry in one query): ``HubsRequestedAgeSeconds``, since when
  the oldest hub still being prepared waits (requested, creating, migrating, seeding, or failed and retried);
  ``HubsFailed``, how many failed; ``DemosDropPending``, since when the oldest demo that ended waits to be dropped;
- ``ERPlora/Fiscal`` (:class:`FiscalBacklog`): ``OldestPendingAgeSeconds``, since when the oldest production record
  waits to reach the tax authority. The queue is the records themselves (PLAN-DB §8, «la cola son los propios
  registros»), so every app that keeps one answers ``fiscal_pending_since()`` on its ``LiveAppConfig`` (VeriFactu),
  in phase 1's shared database and in each hub with its own database where the app is on.

What is measured is the list :func:`default_collectors` gives: one more measure is one more function there, taking the
time and the stop request and giving its :class:`Metric` s. A measure that fails is logged and missing from that pass,
so its alarm (``treat_missing_data = "breaching"``, aws ``stacks/prod/alarms.tf``) also speaks for a blind worker;
CloudWatch refusing a namespace is logged at ERROR and sent again the next pass; nothing stops the worker.

Only where ``METRICS_ENABLED`` is on (prod's worker, whose task role may call ``PutMetricData`` on these two
namespaces): pre has no such permission, nor local development or the tests, and there nothing runs (said once).
"""

import datetime as dt
import logging
import os
import threading
import time
from collections.abc import Callable, Collection
from dataclasses import dataclass
from functools import partial

from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.db import close_old_connections
from live.context import Scope
from live.meta import all_live_app_configs

from base import relay, services
from base.tenancy.connections import close_hub_aliases
from base.tenancy.context import use_control, use_hub, use_shared_database
from control.queries import registry_health

logger = logging.getLogger(__name__)

HUBS_NAMESPACE = "ERPlora/Hubs"
FISCAL_NAMESPACE = "ERPlora/Fiscal"
#: How often the worker publishes; the alarms read 5-minute periods.
INTERVAL_SECONDS = 60.0
#: How long one pass may read the hubs with their own database for the fiscal backlog; the next pass goes on after
#: the last hub read, each hub's last reading kept meanwhile.
FISCAL_PASS_SECONDS = 20.0
#: The region when the task does not say it (the platform's, PLAN-AWS).
DEFAULT_REGION = "eu-west-1"
#: The ``Scope`` kind of a business's hub (``base.worker._serve_hub``).
HUB_SCOPE_KIND = "host"


@dataclass(frozen=True)
class Metric:
    """One value to publish: its namespace, its name, the value and its CloudWatch unit (``Seconds``, ``Count``)."""

    namespace: str
    name: str
    value: float
    unit: str


#: A measure: given the time and the worker's stop request, its metrics.
Collector = Callable[[dt.datetime, threading.Event], list[Metric]]


def seconds_since(moment: dt.datetime | None, now: dt.datetime) -> float:
    """How long ``moment`` is before ``now``, in seconds: 0 when nothing waits, never negative (a clock a little behind
    the database's)."""
    if moment is None:
        return 0.0
    return max(0.0, (now - moment).total_seconds())


def registry_metrics(now: dt.datetime, stop: threading.Event) -> list[Metric]:
    """``ERPlora/Hubs`` from control's registry (``control.queries.registry_health``), on control."""
    with use_control():
        health = registry_health(now)
    return [
        Metric(HUBS_NAMESPACE, "HubsRequestedAgeSeconds", seconds_since(health.oldest_preparing_since, now), "Seconds"),
        Metric(HUBS_NAMESPACE, "HubsFailed", float(health.failed), "Count"),
        Metric(HUBS_NAMESPACE, "DemosDropPending", seconds_since(health.oldest_ended_demo_since, now), "Seconds"),
    ]


def fiscal_pending_since(apps_on: Collection[str] | None = None) -> dt.datetime | None:
    """Since when the oldest fiscal record of the database of the active context waits, asked to every app that keeps
    a fiscal queue (``fiscal_pending_since`` on its ``LiveAppConfig``), only those in ``apps_on`` when given (an app
    that is off in a hub may have no tables there); ``None`` when none waits."""
    found = []
    for config in all_live_app_configs():
        ask = getattr(config, "fiscal_pending_since", None)
        if ask is None or (apps_on is not None and config.label not in apps_on):
            continue
        since = ask()
        if since is not None:
            found.append(since)
    return min(found, default=None)


class FiscalBacklog:
    """``ERPlora/Fiscal`` ``OldestPendingAgeSeconds``: the oldest fiscal record still to send, of every business.

    Phase 1's shared database (every hub with ``db_name=""``, all of prod's today) is read on every pass, all its
    hubs at once: a pass that cannot read it fails, never hiding them. The hubs with their own database the worker
    serves (``base.services.hubs_to_serve``: ready, or a business that left whose records must still reach the tax
    authority) are read in turn, each in its database where the app is on, for ``budget`` seconds a pass; each one's
    last reading is kept until it is read again, and forgotten when it is no longer served. A hub that cannot be read
    is logged and keeps its last reading. A stop request ends the pass before the next hub.
    """

    def __init__(self, budget: float = FISCAL_PASS_SECONDS) -> None:
        self.budget = budget
        self._since: dict = {}
        self._last = None

    def __call__(self, now: dt.datetime, stop: threading.Event) -> list[Metric]:
        with use_shared_database():
            shared = fiscal_pending_since()
        self._read_hubs(now, stop)
        found = [since for since in (shared, *self._since.values()) if since is not None]
        oldest = min(found, default=None)
        return [Metric(FISCAL_NAMESPACE, "OldestPendingAgeSeconds", seconds_since(oldest, now), "Seconds")]

    def _read_hubs(self, now: dt.datetime, stop: threading.Event) -> None:
        with use_control():
            hubs = services.hubs_to_serve(now)
        served = {hub.pk for hub in hubs}
        for gone in set(self._since) - served:
            del self._since[gone]
        start = next((index for index, hub in enumerate(hubs) if self._last is not None and hub.pk > self._last), 0)
        started = time.monotonic()
        for read, hub in enumerate(hubs[start:] + hubs[:start]):
            if stop.is_set() or (read and time.monotonic() - started > self.budget):
                break
            self._read(hub)
            self._last = hub.pk

    def _read(self, hub) -> None:
        try:
            with use_hub(hub):
                self._since[hub.pk] = fiscal_pending_since(relay.active_apps(Scope(HUB_SCOPE_KIND, hub.slug)))
        except Exception:
            logger.exception("worker: the fiscal backlog of the hub %s could not be read; its last reading stays.", hub.slug)
        finally:
            close_hub_aliases(hub)


def default_collectors() -> list[Collector]:
    """What each pass measures: the registry's metrics and the fiscal backlog."""
    return [registry_metrics, FiscalBacklog()]


def cloudwatch_client():
    """CloudWatch in the task's region with the task role's credentials, failing within seconds when unreachable."""
    import boto3
    from botocore.config import Config

    return boto3.client(
        "cloudwatch",
        region_name=os.environ.get("AWS_REGION") or DEFAULT_REGION,
        config=Config(connect_timeout=5, read_timeout=10, retries={"max_attempts": 3, "mode": "standard"}),
    )


def _name(collector: Collector) -> str:
    return getattr(collector, "__name__", type(collector).__name__)


class Emitter:
    """Measures and publishes, one pass at a time in the worker's ``Background("metrics")`` thread (``base.worker``),
    once every ``interval`` seconds of the worker's clock; off (``METRICS_ENABLED``), it never starts a pass."""

    def __init__(
        self,
        stop: threading.Event,
        *,
        enabled: bool = True,
        collectors: list[Collector] | None = None,
        client=None,
        interval: float = INTERVAL_SECONDS,
    ) -> None:
        self.stop = stop
        self.enabled = enabled
        self.collectors = (default_collectors() if enabled else []) if collectors is None else collectors
        self.interval = interval
        self._client = client
        self._next: dt.datetime | None = None

    def start_due(self, now: dt.datetime, runner) -> bool:
        """Start a pass at ``now`` in ``runner`` (``base.worker.Background``) when on, at once and then once
        ``interval`` passed since the last one started; whether it started. A pass still running is not started again:
        the next tick tries."""
        if not self.enabled or (self._next is not None and now < self._next):
            return False
        if not runner.start(partial(self.publish, now)):
            return False
        self._next = now + dt.timedelta(seconds=self.interval)
        return True

    def publish(self, now: dt.datetime) -> int:
        """Measure everything at ``now`` and send each namespace in one ``PutMetricData``; how many values went out."""
        by_namespace: dict[str, list[dict]] = {}
        dimensions = [{"Name": "Environment", "Value": settings.ERPLORA_ENVIRONMENT}]
        for collect in self.collectors:
            try:
                measured = collect(now, self.stop)
            except Exception:
                logger.exception("worker: the measure %s failed; its metrics are missing from this pass.", _name(collect))
                continue
            finally:
                # A measure's connections (control's, the shared database's) are not handed to the next one broken.
                close_old_connections()
            for metric in measured:
                by_namespace.setdefault(metric.namespace, []).append(
                    {
                        "MetricName": metric.name,
                        "Dimensions": dimensions,
                        "Timestamp": now,
                        "Value": metric.value,
                        "Unit": metric.unit,
                    }
                )
        published = 0
        for namespace, data in by_namespace.items():
            try:
                self._cloudwatch().put_metric_data(Namespace=namespace, MetricData=data)
            except (BotoCoreError, ClientError):
                logger.exception("worker: CloudWatch did not take the %s metrics; the next pass sends them again.", namespace)
            else:
                published += len(data)
        logger.debug("worker: published %d metric(s).", published)
        return published

    def _cloudwatch(self):
        if self._client is None:
            self._client = cloudwatch_client()
        return self._client


def emitter(stop: threading.Event) -> Emitter:
    """The worker's emitter: on with ``METRICS_ENABLED``; off, one line says so and it never starts a pass."""
    if not settings.METRICS_ENABLED:
        logger.info("worker: CloudWatch metrics are off (METRICS_ENABLED): nothing is published.")
        return Emitter(stop, enabled=False)
    return Emitter(stop)
