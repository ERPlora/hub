"""A hub's connection (``base.tenancy.limits``): Django's PostgreSQL connection whose every transaction holds a place of
its hub's limiter, from its first statement to its ``COMMIT``, ``ROLLBACK`` or the connection's close, and runs that
first statement after ``SET LOCAL statement_timeout`` of the hub's plan.

The check sits at the cursor, as the first of the connection's ``execute_wrappers`` (it wraps every other one), so it
sees every statement whoever opened the transaction: an operation's ``atomic``, ``live.operations.atomic``, the admin's,
the worker's or a test's. A statement alone (autocommit) is a transaction of its own: it holds a place while it runs,
inside a ``BEGIN``/``COMMIT`` of the driver that carries the timeout. A connection dropped without closing (its thread
gone in the middle of a transaction) gives its place back when it is collected.
"""

import weakref

from django.db.backends.postgresql import base as postgresql

from base.tenancy import limits


class DatabaseWrapper(postgresql.DatabaseWrapper):
    """The connection of a hub's alias: PostgreSQL with its plan's limits on every transaction."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._slot: limits.Slot | None = None
        self._slot_finalizer: weakref.finalize | None = None
        self.execute_wrappers.append(self._within_the_plan)

    def _within_the_plan(self, execute, sql, params, many, context):
        if self._slot is not None:
            return execute(sql, params, many, context)
        self._hold(limits.take(self.alias))
        driver_cursor = context["cursor"].cursor
        if not self.get_autocommit():
            # The transaction's first statement: its place stays held until the transaction ends, even when this fails
            # (an aborted transaction keeps its server connection until its ROLLBACK, or the connection's close).
            with self.wrap_database_errors:
                driver_cursor.execute(limits.statement_timeout_sql(self._slot.limits))
            return execute(sql, params, many, context)
        try:
            with self.wrap_database_errors, self.connection.transaction():
                driver_cursor.execute(limits.statement_timeout_sql(self._slot.limits))
                return execute(sql, params, many, context)
        finally:
            self._give_back()

    def _hold(self, slot: limits.Slot) -> None:
        self._slot = slot
        self._slot_finalizer = weakref.finalize(self, slot.release)

    def _give_back(self) -> None:
        slot, self._slot = self._slot, None
        if slot is not None:
            self._slot_finalizer.detach()
            self._slot_finalizer = None
            slot.release()

    def _commit(self):
        try:
            return super()._commit()
        finally:
            self._give_back()

    def _rollback(self):
        try:
            return super()._rollback()
        finally:
            self._give_back()

    def _close(self):
        try:
            return super()._close()
        finally:
            self._give_back()
