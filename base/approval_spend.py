"""The manager's pass, spent in the transaction of the command it lets through (rv-hub-244; ``base.approvals``).

``LIVE["operation_database"]`` (``base.entitlement``) wraps the transaction ``@operation`` opens; for the command a
request's pass is for (:class:`base.approvals.Approved`), :func:`spending` opens that transaction itself on the
command's alias and spends the pass inside it (``base.approval.spend``: its row locked, one use, bound to who asked, the
command and the request's fingerprint, two minutes), so ``@operation``'s own is a savepoint of it. A command that fails
rolls the spend back with it, and the same request goes through with the pass after; one that went through commits it
and is never repeated; of two at once, the second waits on the row, finds it spent and gets the question again. A
pass that does not spend is the question again, before the command runs.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from django.db import transaction
from live.operations import Operation, get

from base.approvals import Approved, refusal


@contextmanager
def spending(op: Operation, ctx, alias: str) -> Iterator[str]:
    """Around ``op``'s transaction on ``alias``: the request's pass spent in it, when it is ``op``'s; else nothing."""
    request = getattr(ctx, "request", None)
    approved = getattr(request, "approved", None)
    if not isinstance(approved, Approved) or approved.operation != op.name:
        yield alias
        return
    from base.schemas import ApprovalSpendIn

    with transaction.atomic(using=alias):
        spend = ApprovalSpendIn(token=approved.token, operation=op.name, fingerprint=approved.fingerprint)
        if not get("base.approval.spend")(ctx, spend).spent:
            raise refusal(op.name, approved.fingerprint)
        yield alias
