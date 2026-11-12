"""What a business lost, brought back from one of its separate copies (hub#1257, layer 2 of hub#1213; BASE-F114).

The staff asks it in the Hub admin («Recover into the business…» on a separate copy: ``control.copy.recover``, a
``control.CopyRecovery`` row naming the apps to bring back); the worker does it here (:func:`run_due`, in the moves'
thread), one a pass, under the row's own lease (:data:`LEASE`, renewed before each record it creates), never the hub's:
the business stays open and its own work goes on.

1. **Read**: the copy is read without making it a business. It is no hub's database and no process registers an alias
   of it (``names.is_left_behind``), so it is read through a direct connection of the migrator (``ops.connect_ops``),
   the only role that may connect to it, with every transaction read only: nothing scheduled runs there, the VeriFactu
   queue included, and nothing in it changes. For each app asked, its ``django_migrations`` in the copy says first
   whether the app's read fits the copy's schema, which stays the moment's: the app must be in the copy
   (``recover_not_in_copy``), hold the migration its read needs (``reads_since``; ``recover_copy_behind`` otherwise)
   and none this code does not know (``recover_copy_ahead``). Then the app reads its records, and the connection is
   closed before anything is written.
2. **Given back**: in the business (``use_hub``), the app says which of those records the business lacks, and each is
   created by the app's own operation, the one its screen uses, as the platform runs an operation in a business (the
   system's context, in the staff's language): rows are never copied. What the operation refuses for one record
   (its input) is counted with why and the others go on; what it refuses for all (the app turned off, the business
   busy) ends that app's part with why (``refused``), and the next app goes on.
3. **Noted**: control notes the recovery done with what each app gave back, or failed with why
   (``recover_<step>: <why>``). A worker whose lease ran out leaves it to whoever holds it now, who reads the copy
   anew: what was created is not lacking any more, so nothing is made twice.

What each app gives back is its own to say, by a hook of its ``LiveAppConfig`` (:data:`HOOK`, as
``fiscal_record_states`` says what a restore compares): ``recoverable_from_copy()`` answers a list of
:class:`Recoverable`, in the order they are given back. ``base`` never names an app. An app whose records reach the tax
authority never answers it: what was sent is at the tax authority already, and what is new is made in the business.
A business being moved or restored is left for a later pass: its recovery waits, nothing done.
"""

import datetime as dt
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import psycopg
import pydantic
from django.utils import timezone, translation
from live.context import OperationContext, Scope
from live.errors import InvalidPayload, OperationError
from live.meta import all_live_app_configs
from live.operations import get as get_operation

from base import registry, services
from base.tenancy import migrator, move, ops
from base.tenancy.context import use_hub
from control import services as control_services
from control.models import CopyRecovery, Hub

logger = logging.getLogger(__name__)

#: The hook of a ``LiveAppConfig`` that says what the app gives back from a separate copy.
HOOK = "recoverable_from_copy"
#: The worker's lease of a recovery: the moves', renewed before each record it creates.
LEASE = move.LEASE


@dataclass(frozen=True)
class Recoverable:
    """What an app gives back from a separate copy of its business (``recoverable_from_copy`` on its config).

    - ``label``: what the staff reads (a lazy translation: «Customers»);
    - ``reads_since``: the app's migration whose schema ``read`` reads (its tables and columns are there since);
    - ``read(conn)``: the records the copy holds, through ``conn``, the copy's direct read-only connection (its own SQL
      over its model's names, never the ORM): each a ``dict`` with its ``id`` in the copy and the input of ``create``;
    - ``missing(records)``: those the business lacks, read in the business (its ``queries.py``);
    - ``create``: the operation of the app that creates each, the one its screen uses.
    """

    label: Any
    reads_since: str
    read: Callable[[psycopg.Connection], list[dict]]
    missing: Callable[[list[dict]], list[dict]]
    create: str


class RecoveryFailed(Exception):
    """A recovery that cannot go on: ``code`` (``recover_<step>``) and why."""

    def __init__(self, code: str, why: object):
        super().__init__(f"{code}: {why}")
        self.code = code


def recoverable_apps() -> dict[str, list[Recoverable]]:
    """``{label: what it gives back}`` of every app that answers :data:`HOOK`, in the apps' order."""
    return {
        config.label: list(answer())
        for config in all_live_app_configs()
        if (answer := getattr(config, HOOK, None)) is not None
    }


def run_due(now: dt.datetime | None = None, *, cancelled: Callable[[], bool] | None = None) -> int:
    """The worker's pass: the recovery asked longest ago whose lease nobody else holds (one a pass); how many it worked
    on. One whose business is being moved or restored is left for a later pass. ``cancelled``: whether the worker is
    stopping (then it takes none)."""
    now = now or timezone.now()
    for recovery_id in control_services.recoveries_due():
        if cancelled is not None and cancelled():
            return 0
        # By the clock, never ``now``: a move before it in the same tick may have taken longer than the lease.
        row = control_services.claim_recovery(recovery_id, timezone.now(), LEASE, services.LEASE_OWNER)
        if row is None:
            continue
        try:
            worked = recover(row, now=now)
        finally:
            control_services.release_recovery(recovery_id, services.LEASE_OWNER)
        if worked:
            return 1
    return 0


def recover(row: CopyRecovery, *, now: dt.datetime) -> bool:
    """Do the recovery ``row`` (its lease held; see the module); whether it was worked on (``False``: its business is
    being moved or restored, left for later). A failure is noted on it, never raised."""
    copy, owner = row.copy, services.LEASE_OWNER
    # As it is now: a move or a restore may have started since the recovery was asked.
    hub = services.registry_row(copy.hub_id)
    if registry.is_copying(hub):
        logger.info("base.tenancy.recovery.waits copy=%s: the business %s is being moved or restored.", copy, hub.slug)
        return False

    def ours() -> None:
        try:
            control_services.still_recovering(row.pk, LEASE, owner)
        except control_services.MoveTaken as taken:
            raise move.MoveStopped(str(taken)) from taken

    results: list[dict] = []
    try:
        if hub.status != Hub.Status.READY or not hub.db_name:
            raise RecoveryFailed("recover_business_unavailable", f"the business {hub.slug} is {hub.status}")
        read = _read(copy, row.apps)
        with translation.override(row.language), use_hub(hub):
            for label, declared, records, refused in read:
                results.append(_give_back(hub, label, declared, records, refused, ours))
        control_services.recovery_done(row.pk, results, now, owner)
    except (move.MoveStopped, control_services.MoveTaken) as stopped:
        logger.info("base.tenancy.recovery.stopped copy=%s: %s; left to whoever holds it now.", copy, stopped)
        return True
    except Exception as error:
        reason = str(error)
        if not isinstance(error, RecoveryFailed):
            reason = f"recover_unexpected: {type(error).__name__}: {error}"
        logger.warning("base.tenancy.recovery.failed hub=%s copy=%s: %s", hub.slug, copy.db_name, reason)
        try:
            control_services.recovery_failed(row.pk, reason, results, now, owner)
        except control_services.MoveTaken as taken:
            logger.info("base.tenancy.recovery.stopped copy=%s: %s; left to whoever holds it now.", copy, taken)
        return True
    logger.info("base.tenancy.recovery.done hub=%s copy=%s results=%s", hub.slug, copy.db_name, results)
    return True


# ── Step 1: the copy, read only ──────────────────────────────────────────────────────────────────────────────────────


def _read(copy, labels: list[str]) -> list[tuple[str, list[Recoverable], list[list[dict]], str]]:
    """Each app of ``labels`` with what it gives back, the records its reads found in ``copy`` (one list a
    declaration) and why it gives nothing back (``""`` when it gives back what it read)."""
    declared_by_app = recoverable_apps()
    code = migrator.code_migrations()
    read = []
    try:
        with ops.connect_ops(copy.db_name, cluster=copy.cluster) as conn:
            conn.execute("SET default_transaction_read_only = on")
            applied = _applied(conn)
            for label in labels:
                declared = declared_by_app.get(label)
                refused = _refusal(label, declared, applied.get(label, set()), code)
                records = [] if refused else [one.read(conn) for one in declared]
                read.append((label, declared or [], records, refused))
    except psycopg.Error as error:
        raise RecoveryFailed("recover_copy_unreadable", ops.reason(error)) from error
    except ops.DatabaseOpsError as error:
        raise RecoveryFailed("recover_copy_unreadable", error) from error
    return read


def _applied(conn: psycopg.Connection) -> dict[str, set[str]]:
    """``{app: its migrations}`` the copy's ``django_migrations`` says it holds."""
    applied: dict[str, set[str]] = {}
    for app, name in conn.execute("SELECT app, name FROM django_migrations"):
        applied.setdefault(app, set()).add(name)
    return applied


def _refusal(label: str, declared: list[Recoverable] | None, applied: set[str], code: migrator.CodeMigrations) -> str:
    """Why the copy cannot give back ``label``'s records, by its ``django_migrations`` there; ``""`` when it can."""
    if not declared:
        return f"recover_not_recoverable: {label} gives nothing back from a copy"
    if not applied:
        return f"recover_not_in_copy: {label} was not in the business at the copy's moment"
    unknown = sorted(name for name in applied if (label, name) not in code.nodes)
    if unknown:
        return f"recover_copy_ahead: the copy has migrations of {label} this code does not know: {', '.join(unknown)}"
    behind = sorted({one.reads_since for one in declared} - applied)
    if behind:
        return f"recover_copy_behind: the copy lacks the migration of {label} its read needs: {', '.join(behind)}"
    return ""


# ── Step 2: given back in the business, by the app's own operations ─────────────────────────────────────────────────


def _give_back(hub: Hub, label: str, declared, records, refused: str, ours: Callable[[], None]) -> dict:
    """What ``label`` gave back to ``hub`` (in its ``use_hub``): each record it lacks created by its operation."""
    result = {"app": label, "created": 0, "not_created": 0, "reasons": [], "refused": refused}
    if refused:
        return result
    ctx = OperationContext(
        scope=Scope("host", hub.slug), actor="system", permissions=frozenset({"*"}), language=translation.get_language()
    )
    for one, found in zip(declared, records, strict=True):
        op = get_operation(one.create)
        for record in one.missing(found):
            ours()
            payload = {key: value for key, value in record.items() if key != "id"}
            try:
                op(ctx, op.input.model_validate(payload))
            except pydantic.ValidationError as invalid:
                _not_created(result, record, f"invalid_payload: {_first_error(invalid)}")
            except InvalidPayload as invalid:
                _not_created(result, record, f"{invalid.code}: {invalid.message}")
            except OperationError as stopped:
                result["refused"] = f"{stopped.code}: {stopped.message}"
                return result
            else:
                result["created"] += 1
    return result


def _not_created(result: dict, record: dict, reason: str) -> None:
    result["not_created"] += 1
    if len(result["reasons"]) < CopyRecovery.REASONS_KEPT:
        result["reasons"].append({"id": str(record["id"]), "reason": reason})


def _first_error(invalid: pydantic.ValidationError) -> str:
    error = invalid.errors()[0]
    where = ".".join(str(part) for part in error.get("loc", ()))
    return f"{where}: {error.get('msg', '')}" if where else str(error.get("msg", ""))
