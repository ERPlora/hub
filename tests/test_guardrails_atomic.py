"""Guardrail of the savepoints (W9; the finding of hub#468; PLAN-DB §4; CLAUDE.md «Tenencia del Hub»).

Django's ``transaction.atomic()`` opens on ``default`` (control's database) whatever hub the code works in. With a hub's
own database (S2) an operation's transaction is on the hub's alias, and a bare ``transaction.atomic()`` inside it opens
another transaction on control instead of a savepoint of the operation's: ``try: with transaction.atomic(): create…
except IntegrityError:`` then aborts the hub's transaction, and every write after it fails (or a select_for_update runs
with no transaction at all). ``live.operations.atomic()`` opens on ``live.operations.current_alias()``: the hub's
``LIVE["current_database"]`` (``base.tenancy.context.current_alias``, the active ``use_hub``'s alias and
``HubContextMissing`` without one), never ``default`` by omission.

Static and fast, like ``tests/test_guardrails.py`` (whose rule (b) keeps ``using=`` out): a pure function over source
text, proven by made-up offenders (the positive control), then run over ``apps/`` and ``base/`` outside ``tests/``,
``base/tenancy/`` (the tenancy chooses aliases itself) and the migrations (``RunPython`` runs on its schema editor's
alias). Django's atomic, and what else of its transactions works on ``default`` without ``using=`` (``set_rollback``,
the savepoints, ``get_connection``, ``mark_for_rollback_on_error``…), stays only in the functions of
``DJANGO_ATOMIC_ALLOWED``, each with its reason. The tests at the
end prove the behaviour with the two hubs' real databases (``hub_a``, ``hub_b``).
"""

import ast
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

import pytest
from django.db import IntegrityError, connections
from live.context import OperationContext, Scope
from live.operations import INTERNAL, Operation, atomic, current_alias
from ninja import Schema

from apps.demo.models import Item
from base.tenancy import context
from base.tenancy.tests import hubs

HUB_DIR = Path(__file__).resolve().parent.parent
SOURCE_ROOTS = ("apps", "base")
#: Out of the scan: the tenancy, which chooses and opens the hubs' aliases itself (``tests/test_guardrails.py``, (b)).
SKIPPED_PACKAGE = PurePosixPath("base/tenancy")
#: Django's module of transactions, as a dotted name.
TRANSACTION_MODULE = "django.db.transaction"
#: What of it opens a block: the function and its class (always reported, ``using=`` or not).
ATOMIC_NAMES = frozenset({"atomic", "Atomic"})
#: The rest of it that works on ``default`` without ``using=``: inside an operation on a hub's alias, the same bug.
#: Called with ``using=`` it is ``tests/test_guardrails.py``'s rule (b); a positional alias, which that rule cannot see,
#: is reported here.
DEFAULT_ALIAS_NAMES = frozenset(
    {
        "set_rollback",
        "get_rollback",
        "savepoint",
        "savepoint_commit",
        "savepoint_rollback",
        "clean_savepoints",
        "get_connection",
        "mark_for_rollback_on_error",
        "get_autocommit",
        "set_autocommit",
        "commit",
        "rollback",
    }
)
REPORTED_NAMES = ATOMIC_NAMES | DEFAULT_ALIAS_NAMES

CONTROL_LOGIN = (
    "The way in writes control's models (the account's local copy in auth, its Membership, Django's session and its "
    "SessionOwner) in control's transaction, Django's atomic on default, whatever hub's host it runs on; the hub's own "
    "rows (its TrustedDevice) go in the hub's, live.operations.atomic() inside it: two databases, a block on each."
)

#: ``<path>::<function>`` → why Django's atomic (or the rest of its transactions) on its alias is the one meant there.
DJANGO_ATOMIC_ALLOWED: dict[str, str] = {
    "base/catalog.py::register_apps": (
        "It writes shared.app and shared.app_doc on the `shared` alias, which it names (SHARED_CATALOG_REASON of "
        "tests/test_guardrails.py): no hub's database and no operation."
    ),
    "base/approval_spend.py::spending": (
        "It is part of LIVE['operation_database']: it opens the operation's own transaction on the alias the tenancy "
        "gave it (APPROVAL_SPEND_REASON of tests/test_guardrails.py), before live.operations runs the operation."
    ),
    "base/services.py::hub_register": (
        "base.hub.register is the platform's operation (use_control): its writes (control.Hub) and its two savepoints "
        "are control's, the alias of its own transaction. The registry block is S2a's; it is left as it is here."
    ),
    "base/services.py::open_session_from_saas": CONTROL_LOGIN,
    "base/services.py::open_session_on_device": CONTROL_LOGIN,
    "base/services.py::open_admin_session_from_saas": (
        "Only control's models (the staff copy, its groups, Django's session), on the platform host: control's "
        "transaction."
    ),
    "base/services.py::open_demo_session": (
        "Only control's models (the demo's local user, its Membership, Django's session): control's transaction, "
        "whatever demo's host it runs on."
    ),
}


class _DjangoAtomicFinder(ast.NodeVisitor):
    """Each use of Django's ``atomic`` (and of what else of its transactions works on ``default`` without ``using=``),
    with the function it is in (``Class.method``; a decorator is its function's)."""

    def __init__(self) -> None:
        self.found: list[tuple[int, str, str]] = []
        self._scope: list[str] = []
        # ``transaction`` is Django's in the Hub's code, imported or not (a file that lost its import still reads so).
        self._modules: set[str] = {"transaction"}
        #: Names bound to ``django.db`` itself (``import django.db as db``, ``from django import db``).
        self._db_modules: set[str] = set()
        #: The calls with ``using=`` already judged: their function is not reported again as an attribute.
        self._with_using: set[int] = set()

    def _note(self, node: ast.AST, what: str) -> None:
        self.found.append((node.lineno, ".".join(self._scope) or "<module>", what))

    def _is_transaction(self, node: ast.AST) -> bool:
        dotted = _dotted(node)
        if dotted is None:
            return False
        owner, _, last = dotted.rpartition(".")
        if dotted in self._modules or dotted == TRANSACTION_MODULE:
            return True
        return last == "transaction" and owner in self._db_modules

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == TRANSACTION_MODULE and alias.asname:
                self._modules.add(alias.asname)
            elif alias.name == "django.db" and alias.asname:
                self._db_modules.add(alias.asname)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "django":
            self._db_modules |= {alias.asname or alias.name for alias in node.names if alias.name == "db"}
        elif node.module == "django.db":
            self._modules |= {alias.asname or alias.name for alias in node.names if alias.name == "transaction"}
        elif node.module == TRANSACTION_MODULE:
            for alias in node.names:
                if alias.name in REPORTED_NAMES:
                    self._note(node, f"from {TRANSACTION_MODULE} import {alias.name}")

    def visit_Assign(self, node: ast.Assign) -> None:
        # ``tx = transaction``: the module under another name.
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and self._is_transaction(node.value):
            self._modules.add(node.targets[0].id)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        function = node.func
        if (
            isinstance(function, ast.Attribute)
            and function.attr in DEFAULT_ALIAS_NAMES
            and any(keyword.arg == "using" for keyword in node.keywords)
        ):
            self._with_using.add(id(function))
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in REPORTED_NAMES and id(node) not in self._with_using and self._is_transaction(node.value):
            self._note(node, f"{_dotted(node.value)}.{node.attr}")
        self.generic_visit(node)

    def _scoped(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> None:
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _scoped


def _dotted(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        owner = _dotted(node.value)
        return None if owner is None else f"{owner}.{node.attr}"
    return None


def django_atomic_uses(source: str) -> list[tuple[int, str, str]]:
    """``(line, function, what)`` for each use of Django's ``atomic`` (or ``Atomic``) in ``source``: through
    ``transaction`` however it was imported, by its dotted name, or imported by name. With or without ``using=``."""
    finder = _DjangoAtomicFinder()
    finder.visit(ast.parse(source))
    return finder.found


def scanned_files() -> list[PurePosixPath]:
    """Every ``.py`` of ``apps/`` and ``base/`` the rule reads: not in ``tests/``, a migration or ``base/tenancy/``."""
    files = []
    for root in SOURCE_ROOTS:
        for path in sorted((HUB_DIR / root).rglob("*.py")):
            relative = PurePosixPath(path.relative_to(HUB_DIR).as_posix())
            if {"tests", "migrations"} & set(relative.parts) or relative.is_relative_to(SKIPPED_PACKAGE):
                continue
            files.append(relative)
    return files


def _uses_by_file() -> dict[str, list[tuple[int, str, str]]]:
    return {
        str(path): uses
        for path in scanned_files()
        if (uses := django_atomic_uses((HUB_DIR / path).read_text(encoding="utf-8")))
    }


OFFENDERS = '''
from django.db import transaction
from django.db import transaction as tx
import django.db.transaction as dtx
import django.db.transaction
from django.db.transaction import atomic, Atomic as Block


@transaction.atomic
def decorated():
    pass


@transaction.atomic()
def decorated_called():
    pass


class Admin:
    def delete_model(self):
        with transaction.atomic():
            pass

    def named(self):
        with transaction.atomic(using="hub_0190"):
            pass


def others():
    with tx.atomic(savepoint=False):
        pass
    with dtx.atomic():
        pass
    with django.db.transaction.atomic():
        pass
    return transaction.Atomic
'''

INNOCENT = '''
from django.db import transaction
from live.operations import atomic, on_commit


@atomic
def decorated(alias):
    with atomic(savepoint=False):
        transaction.set_rollback(True, using=alias)


def elsewhere(self, block):
    transaction.on_commit(print)
    on_commit(print)
    return self.atomic, block.atomic(), self.transaction.set_rollback(True)
'''

#: ``django.db`` under a name of its own, and ``transaction`` given another one.
RENAMED = '''
import django.db as db
from django import db as dj
from django.db import transaction

tx = transaction
inner = db.transaction


def f():
    with db.transaction.atomic():
        dj.transaction.set_rollback(True)
    with tx.atomic():
        inner.get_connection()
'''

#: What else of Django's transactions goes to ``default`` without ``using=`` (a positional alias is no ``using=``).
DEFAULT_ALIAS_APIS = '''
from django.db import transaction
from django.db.transaction import savepoint


def f(sid, alias):
    transaction.set_rollback(True)
    sid = transaction.savepoint()
    transaction.savepoint_rollback(sid)
    transaction.savepoint_commit(sid)
    transaction.get_connection()
    transaction.get_connection(alias)
    with transaction.mark_for_rollback_on_error():
        pass
    later = transaction.get_rollback
    transaction.set_rollback(True, using=alias)
    return later
'''


def test_the_scanner_sees_every_shape_of_djangos_atomic_and_where_it_is():
    assert django_atomic_uses(OFFENDERS) == [
        (6, "<module>", "from django.db.transaction import atomic"),
        (6, "<module>", "from django.db.transaction import Atomic"),
        (9, "decorated", "transaction.atomic"),
        (14, "decorated_called", "transaction.atomic"),
        (21, "Admin.delete_model", "transaction.atomic"),
        (25, "Admin.named", "transaction.atomic"),
        (30, "others", "tx.atomic"),
        (32, "others", "dtx.atomic"),
        (34, "others", "django.db.transaction.atomic"),
        (36, "others", "transaction.Atomic"),
    ]


def test_the_scanner_reads_transaction_as_djangos_even_without_its_import():
    assert django_atomic_uses("def f():\n    with transaction.atomic():\n        pass\n") == [
        (2, "f", "transaction.atomic")
    ]


def test_the_scanner_follows_django_db_under_another_name_and_transaction_reassigned():
    assert django_atomic_uses(RENAMED) == [
        (11, "f", "db.transaction.atomic"),
        (12, "f", "dj.transaction.set_rollback"),
        (13, "f", "tx.atomic"),
        (14, "f", "inner.get_connection"),
    ]


def test_the_scanner_sees_the_rest_of_djangos_transaction_api_that_goes_to_default_without_using():
    assert django_atomic_uses(DEFAULT_ALIAS_APIS) == [
        (3, "<module>", "from django.db.transaction import savepoint"),
        (7, "f", "transaction.set_rollback"),
        (8, "f", "transaction.savepoint"),
        (9, "f", "transaction.savepoint_rollback"),
        (10, "f", "transaction.savepoint_commit"),
        (11, "f", "transaction.get_connection"),
        (12, "f", "transaction.get_connection"),
        (13, "f", "transaction.mark_for_rollback_on_error"),
        (15, "f", "transaction.get_rollback"),
    ]


def test_the_scanner_lets_lives_atomic_and_the_rest_of_transaction_be():
    assert django_atomic_uses(INNOCENT) == []


def test_the_scan_reads_the_apps_and_base_but_not_the_tenancy_the_migrations_nor_the_tests():
    files = {str(path) for path in scanned_files()}

    assert {"apps/sale/services.py", "apps/task/admin.py", "base/services.py", "base/catalog.py"} <= files
    assert not any(path.startswith("base/tenancy/") for path in files)
    assert not any("/migrations/" in path or "/tests/" in path for path in files)


def test_djangos_atomic_is_only_where_the_list_says():
    offenders = [
        f"{path}:{line} {what} (in {function})"
        for path, uses in _uses_by_file().items()
        for line, function, what in uses
        if f"{path}::{function}" not in DJANGO_ATOMIC_ALLOWED
    ]

    assert offenders == [], (
        "A bare transaction.atomic() (or set_rollback, a savepoint, get_connection… without using=) works on control's "
        "database, not in the operation's transaction on the hub's: use live.operations.atomic() (or list the function "
        f"in DJANGO_ATOMIC_ALLOWED with its reason): {offenders}"
    )


def test_every_listed_function_still_uses_djangos_atomic():
    used = {f"{path}::{function}" for path, uses in _uses_by_file().items() for _, function, _ in uses}

    assert sorted(set(DJANGO_ATOMIC_ALLOWED) - used) == []


# ── The behaviour, with the two hubs' real databases ─────────────────────────────────────────────────────────────


HUB_DB = pytest.mark.django_db(databases=hubs.HUB_DATABASES)


@pytest.fixture
def no_test_fallback(monkeypatch):
    """As production: without a context a hub's model fails (``base/tenancy/tests/conftest.py`` has the same one)."""
    monkeypatch.setattr(context, "_test_fallback", None)


class Empty(Schema):
    pass


class Names(Schema):
    names: list[str]


def as_hub(hub) -> OperationContext:
    return OperationContext(scope=Scope("host", hub.slug), actor="system", permissions=frozenset({"*"}))


@contextmanager
def statements_on(alias: str):
    """Every statement this thread sends to ``alias`` while the block runs (Django's savepoints included)."""
    sent: list[str] = []

    def note(execute, sql, params, many, ctx):
        sent.append(sql)
        return execute(sql, params, many, ctx)

    with connections[alias].execute_wrapper(note):
        yield sent


def recover(ctx, data) -> dict:
    """What a services.py does: the write that may clash in ``atomic()``, the error caught, and on writing."""
    first = Item.objects.create(name="first")
    try:
        with atomic():
            Item.objects.create(id=first.id, name="again")
    except IntegrityError:
        pass
    Item.objects.create(name="after")
    return {"names": sorted(Item.objects.values_list("name", flat=True))}


@HUB_DB
@pytest.mark.usefixtures("no_test_fallback")
def test_an_operation_in_a_recovers_from_an_integrity_error_in_a_savepoint_of_a_and_never_opens_one_on_control(
    hub_a, hub_b
):
    op = Operation(
        name="demo.item.recover",
        kind="command",
        permission=None,
        input=Empty,
        output=Names,
        expose_api=False,
        ai=INTERNAL,
        fn=recover,
    )

    with context.use_hub(hub_a), statements_on("default") as on_control, statements_on(hubs.HUB_A_ALIAS) as on_a:
        result = op(as_hub(hub_a), Empty())

    assert result.names == ["after", "first"]
    assert not any("SAVEPOINT" in sql for sql in on_control)
    assert any(sql.startswith("ROLLBACK TO SAVEPOINT") for sql in on_a)
    with context.use_hub(hub_b):
        assert not Item.objects.exists()


@HUB_DB
@pytest.mark.usefixtures("no_test_fallback")
def test_outside_an_operation_atomic_opens_in_the_active_context_and_refuses_without_one(hub_a):
    with context.use_hub(hub_a):
        in_a = current_alias()
        before = len(connections[hubs.HUB_A_ALIAS].savepoint_ids)
        with atomic():
            opened_in_a = len(connections[hubs.HUB_A_ALIAS].savepoint_ids) - before
    with context.use_control():
        in_control = current_alias()

    assert (in_a, opened_in_a, in_control) == (hubs.HUB_A_ALIAS, 1, "default")
    with pytest.raises(context.HubContextMissing), atomic():
        pass
