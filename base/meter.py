"""What each business does during the day, counted in the memory of every process that serves it and written to control
once a minute (BASE-F40; PLAN-HUB §66 and its correction).

Four figures, each in the UTC day of its moment:

- :func:`count_request`: the requests a business served (``base.middleware.HubDatabaseMiddleware``; never a static file,
  a health probe, ``/internal`` or the platform's host);
- :func:`note_peak`: the most transactions it had at once in one process, which is how the plan's limit is applied
  (``base.tenancy.limits``). Reading ``pg_stat_activity`` from time to time would see almost nothing, because a
  transaction lasts milliseconds: the false zero the screen must not paint;
- :func:`count_busy`: the requests that found no room (503 ``base.hub_busy``, ``base.tenancy.limits``);
- :func:`note_seen`: who has activity there (``base.operations.HubContextBuilder``: people, never a visitor of the public
  web nor an API key).

Counting is a lock and a dictionary: nothing here reaches the network, so no request waits for it and a busy or absent
control database never reaches one. A thread (:func:`start`, once per process) writes the deltas every
:data:`INTERVAL_SECONDS` and at exit (``services.activity_recorded``, ``services.people_seen``): what could not be written
stays for the next pass, and a hub that went away meanwhile is forgotten without stopping the others.

Only a process that serves requests counts (``config/asgi.py`` starts it, unless ``METER_ENABLED`` is off, as in the
tests). The worker never does, on purpose: a pass of its own that finds its hub busy is nobody's error on a screen, and
it must not tell the owner to upgrade. Not Valkey: it may lose what it holds, and in this project it is only a cache.
"""

import atexit
import datetime as dt
import logging
import threading
import uuid
from dataclasses import dataclass
from dataclasses import field as dataclass_field

from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

logger = logging.getLogger(__name__)

#: How often the thread writes what the process counted.
INTERVAL_SECONDS = 60


@dataclass
class _Activity:
    """What a hub did on a day in this process since the last pass."""

    requests: int = 0
    peak: int = 0
    busy: int = 0


@dataclass(frozen=True)
class Unflushed:
    """What this process counted of a hub today and has not written yet: a reading adds it to control's."""

    requests: int = 0
    peak: int = 0
    busy: int = 0
    people: frozenset[str] = dataclass_field(default_factory=frozenset)


#: Guards the two dictionaries below; held for a dictionary's update, never around anything that may wait.
_lock = threading.Lock()
#: One pass at a time: the thread's and the one at exit.
_flushing = threading.Lock()
_recording = False
_started = False
_activity: dict[tuple[uuid.UUID, dt.date], _Activity] = {}
#: ``(host, day, person)`` → when they were last seen.
_seen: dict[tuple[str, dt.date, str], dt.datetime] = {}


def _utc_now() -> dt.datetime:
    return timezone.now().astimezone(dt.UTC)


def _today_s(hub_id: uuid.UUID) -> _Activity:
    return _activity.setdefault((hub_id, _utc_now().date()), _Activity())


def count_request(hub_id: uuid.UUID) -> None:
    """A request of the hub was served."""
    if not _recording:
        return
    with _lock:
        _today_s(hub_id).requests += 1


def note_peak(hub_id: uuid.UUID, in_use: int) -> None:
    """The hub has ``in_use`` transactions at once in this process."""
    if not _recording:
        return
    with _lock:
        activity = _today_s(hub_id)
        activity.peak = max(activity.peak, in_use)


def count_busy(hub_id: uuid.UUID) -> None:
    """A transaction of the hub found no room."""
    if not _recording:
        return
    with _lock:
        _today_s(hub_id).busy += 1


def note_seen(host: str, saas_user_id: str) -> None:
    """The person has activity in ``host`` now."""
    if not _recording:
        return
    now = _utc_now()
    with _lock:
        _seen[(host, now.date(), saas_user_id)] = now


def unflushed(hub_id: uuid.UUID, host: str) -> Unflushed:
    """What this process counted of the hub today and is still to write."""
    today = _utc_now().date()
    with _lock:
        activity = _activity.get((hub_id, today), _Activity())
        people = frozenset(person for (place, day, person) in _seen if place == host and day == today)
    return Unflushed(requests=activity.requests, peak=activity.peak, busy=activity.busy, people=people)


def _keep_activity(key: tuple[uuid.UUID, dt.date], failed: _Activity) -> None:
    with _lock:
        activity = _activity.setdefault(key, _Activity())
        activity.requests += failed.requests
        activity.peak = max(activity.peak, failed.peak)
        activity.busy += failed.busy


def _keep_people(host: str, day: dt.date, failed: dict[str, dt.datetime]) -> None:
    with _lock:
        for person, moment in failed.items():
            key = (host, day, person)
            _seen[key] = max(_seen.get(key, moment), moment)


def flush() -> None:
    """Write what the process counted; what could not be written stays for the next pass."""
    # Here: this module is imported by the tenancy's limits, before the apps are ready.
    from base import services

    global _activity, _seen
    with _flushing:
        with _lock:
            activity, seen = _activity, _seen
            _activity, _seen = {}, {}
        for (hub_id, day), delta in activity.items():
            try:
                if not services.activity_recorded(hub_id, day, requests=delta.requests, peak=delta.peak, busy=delta.busy):
                    logger.info("base.meter.hub_gone hub=%s day=%s: what it did is forgotten.", hub_id, day)
            except Exception:
                logger.exception("base.meter.not_written hub=%s day=%s: kept for the next pass.", hub_id, day)
                _keep_activity((hub_id, day), delta)
        by_place: dict[tuple[str, dt.date], dict[str, dt.datetime]] = {}
        for (host, day, person), moment in seen.items():
            by_place.setdefault((host, day), {})[person] = moment
        for (host, day), people in by_place.items():
            try:
                services.people_seen(host, day, people)
            except Exception:
                logger.exception("base.meter.not_written host=%s day=%s: its people kept for the next pass.", host, day)
                _keep_people(host, day, people)


def _loop(stop: threading.Event) -> None:
    while not stop.wait(INTERVAL_SECONDS):
        try:
            flush()
        except Exception:
            logger.exception("base.meter: a pass failed; the next one goes on.")
        finally:
            close_old_connections()


def start() -> None:
    """Count from now on and write it from a daemon thread and at exit: once per process, where ``METER_ENABLED``."""
    global _recording, _started
    if not settings.METER_ENABLED:
        return
    with _lock:
        if _started:
            return
        _started = True
        _recording = True
    threading.Thread(target=_loop, name="hub-meter", daemon=True, args=(threading.Event(),)).start()
    atexit.register(flush)
