"""The worker's visits to the businesses with a database of their own.

On every tick of the worker (``base.worker``), :meth:`HubVisits.serve` enters the database of each business it serves
(``use_hub``), one at a time and for ``HUB_PASS_SECONDS`` at most, only when there is something to do there. Which they
are it reads on control at the worker's passes there (``look``, ``base.control_pace``; ready ones and those that left
but keep their database, whose records still to send must reach the AEAT; never one being made, dropped, moved or
restored: ``base.services.provisioning.hubs_to_serve``), and keeps between two. Something to do:

- its channel was notified: an operation of the business committed (``live.outbox.notify`` after its COMMIT), heard on
  the worker's own LISTEN (``base.hub_listener``, shared with control's steps: ``base.control_pace.Ear``);
- the next run of a task of one of its apps that are on, or the next try of a delivery, came
  (``base.queries.due_work``, read when its last visit ended);
- ``LOOK_SECONDS`` passed since its last visit: the look that finds what a lost notice, or a LISTEN down, did not say;
- or this process never visited it.

A visit writes the business's schedule the first time in the process (``scheduler.sync``), takes its new events
(``relay.take``), runs its deliveries due when it took some or one is due (``relay.deliver_due``) and its tasks due,
those of its apps that are on, on its own scope and as the system (``scheduler.run_due``: a task of an app off is not
even claimed), and, at the sweep's pace (``SWEEP_ACTIVE`` for a business visited in the last ``ACTIVE_WINDOW``, else
``SWEEP_ALL``), rings again a ready business with apps still to set up whose ring was lost. Every claim is
``SKIP LOCKED`` and marked in its own transaction, so two workers at once (a deploy) never deliver nor run the same
thing twice. A visit that fails is logged and tried again at the next pass; its connections are released either way.
"""

import datetime as dt
import logging
import time
from dataclasses import dataclass

from django.db import close_old_connections
from live.context import Scope

from base import apps_on, queries, relay, scheduler, services
from base.hub_listener import Listener
from base.tenancy.connections import close_hub_aliases
from base.tenancy.context import use_control, use_hub
from control.models import Hub

logger = logging.getLogger(__name__)

#: How long the visits of a pass may go on; the next pass goes on with the next business due.
HUB_PASS_SECONDS = 3.0
#: The longest a business served goes without a visit: what covers a notice lost.
LOOK_SECONDS = 60
#: How often a visit looks into a business for apps to set up whose ring was lost (between a COMMIT and its ring, or
#: ended by another pass): an active one (a visit in the last 7 days) every 10 minutes, any other once a day.
SWEEP_ACTIVE = dt.timedelta(minutes=10)
SWEEP_ALL = dt.timedelta(days=1)
ACTIVE_WINDOW = dt.timedelta(days=7)


def _came(at: dt.datetime | None, now: dt.datetime) -> bool:
    return at is not None and at <= now


@dataclass(frozen=True)
class _Known:
    """What the last visit to a business left known: when it was, and what comes next there."""

    visited_at: dt.datetime
    task_at: dt.datetime | None
    delivery_at: dt.datetime | None

    def due(self, now: dt.datetime) -> bool:
        looked_long_ago = now - self.visited_at >= dt.timedelta(seconds=LOOK_SECONDS)
        return looked_long_ago or _came(self.task_at, now) or _came(self.delivery_at, now)


class HubVisits:
    """The visits of one worker process: what it knows of each business, and its LISTEN on their channels."""

    def __init__(self, listener: Listener | None = None) -> None:
        self._ear = Listener() if listener is None else listener
        self._hubs: list[Hub] | None = None
        self._active: frozenset[str] = frozenset()
        self._known: dict = {}
        self._heard: set = set()
        self._swept: dict = {}
        self._next_hub = None

    def serve(self, now: dt.datetime, *, look: bool = True) -> None:
        """Visit, at ``now``, the businesses served that have something to do; ``look``: read again on control which
        they are, else the ones read last. A failure to read them is logged and the next tick tries again."""
        if (look or self._hubs is None) and not self._read(now):
            return
        self._hear(self._hubs)
        started = time.monotonic()
        for hub in self._due(self._hubs, now):
            self._visit(hub, now, active=hub.slug in self._active)
            self._next_hub = hub.pk
            if time.monotonic() - started > HUB_PASS_SECONDS:
                break

    def close(self) -> None:
        self._ear.close()

    def _read(self, now: dt.datetime) -> bool:
        try:
            with use_control():
                hubs = services.provisioning.hubs_to_serve(now)
                active = services.activation.hubs_visited_since((now - ACTIVE_WINDOW).date()) if hubs else frozenset()
        except Exception:
            logger.exception("worker: the hubs to serve could not be read; the next tick tries again.")
            close_old_connections()
            return False
        self._hubs, self._active = hubs, active
        return True

    def _hear(self, hubs: list[Hub]) -> None:
        channels = {Scope("host", hub.slug).channel: hub.pk for hub in hubs}
        heard = self._ear.heard(channels)
        self._heard |= set(channels.values()) if heard is None else {channels[channel] for channel in heard}

    def _due(self, hubs: list[Hub], now: dt.datetime) -> list[Hub]:
        """The businesses to visit, by id from the one after the last visited: every one gets its turn."""
        start = next((index for index, hub in enumerate(hubs) if self._next_hub is not None and hub.pk > self._next_hub), 0)
        return [hub for hub in hubs[start:] + hubs[:start] if self._wanted(hub.pk, now)]

    def _wanted(self, hub_id, now: dt.datetime) -> bool:
        known = self._known.get(hub_id)
        return known is None or hub_id in self._heard or known.due(now)

    def _visit(self, hub: Hub, now: dt.datetime, *, active: bool = False) -> None:
        self._heard.discard(hub.pk)
        try:
            with use_hub(hub):
                self._known[hub.pk] = self._work(hub, now, self._known.get(hub.pk), active)
        except Exception:
            self._heard.add(hub.pk)
            logger.exception("worker: the hub %s failed; the next tick tries it again.", hub.slug)
        finally:
            close_hub_aliases(hub)
            close_old_connections()

    def _work(self, hub: Hub, now: dt.datetime, known: _Known | None, active: bool) -> _Known:
        scope = Scope("host", hub.slug)
        if known is None:
            scheduler.sync(now)
        apps = apps_on.active_apps(scope)
        taken = relay.take(now)
        if taken >= relay.TAKE_PER_TICK:
            self._heard.add(hub.pk)  # more may be waiting: the next pass takes them
        if taken or known is None or _came(known.delivery_at, now):
            relay.deliver_due(now)
        if known is None or _came(known.task_at, now):
            scheduler.run_due(now, scope=scope, active=apps)
        self._sweep(hub, now, active)
        due = queries.due_work.next_due(apps)
        return _Known(visited_at=now, task_at=due.task_at, delivery_at=due.delivery_at)

    def _sweep(self, hub: Hub, now: dt.datetime, active: bool) -> None:
        """At the sweep's pace, ring again a ready business with apps still to set up (a ring lost)."""
        last = self._swept.get(hub.pk)
        if hub.status != Hub.Status.READY or (last is not None and now - last < (SWEEP_ACTIVE if active else SWEEP_ALL)):
            return
        self._swept[hub.pk] = now
        pending = queries.apps.activation_next_at(hub.slug)
        if pending is not None:
            services.activation.ring_activations(hub, pending)
