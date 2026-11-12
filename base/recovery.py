"""What an app says it gives back from a separate copy of its business (hub#1257; BASE-F114).

The contract of the hook ``recoverable_from_copy`` of a ``LiveAppConfig``, here and not in ``base.tenancy`` because the
apps import it and a module never imports the tenancy (``tests/test_guardrails.py``): the app only declares its reads
and its operation; the platform (``base.tenancy.recovery``) connects to the copy and chooses the business's database.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import psycopg

#: The hook of a ``LiveAppConfig`` that says what the app gives back from a separate copy.
HOOK = "recoverable_from_copy"


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
