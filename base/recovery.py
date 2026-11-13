"""What an app says it gives back from a separate copy of its business (hub#1257; BASE-F114).

The contract of the hook ``recoverable_from_copy`` of a ``LiveAppConfig``, here and not in ``base.tenancy`` because the
apps import it and a module never imports the tenancy (``tests/test_guardrails.py``): the app only declares its reads
and its operation; the platform (``base.tenancy.recovery``) connects to the copy and chooses the business's database.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import psycopg
from ninja import Field, Schema

#: The hook of a ``LiveAppConfig`` that says what the app gives back from a separate copy.
HOOK = "recoverable_from_copy"

#: The actor prefix of what a recovery does in the business (``copy_recovery:<id>``, the ``CopyRecovery``'s id): its
#: operations run as it, so every event they record keeps it in the outbox, as a run of an automation keeps its own
#: (hub#1307). What comes back is nothing new to the business: a reaction that greets or announces something new (an
#: automation of «customer created») starts nothing for it, while one that keeps the business's data whole still runs,
#: and the events that one records keep the mark too (the relay gives it), so nothing starts from them either.
ACTOR = "copy_recovery:"


def actor_of(recovery_id: object) -> str:
    """The actor the recovery ``recovery_id`` runs the apps' operations as."""
    return f"{ACTOR}{recovery_id}"


def brought_back(actor: str) -> bool:
    """Whether an event's ``actor``, as the outbox keeps it, is a recovery's: what it records came back from a separate
    copy, and is nothing new to the business."""
    return actor.startswith(ACTOR)


@dataclass(frozen=True)
class Recoverable:
    """What an app gives back from a separate copy of its business (``recoverable_from_copy`` on its config).

    - ``label``: what the staff reads, a lazy translation without a context («Customers»): a recovery keeps it as the
      code writes it, counted apart from the app's other things, and Recoveries says it in its reader's language;
    - ``reads_since``: the app's migration whose schema ``read`` reads (its tables and columns are there since);
    - ``read(conn)``: the records the copy holds, through ``conn``, the copy's direct read-only connection (its own SQL
      over its model's names, never the ORM): each a ``dict`` with its ``id`` in the copy and the input of ``create``;
    - ``missing(records)``: those the business no longer has, read in the business (its ``queries.py``);
    - ``create``: the operation of the app that creates each, the one its screen uses;
    - ``deleted(records)`` and ``restore``, together or neither, for an app whose deletion keeps the record: those the
      business still holds deleted, read in the business (its ``queries.py``), and the operation of the app that brings
      each back, the same record with all that hangs from it, given its ``id`` (hub#1306). They come back before the
      missing are created, so ``missing`` never counts them.
    """

    label: Any
    reads_since: str
    read: Callable[[psycopg.Connection], list[dict]]
    missing: Callable[[list[dict]], list[dict]]
    create: str
    deleted: Callable[[list[dict]], list[dict]] | None = None
    restore: str = ""

    def __post_init__(self) -> None:
        if (self.deleted is None) != (not self.restore):
            raise ValueError("A Recoverable restores what it reads deleted: deleted and restore come together.")


class LeftOut(Schema):
    """One thing a record came back without, and why: ``code`` (``<app>.<why>``) and ``message``, said in the language
    the operation runs in, which a recovery sets to the staff's."""

    code: str
    message: str


class RecoveredOut(Schema):
    """Mixed into the output of an operation a recovery runs (a ``Recoverable``'s ``create`` or ``restore``) whose
    record may come back without something that hung from it in the copy (a professional who has left since): the
    recovery notes each by the record's id in the copy, as it notes why one did not come back at all. An output without
    it notes nothing."""

    left_out: list[LeftOut] = Field(
        default_factory=list, description="What the record came back without, each with why."
    )
