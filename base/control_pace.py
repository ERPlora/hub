"""When the worker's steps on control run (``base.worker``).

Control's steps (the platform's own outbox, the list of businesses the visits serve, the apps to set up, the hubs due in
``hub_due``, the data work, the moves and the reaper) do not look for work on every tick: they run together, in a pass,
on the tick when one of these says so:

- the platform's channel (``CHANNEL``) was notified: every operation of the platform that records an event notifies
  it after its COMMIT (a sign-up, a demo, a cancellation, a move or a restore asked, the freeze set or lifted), and so
  does a business that turns on an app or asks for a reset (``base.services.provisioning.ring``);
- the next time control keeps came: a hub due in ``hub_due`` then, or free then from another worker's lease, or a move
  asked for its night (``base.queries.due_work.next_on_control``, read at the end of each pass);
- the last pass worked: what did not fit in its time budget is taken at the next tick;
- ``LOOK_SECONDS`` passed since the last pass: what a notice lost, or the LISTEN down, did not say;
- or this process never ran one.

The moves' pass (a hub moved to another cluster, a restore, a separate copy, a recovery, and the drop of the copies they
left after their days) starts in a pass only when it was asked (that pass's notice, or a move's night came), when the
last one could not start because one still ran, or ``MOVES_LOOK_SECONDS`` after it last started: nobody waits on the
rest of it.

Between two passes nothing is sent to control's database. The worker hears its channel on its one LISTEN, the one its
visits hear the businesses' channels on (:class:`Ear`, over ``base.hub_listener.Listener``).
"""

import datetime as dt
import logging
from collections.abc import Collection

from django.db import close_old_connections

from base import queries
from base.hub_listener import Listener
from base.registry import REGISTRY_SCOPE
from base.tenancy.context import use_control

logger = logging.getLogger(__name__)

#: The channel whose notice wakes control's steps: the platform's operations' (``REGISTRY_SCOPE``).
CHANNEL = REGISTRY_SCOPE.channel
#: The longest control goes without a pass.
LOOK_SECONDS = 60
#: The longest the moves' pass goes without starting.
MOVES_LOOK_SECONDS = 600


class Ear:
    """The worker's one LISTEN for its two listeners: the visits, on the businesses' channels (``heard``, as
    ``Listener.heard``), and control's steps, on :data:`CHANNEL` (``rung``). What one of them was not asking about yet is
    kept for it, and a connection made again counts as every channel heard for both."""

    def __init__(self, listener: Listener | None = None) -> None:
        self._listener = Listener() if listener is None else listener
        self._channels: frozenset[str] = frozenset()
        self._heard: set[str] = set()
        self._all = False
        self._rung = False

    def heard(self, channels: Collection[str]) -> frozenset[str] | None:
        """The businesses' ``channels`` notified since the visits last asked, or ``None`` after a connection made."""
        self._channels = frozenset(channels)
        self._listen()
        heard, every = frozenset(self._heard & self._channels), self._all
        self._heard, self._all = set(), False
        return None if every else heard

    def rung(self) -> bool:
        """Whether :data:`CHANNEL` was notified since the last call, or a connection was made."""
        self._listen()
        rung, self._rung = self._rung, False
        return rung

    def close(self) -> None:
        self._listener.close()

    def _listen(self) -> None:
        heard = self._listener.heard(self._channels | {CHANNEL})
        if heard is None:
            self._all = self._rung = True
            return
        self._heard |= heard - {CHANNEL}
        self._rung = self._rung or CHANNEL in heard


class ControlPace:
    """Whether this tick runs control's steps (:meth:`due`) and the moves' pass among them (:meth:`moves_due`), and
    what the pass left known (:meth:`ran`, :meth:`moved`)."""

    def __init__(self, ear: Ear) -> None:
        self._ear = ear
        self._ran_at: dt.datetime | None = None
        self._next_at: dt.datetime | None = None
        self._again = False
        self._asked = False
        self._moved_at: dt.datetime | None = None
        self._moves_waiting = False

    def due(self, now: dt.datetime) -> bool:
        rung = self._ear.rung()
        self._asked = rung or (self._next_at is not None and self._next_at <= now)
        if self._asked or self._again or self._ran_at is None:
            return True
        return now - self._ran_at >= dt.timedelta(seconds=LOOK_SECONDS)

    def moves_due(self, now: dt.datetime) -> bool:
        if self._asked or self._moves_waiting or self._moved_at is None:
            return True
        return now - self._moved_at >= dt.timedelta(seconds=MOVES_LOOK_SECONDS)

    def moved(self, now: dt.datetime, *, started: bool) -> None:
        """The moves' pass started at ``now``, or could not (one still runs: it starts at the next pass)."""
        if started:
            self._moved_at = now
        self._moves_waiting = not started

    def ran(self, now: dt.datetime, *, worked: bool) -> None:
        """A pass ran at ``now`` (``worked``: it did something, so the next tick looks again); the next time control
        keeps is read on it. One it cannot read is logged, and the look finds it."""
        self._ran_at, self._again = now, worked
        try:
            with use_control():
                self._next_at = queries.due_work.next_on_control(now)
        except Exception:
            self._next_at = None
            logger.exception("worker: the next time control keeps could not be read; its look finds it.")
        finally:
            close_old_connections()
