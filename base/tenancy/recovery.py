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
2. **Given back**: in the business (``use_hub``), the app says which of those records the business still holds deleted
   and which it no longer has: each deleted one comes back first, the same record with all that hangs from it, by the
   app's operation that undoes a deletion (``restore``, hub#1306), given of the record what its input declares (its
   id, and what the business lost of it since, hub#1356), and each missing one is created by the app's own
   operation, the one its screen uses, as the platform runs an operation in a business (the system's permissions, in the
   staff's language): rows are never copied. They run as the recovery (``base.recovery.actor_of``), so every event they
   record says in the outbox that it came back, and nothing new to the business starts for it (hub#1307). The apps go in the order of their ``requires``
   (``activation.in_requires_order``), whatever the order asked, so a record finds what it points at in another app
   brought back first (hub#1284). What the operation refuses for one record (its input, the record or what it names
   gone since, or the business as it is now: a time taken) is counted with why and the others go on; what it refuses
   for all (the app turned off, the business busy) ends that app's part with why (``refused``), and the next app goes
   on.
3. **Noted**: control notes the recovery done with what each thing each app declares gave back, apart and under its
   name, with what a record came back without when its operation says so (``base.recovery.RecoveredOut``), or failed
   with why (``recover_<step>: <why>``). A worker whose lease ran out leaves it to whoever holds it now, who reads the
   copy anew: what was created is not lacking any more, so nothing is made twice.

What each app gives back is its own to say, by a hook of its ``LiveAppConfig`` (``base.recovery.HOOK``, as
``fiscal_record_states`` says what a restore compares): ``recoverable_from_copy()`` answers a list of
:class:`base.recovery.Recoverable`, in the order they are given back. ``base`` never names an app. An app whose records
reach the tax authority never answers it: what was sent is at the tax authority already, and what is new is made in the
business.
A business being moved or restored is left for a later pass: its recovery waits, nothing done.
"""

import datetime as dt
import logging
from collections.abc import Callable
from functools import partial

import psycopg
import pydantic
from django.utils import timezone, translation
from live.context import OperationContext, Scope
from live.errors import Conflict, InvalidPayload, NotFound, OperationError
from live.meta import all_live_app_configs
from live.operations import get as get_operation

from base import activation, registry, services
from base.recovery import HOOK, LeftOut, Recoverable, RecoveredOut, actor_of
from base.tenancy import migrator, move, ops
from base.tenancy.context import use_hub
from control import services as control_services
from control.models import CopyRecovery, Hub

logger = logging.getLogger(__name__)

#: The worker's lease of a recovery: the moves', renewed before each record it creates.
LEASE = move.LEASE


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
        read = _read(copy, activation.in_requires_order(row.apps, activation.module_graph()))
        with translation.override(row.language), use_hub(hub):
            for label, declared, records, refused in read:
                _give_back(row, hub, results, label, declared, records, refused, ours)
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


def _give_back(
    row: CopyRecovery,
    hub: Hub,
    results: list[dict],
    label: str,
    declared,
    records,
    refused: str,
    ours: Callable[[], None],
) -> None:
    """What ``label`` gives back to ``hub`` (in its ``use_hub``), each thing it declares in turn and counted in a result
    of its own: each record it holds deleted brought back by its restore, then each it no longer has created by its
    create. A result is in ``results`` from the start of its part, so a failure halfway is noted with what had come back
    until then; ``not_created`` counts what either refused. What the app refuses for all ends its part, and what it had
    left to give back is noted with the same why. An app that declares nothing has one result, its own. The operations
    run as the recovery (``base.recovery.actor_of``), with the system's permissions: their events say it came back."""
    if not declared:
        results.append(_result(label, refused))
        return
    ctx = OperationContext(
        scope=Scope("host", hub.slug),
        actor=actor_of(row.pk),
        permissions=frozenset({"*"}),
        language=translation.get_language(),
    )
    for index, one in enumerate(declared):
        result = _result(label, refused, one.label)
        results.append(result)
        if refused:
            continue
        steps = [(one.create, one.missing, "created", _create_input)]
        if one.restore:
            takes = get_operation(one.restore).input.model_fields
            steps.insert(0, (one.restore, one.deleted, "restored", partial(_restore_input, takes)))
        for name, which, counted, payload in steps:
            if not _each(ctx, get_operation(name), which(records[index]), payload, counted, result, ours):
                refused = result["refused"]
                break


def _result(app: str, refused: str, named=None) -> dict:
    """What ``app`` gave back, nothing yet: of the thing it declares ``named``, whose name is kept as the code writes
    it (``label``) and said in the language of whoever reads it, as Django keeps an object's name in its admin's
    history; without ``named``, of the app as a whole."""
    result = {"app": app, "restored": 0, "created": 0, "not_created": 0, "reasons": [], "refused": refused}
    if named is not None:
        with translation.override(None):
            result["label"] = str(named)
    return result


def _each(ctx, op, records: list[dict], payload, counted: str, result: dict, ours: Callable[[], None]) -> bool:
    """``op`` run on each of ``records``, its input ``payload(record)``, counted in ``result[counted]``, with what its
    output says the record came back without; ``False`` once it refuses them all (``refused``), and the app's part
    ends."""
    for record in records:
        ours()
        try:
            done = op(ctx, op.input.model_validate(payload(record)))
        except pydantic.ValidationError as invalid:
            _not_created(result, record, f"invalid_payload: {_first_error(invalid)}")
        except (InvalidPayload, NotFound, Conflict) as refused_one:
            # The record's own: its input, it or what it names gone, the business as it is now (a time taken).
            _not_created(result, record, f"{refused_one.code}: {refused_one.message}")
        except OperationError as stopped:
            result["refused"] = f"{stopped.code}: {stopped.message}"
            return False
        else:
            result[counted] += 1
            if isinstance(done, RecoveredOut) and done.left_out:
                _noted(result, record, done.left_out)
    return True


def _create_input(record: dict) -> dict:
    """What a create takes: the record as the copy holds it, but its id there."""
    return {key: value for key, value in record.items() if key != "id"}


def _restore_input(takes, record: dict) -> dict:
    """What a restore takes: of the record as the copy holds it, what its input declares (``takes``): its id, the same
    in the copy and in the business, and whatever else it gives back to the record that the business lost since."""
    return {key: value for key, value in record.items() if key in takes}


def _not_created(result: dict, record: dict, reason: str) -> None:
    result["not_created"] += 1
    if len(result["reasons"]) < CopyRecovery.REASONS_KEPT:
        result["reasons"].append({"id": str(record["id"]), "reason": reason})


def _noted(result: dict, record: dict, left_out: list[LeftOut]) -> None:
    """``record`` came back without what ``left_out`` says: counted once (``noted``) and each said with why
    (``notes``), the first :data:`CopyRecovery.REASONS_KEPT` of the result, by its id in the copy."""
    result["noted"] = result.get("noted", 0) + 1
    notes = result.setdefault("notes", [])
    for one in left_out[: CopyRecovery.REASONS_KEPT - len(notes)]:
        notes.append({"id": str(record["id"]), "note": f"{one.code}: {one.message}"})


def _first_error(invalid: pydantic.ValidationError) -> str:
    error = invalid.errors()[0]
    where = ".".join(str(part) for part in error.get("loc", ()))
    return f"{where}: {error.get('msg', '')}" if where else str(error.get("msg", ""))
