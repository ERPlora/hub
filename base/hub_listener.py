"""The worker's ear on the channels of the businesses it serves (``base.hub_visits``).

One psycopg connection of its own to control's database, outside Django and the ORM, where every operation of a
business sends its notice after the COMMIT (``live.outbox.notify``, on ``Scope.channel``). It LISTENs on the channel of
each business it is asked for and says, without waiting and without sending anything to the database, which of them
were notified since it last asked: a ``select`` on its socket. Between two notices it holds an idle connection only.

A connection made, or made again after one was lost, counts as every channel heard (what was notified meanwhile is
unknown). One it cannot make is logged at ERROR (``base.worker.listen_failed``) and tried again after a pause that
doubles (``BACKOFF``: 1 s first, 60 s at most); meanwhile nothing is heard, and the worker's look every minute finds
what the notices would have said. Its connection string is control's (``live.broker.control_conninfo``, as the web's
LISTEN), with its own ``application_name``.
"""

import logging
import select
import time
from collections.abc import Callable, Collection

import psycopg
from live.broker import control_conninfo
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

logger = logging.getLogger(__name__)

#: TCP keepalives, so a connection dropped without a word (a failover) is noticed within about a minute.
KEEPALIVES = {"keepalives": 1, "keepalives_idle": 30, "keepalives_interval": 10, "keepalives_count": 3}
#: The pause after a connection it could not make: the first, and the longest it doubles up to (seconds).
BACKOFF = (1.0, 60.0)


def connect() -> psycopg.Connection:
    conninfo = control_conninfo()
    name = f"{conninfo_to_dict(conninfo).get('application_name') or 'worker'}-listener"
    return psycopg.connect(conninfo, autocommit=True, application_name=name, **KEEPALIVES)


class Listener:
    """``LISTEN`` on the channels asked for, on a connection of its own, and what was notified on them."""

    def __init__(
        self,
        *,
        connect: Callable[[], psycopg.Connection] = connect,
        backoff: tuple[float, float] = BACKOFF,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._connect = connect
        self._first_pause, self._longest_pause = backoff
        self._pause = self._first_pause
        self._clock = clock
        self._retry_at = 0.0
        self._conn: psycopg.Connection | None = None
        self._channels: set[str] = set()
        self._notified: set[str] = set()

    @property
    def pid(self) -> int | None:
        """The backend process of its connection (``pg_stat_activity.pid``), while it has one."""
        return None if self._conn is None else self._conn.info.backend_pid

    def heard(self, channels: Collection[str]) -> frozenset[str] | None:
        """Listen on ``channels`` (and no longer on the others), then take, without waiting, what was notified on them
        since the last call: the channels heard, or ``None`` when its connection was just made (every one counts as
        heard). Nothing heard while it cannot connect."""
        wanted = set(channels)
        if self._conn is None:
            return None if self._open(wanted) else frozenset()
        try:
            self._follow(wanted)
            heard = self._take()
        except psycopg.Error as error:
            logger.error("base.worker.listen_lost: %s", error)
            self._drop()
            self._open(wanted)
            return None
        return frozenset(heard & wanted)

    def close(self) -> None:
        self._drop()

    def _open(self, channels: set[str]) -> bool:
        if self._clock() < self._retry_at:
            return False
        try:
            self._conn = self._connect()
            # What arrives while it sends a LISTEN, psycopg hands to its handlers.
            self._conn.add_notify_handler(self._note)
            self._follow(channels)
        except psycopg.Error as error:
            logger.error("base.worker.listen_failed: %s; tried again in %.0f s.", error, self._pause)
            self._drop()
            self._retry_at = self._clock() + self._pause
            self._pause = min(self._pause * 2, self._longest_pause)
            return False
        self._pause = self._first_pause
        logger.info("base.worker.listening channels=%d pid=%s", len(channels), self.pid)
        return True

    def _follow(self, channels: set[str]) -> None:
        for channel in sorted(channels - self._channels):
            self._conn.execute(sql.SQL("LISTEN {}").format(sql.Identifier(channel)))
            self._channels.add(channel)
        for channel in sorted(self._channels - channels):
            self._conn.execute(sql.SQL("UNLISTEN {}").format(sql.Identifier(channel)))
            self._channels.discard(channel)

    def _note(self, notice: psycopg.Notify) -> None:
        self._notified.add(notice.channel)

    def _take(self) -> set[str]:
        ready, _, _ = select.select([self._conn.fileno()], [], [], 0)
        if ready:
            pgconn = self._conn.pgconn
            pgconn.consume_input()
            while (notice := pgconn.notifies()) is not None:
                self._notified.add(notice.relname.decode())
            if self._conn.closed:
                raise psycopg.OperationalError("the server closed the connection")
        heard, self._notified = self._notified, set()
        return heard

    def _drop(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        self._channels = set()
        self._notified = set()
