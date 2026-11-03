"""The outbox relay, run by the worker on every tick (PLAN-HUB «Eventos entre módulos»; round 2026-10-20).

A port of the old Hub's ``crates/runtime/src/outbox.rs``. A command records its events in the outbox in its own
transaction (``live.outbox.record_event``); the relay hands each one to the reactions of the apps that listen to
it, the ``REACTIONS`` of their ``events.py`` (``"*"``: every event of the other apps):

- **taken**: an event nobody took yet gets one delivery per app that is on and listens to it, and its
  ``delivered_at``, in one transaction (``base.services.relay_take_events``); an app turned on later never
  receives what came before. An app is on unless it is a paid one its business has no right to or one the
  business turned off (``active_apps``: ``base.entitlement`` and ``base.activation``; ``base.session.me`` says the
  same);
- **delivered**: each delivery runs its app's reaction as the system, in the scope of the hub that recorded the
  event (the reaction's own notice goes to that hub's channel after the COMMIT), and is marked in the same
  transaction, so an app never gets an event twice (``relay_deliver_next``); the events a reaction records are
  taken in it, one level deeper, and past ``MAX_EVENT_DEPTH`` they are not delivered; what a reaction leaves for
  after its COMMIT that waits on the network (a call to another system) goes through ``base.outbound``, in a thread
  of the worker's own, so it never holds the next delivery, of this hub or of another;
- **failed**: a reaction that raises has its writes undone and waits ``backoff`` (2, 4, 8… s, an hour at most);
  after ``MAX_ATTEMPTS`` it is given up (``dead``), logged with the event, and the other deliveries go on.

Both steps claim their rows with ``SKIP LOCKED``: the old worker and the new one overlap on a deploy. Every
transaction releases its connection, so the worker never idles holding one. The events recorded before the relay
existed were taken without a delivery by its migration (``base/migrations/0006_event_delivery.py``): the backlog
of phase 1 is never applied. The worker runs it in each hub with its own database, under ``use_hub``
(``base.worker._hubs``; review of hub#471), and on control for control's own events (``of_hubs=False``: the registry's
and the demos', which no app hears); since S5 what a business of phase 1 recorded in control before its cut is never
taken there (its cut copies its own events into its database, ``base.tenancy.cut``).
"""

import datetime as dt
from dataclasses import dataclass
from functools import cache
from importlib import import_module
from types import ModuleType

from django.db import close_old_connections
from django.utils.module_loading import module_has_submodule
from live.context import Scope
from live.live_registry import ALL_EVENTS
from live.meta import all_live_app_configs
from live.models import OutboxEvent

from base import activation, entitlement, services
from base.tenancy.context import HUB_SCOPE_KIND

#: How deep a chain of events may go (an event, the event its reaction records, …): the old Hub's.
MAX_EVENT_DEPTH = 16
#: Attempts of a reaction before it is given up: the old Hub's.
MAX_ATTEMPTS = 8
#: The longest wait between two attempts.
BACKOFF_MAX_SECONDS = 3600
#: At most this many events taken, and deliveries run, a tick: the rest waits for the next one.
TAKE_PER_TICK = 500
DELIVER_PER_TICK = 200


@dataclass(frozen=True)
class RelayPass:
    """What a pass of the relay did: events taken, deliveries done and deliveries that failed."""

    taken: int
    delivered: int
    failed: int


def active_apps(scope: Scope) -> frozenset[str]:
    """The apps that are on in ``scope``: every installed app of ours but those its business has no right to
    (``base.entitlement``: a paid module without it in the SaaS's photo) and those it turned off (``base.activation``)."""
    left_out = entitlement.blocked_apps(scope) | activation.off_apps(scope)
    return frozenset(config.label for config in all_live_app_configs() if config.label not in left_out)


@cache
def _events_modules() -> dict[str, ModuleType]:
    """The ``events.py`` of every app of ours that reacts to some event, by app label."""
    modules: dict[str, ModuleType] = {}
    for config in all_live_app_configs():
        if module_has_submodule(config.module, "events"):
            module = import_module(f"{config.name}.events")
            if getattr(module, "REACTIONS", None):
                modules[config.label] = module
    return modules


def listeners(event: OutboxEvent) -> list[str]:
    """The apps on in the event's scope that react to it; ``"*"`` hears every event but its own app's. An event of no
    hub (the registry's and the demos', in control's outbox) is heard by none: an app's reaction is a hub's work, and
    such an event has no hub to run it in (verification of hub#471 in pre: Flows failed on ``base.demo.created``)."""
    if event.scope_kind != HUB_SCOPE_KIND:
        return []
    on = active_apps(Scope(event.scope_kind, event.scope_key))
    source = event.name.split(".", 1)[0]
    return [
        label
        for label, module in sorted(_events_modules().items())
        if label in on
        and (event.name in module.REACTIONS or (ALL_EVENTS in module.REACTIONS and label != source))
    ]


def deliver(app_label: str, event: OutboxEvent) -> object:
    """Hand ``event`` to the reaction of ``app_label``, in the event's scope: its ``deliver(event)`` if the app
    needs the whole event (its id, its actor), else ``react(scope, name, payload)``."""
    module = _events_modules()[app_label]
    whole = getattr(module, "deliver", None)
    if whole is not None:
        return whole(event)
    return module.react(Scope(event.scope_kind, event.scope_key), event.name, event.payload)


def backoff(attempts: int) -> dt.timedelta:
    """The wait after the ``attempts``-th failed attempt: 2 s, doubling, an hour at most."""
    return dt.timedelta(seconds=min(2**attempts, BACKOFF_MAX_SECONDS))


def run(now: dt.datetime, *, of_hubs: bool = True) -> RelayPass:
    """Take the new events, then run the deliveries due at ``now``, one transaction each. ``of_hubs=False`` (control's
    outbox): only the events of no hub, never a business's."""
    taken = services.relay_take_events(
        now, listeners=listeners, limit=TAKE_PER_TICK, max_depth=MAX_EVENT_DEPTH, of_hubs=of_hubs
    )
    close_old_connections()
    delivered = failed = 0
    for _ in range(DELIVER_PER_TICK):
        outcome = services.relay_deliver_next(
            now,
            deliver=deliver,
            listeners=listeners,
            max_depth=MAX_EVENT_DEPTH,
            max_attempts=MAX_ATTEMPTS,
            backoff=backoff,
            of_hubs=of_hubs,
        )
        close_old_connections()
        if outcome is None:
            break
        if outcome[1]:
            delivered += 1
        else:
            failed += 1
    return RelayPass(taken=taken, delivered=delivered, failed=failed)
