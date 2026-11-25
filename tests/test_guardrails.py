"""Guardrails of the Hub's source: the tenancy (one database per hub) and the single path to the server (every
read and write through an operation). Static and fast: each check is a pure
function over source text (or the ``DATABASES`` dict), proven by a made-up offender (the positive
control), then run over ``base/`` and ``apps/`` (outside ``tests/``).

(a) Only the doors touch the ORM: managers, QuerySet methods, model writes, ``transaction``,
    ``connection``, ``QuerySet``/``Manager`` and ``get_object_or_404`` appear only in an app's ``services`` and
    ``queries``, a file or a package (``orm_doors.py``), plus the owners and exceptions of ``ORM_OWNERS`` and
    ``ORM_EXCEPTIONS``, each with its reason. Known limit: it reads shape, not types, so methods
    shared with dicts, sets, strings or paths (``get``, ``update``, ``count``, ``exists``, ``add``…)
    are only caught when they hang from a manager (``Model.objects.get``).
(b) No alias chosen by hand: no ``using=``, ``.using(`` or ``connections[``; no session
    ``pg_advisory_lock(`` (PgBouncer) and no ``ATOMIC_REQUESTS`` (the transaction is
    ``@operation``'s). Single exceptions: ``.using(<schema_editor>.connection.alias)`` in a migration
    (``RunPython``), the modules of ``base/tenancy/migrator/`` and ``base/catalog/register_apps.py`` (the ``shared`` alias).
(c) No ``GenericForeignKey``: a hub's models only reference what lives in the same hub database.
(d) Hub aliases (``hub_<hex>``, ``hub_<hex>__ddl``, ``demo_…``, ``hub_template…``) go through PgBouncer in
    transaction mode: no ``pool``, ``CONN_MAX_AGE`` 0, no server-side cursors and no prepared statements; no alias
    has ``ATOMIC_REQUESTS``.
(f) The tests read the clock when they run, never when pytest imports them (``clock_at_import``): a date taken at
    import is the day of the collection, and a run that crosses midnight or New Year's Eve falls. Unlike the others,
    it runs over the suite itself: every ``test_*.py`` and ``conftest.py`` of the repo, and the helpers of its
    ``tests`` folders, but the submodules of ``packages/``.

The tenancy's rules (e) and (g) are ``tests/test_guardrails_tenancy.py``; (i), (j) and (k), which run over the
suite like (f), ``tests/test_guardrails_suite.py``.

Every ninja route bound to an operation is ``config/tests/test_api.py`` (``ensure_api_parity``);
``/admin/`` on a tenant's host → 404 is ``base/tests/test_middleware.py``.
"""

import ast
import re
from pathlib import Path, PurePosixPath

from django.conf import settings
from orm_doors import is_door, is_schema_module

HUB_DIR = Path(__file__).resolve().parent.parent
SOURCE_ROOTS = ("base", "control", "apps")

# ── (a) Who may touch the ORM ──────────────────────────────────────────────────────────────────

#: Owners of the ORM that are no path to the data from the API: ``models.py``, or a module of a ``models/`` package,
#: declares the schema (managers, QuerySets, constraints with ``Q``); ``admin.py`` is Django's admin, the second write
#: path the platform accepts, whose actions call ``services.py``; an ``admin_<part>.py`` beside it is a
#: part of that admin, which its ``admin.py`` registers.
ORM_OWNERS = frozenset({"models.py", "admin.py"})
ADMIN_PART = re.compile(r"admin_\w+\.py")
#: Files outside the doors that may touch the ORM, each with its reason. Not here on purpose:
#: ``live.py`` (it only names events), ``api.py`` (one operation per route), ``auth.py`` (reads
#: ``Membership.Role``, an enum), ``auth_views.py`` (opens the session through ``services``),
#: ``middleware.py`` (only ``request.user``, loaded by Django), ``management/commands/`` (all by
#: API: a command calls an operation).
#: ``/readyz`` is the deploy gate: it must reach the database without an operation.
READYZ_REASON = (
    "/readyz reads django_migrations on the control database (connections[DEFAULT_DB_ALIAS], "
    "MigrationExecutor): a platform probe that never reads a hub's data."
)
#: The registry of the Hub's modules in the SaaS's ``shared`` schema.
SHARED_CATALOG_REASON = (
    "register_apps writes shared.app and shared.app_doc on the `shared` alias for no hub and no user, "
    "so it is no @operation; it is the only module that imports shared.models and names that alias "
    "(base/tests/test_shared_lint.py), and the hub_shared role (SELECT, INSERT, UPDATE on those two "
    "tables) is the boundary."
)
#: A manager's pass is spent in the transaction of the command it lets through.
APPROVAL_SPEND_REASON = (
    "LIVE['operation_database'] wraps @operation's transaction: for the command a request's pass is for, "
    "base.approval_spend opens that transaction on the alias the tenancy gave the command (never one of its own) and "
    "spends the pass through the base.approval.spend operation inside it, so a command that fails rolls the spend back "
    "and two at once lock the same row; it reads and writes nothing itself."
)
#: The tenancy itself chooses and checks the hubs' aliases.
TENANCY_ALIASES_REASON = (
    "use_hub registers a hub's alias the first time a process uses it, swapping in a copy of "
    "connections.settings under a lock, never changing it in place."
)
TENANCY_IDENTITY_REASON = (
    "use_hub reads base_hub_identity on the hub's own alias once per process before serving anything from it: "
    "a database that says it is another hub is refused; outside any operation by design."
)
#: The schema migrator, a package: each of its modules that reaches the database by hand.
MIGRATOR_ORM_REASON = (
    "The only function that changes a hub's schema, through its direct __ddl "
    "connection and the schema lock."
)
MIGRATOR_ALIAS_REASON = (
    "The schema migrator opens hub_<hex>__ddl itself and takes the session "
    "pg_advisory_lock of the schema."
)
ORM_EXCEPTIONS: dict[str, str] = {
    "base/permissions.py": (
        "The context builder reads Membership, the role the business gave the person and a fresh copy of the user "
        "before any operation runs, so it cannot go through one; read only."
    ),
    "base/health.py": READYZ_REASON,
    "base/registry.py": (
        "The host gate reads the registry's row of the Host's slug (404, 410, 503) before any operation runs, "
        "so it cannot go through one; read only, one indexed lookup; its writes are base.services' operations."
    ),
    "base/approval_spend.py": APPROVAL_SPEND_REASON,
    "base/tenancy/migrator/control_database.py": MIGRATOR_ORM_REASON,
    "base/tenancy/migrator/hub_templates.py": MIGRATOR_ORM_REASON,
    "base/tenancy/migrator/hubs_pass.py": MIGRATOR_ORM_REASON,
    "base/tenancy/migrator/schema.py": MIGRATOR_ORM_REASON,
    "base/tenancy/migrator/servers.py": MIGRATOR_ORM_REASON,
    "base/catalog/register_apps.py": SHARED_CATALOG_REASON,
    "base/tenancy/bootstrap.py": "bootstrap runs once as the RDS master before any app database exists.",
    "base/tenancy/connections.py": TENANCY_ALIASES_REASON,
    "base/worker.py": (
        "The worker's slow passes (a hub's copy, the nightly measurement) run in threads of their own, one piece at a "
        "time: each closes its thread's connections when it ends "
        "(connections.close_all, as migrate_hubs' threads do); no query, no write."
    ),
    "base/tenancy/router.py": (
        "The TenantRouter compares the databases behind two aliases (connections.settings) to allow a relation: it "
        "routes, it never queries."
    ),
    "base/tenancy/identity.py": TENANCY_IDENTITY_REASON,
    "apps/website/qr.py": (
        "Pillow's Image.save writes the website's QR as a PNG into a memory buffer: no model and no database."
    ),
    "base/images.py": (
        "Pillow's Image.save writes a photo into a memory buffer, and the hub file store's save and delete keep and "
        "remove its file (storages, not the ORM): no model and no database."
    ),
    "base/public_images.py": (
        "The hub file store's save keeps an image a business shows to anyone (storages, not the ORM): no model and no "
        "database; the app that uploads it keeps its own row or name."
    ),
    "base/files.py": (
        "The Files module writes the business's files with Django's Storage API on STORAGES['hub_files'] (save, "
        "delete) under the hub's prefix: no model and no database (it imports neither, "
        "base/tests/test_files.py::test_files_touches_no_model_nor_database); only base.file.* operations reach it."
    ),
}

#: Attributes that are a model's manager: ``Model.objects…`` is always the ORM.
MANAGERS = frozenset({"objects", "_default_manager", "_base_manager"})
#: Methods only a QuerySet, a manager or a model instance has (sync and async). Left out because
#: dicts, sets, strings or paths share them: ``get``, ``update``, ``values``, ``count``,
#: ``exists``, ``iterator``, ``add``, ``remove``, ``set``, ``clear``.
ORM_METHODS = frozenset(
    {
        "all", "filter", "exclude", "order_by", "distinct", "only", "defer", "first", "last",
        "latest", "earliest", "select_related", "prefetch_related", "select_for_update",
        "annotate", "aggregate", "values_list", "in_bulk", "bulk_create", "bulk_update",
        "get_or_create", "update_or_create", "raw", "extra", "create", "save", "delete",
        "refresh_from_db",
        "aget", "afirst", "alast", "alatest", "aearliest", "acount", "aexists", "acontains",
        "aaggregate", "ain_bulk", "aiterator", "acreate", "aget_or_create",
        "aupdate_or_create", "abulk_create", "abulk_update", "aupdate", "adelete", "asave",
        "arefresh_from_db",
    }
)  # fmt: skip
#: Stores with ``save``/``delete``/``create`` of their own that are not the ORM.
NON_ORM_RECEIVERS = frozenset({"session", "cache"})
#: ``django.db`` handles that reach the database without a model.
DB_HANDLES = frozenset({"connection", "connections", "transaction", "router"})
#: Query types: code that builds or passes QuerySets around.
ORM_TYPES = frozenset({"QuerySet", "Manager", "BaseManager"})
ORM_SHORTCUTS = frozenset(
    {"get_object_or_404", "get_list_or_404", "aget_object_or_404", "aget_list_or_404"}
)

# ── (b) Who may choose a database alias ────────────────────────────────────────────────────────

#: Files that may choose an alias by hand, each with its reason.
ALIAS_EXCEPTIONS: dict[str, str] = {
    "base/health.py": READYZ_REASON,
    "base/registry.py": (
        "The host gate reads the registry's row of the Host's slug (404, 410, 503) before any operation runs, "
        "so it cannot go through one; read only, one indexed lookup; its writes are base.services' operations."
    ),
    "base/approval_spend.py": APPROVAL_SPEND_REASON,
    "base/tenancy/migrator/__init__.py": MIGRATOR_ALIAS_REASON,
    "base/tenancy/migrator/control_database.py": MIGRATOR_ALIAS_REASON,
    "base/tenancy/migrator/hub_templates.py": MIGRATOR_ALIAS_REASON,
    "base/tenancy/migrator/schema.py": MIGRATOR_ALIAS_REASON,
    "base/tenancy/migrator/servers.py": MIGRATOR_ALIAS_REASON,
    "base/catalog/register_apps.py": SHARED_CATALOG_REASON,
    "base/tenancy/bootstrap.py": "bootstrap runs once as the RDS master before any app database exists.",
    "base/tenancy/identity.py": TENANCY_IDENTITY_REASON,
}
#: Session-level advisory locks (not the ``_xact_`` ones): PgBouncer in transaction mode loses them.
SESSION_LOCK_RE = re.compile(r"\bpg_(?:try_)?advisory_lock(?:_shared)?\s*\(")

# ── (d) Hub aliases ────────────────────────────────────────────────────────────────────────────

#: ``hub_<hex>`` (a hub), ``hub_<hex>__ddl`` and ``<db_name>__ddl`` (its migrator), ``demo_…`` and ``hub_template…``
#: (the templates); the control database is ``default``.
HUB_ALIAS_PREFIXES = ("hub_", "demo_")
DDL_ALIAS_SUFFIX = "__ddl"


def is_hub_alias(alias: str) -> bool:
    return alias.startswith(HUB_ALIAS_PREFIXES) or alias.endswith(DDL_ALIAS_SUFFIX)


def source_files(root: Path) -> list[PurePosixPath]:
    """Every ``.py`` under ``base/`` and ``apps/`` (relative to ``root``) outside a ``tests/`` package."""
    files = []
    for top in SOURCE_ROOTS:
        for path in sorted((root / top).rglob("*.py")):
            relative = PurePosixPath(path.relative_to(root).as_posix())
            if "tests" not in relative.parts:
                files.append(relative)
    return files


def is_migration(path: PurePosixPath) -> bool:
    return "migrations" in path.parts


def orm_rule_applies(path: PurePosixPath) -> bool:
    """Whether rule (a) reads ``path``: not a door, an owner, a migration or an exception."""
    return not (
        is_door(path)
        or path.name in ORM_OWNERS
        or is_schema_module(path)
        or ADMIN_PART.fullmatch(path.name)
        or is_migration(path)
        or str(path) in ORM_EXCEPTIONS
    )


def _dotted(node: ast.AST) -> str | None:
    """``django.db.connection`` for that chain of names; ``None`` for anything else."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        head = _dotted(node.value)
        return f"{head}.{node.attr}" if head else None
    return None


def _receiver_name(node: ast.AST) -> str | None:
    """The last name of what a method is called on: ``session`` for ``request.session.save()``."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_db_handle(dotted: str) -> bool:
    parts = dotted.split(".")
    return parts[:2] == ["django", "db"] and len(parts) > 2 and parts[2] in DB_HANDLES


def orm_touches(source: str) -> list[tuple[int, str]]:  # noqa: C901
    """``(line, what)`` for every place in ``source`` that reaches the ORM or the database."""
    found: set[tuple[int, str]] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found |= {
                (node.lineno, a.name)
                for a in node.names
                if a.name == "django.db" or _is_db_handle(a.name)
            }
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                name = f"{node.module}.{alias.name}"
                if _is_db_handle(name):
                    found.add((node.lineno, name))
                elif (
                    node.module.startswith("django.db.models")
                    and alias.name in ORM_TYPES
                ) or (
                    node.module == "django.shortcuts" and alias.name in ORM_SHORTCUTS
                ):
                    found.add((node.lineno, alias.name))
        elif isinstance(node, ast.Attribute):
            dotted = _dotted(node)
            receiver = _receiver_name(node.value)
            if node.attr in MANAGERS:
                found.add((node.lineno, f".{node.attr}"))
            elif (receiver == "models" and node.attr in ORM_TYPES) or (
                receiver == "shortcuts" and node.attr in ORM_SHORTCUTS
            ):
                found.add((node.lineno, node.attr))
            elif dotted and _is_db_handle(dotted):
                found.add((node.lineno, dotted))
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ORM_METHODS
            and _receiver_name(node.func.value) not in NON_ORM_RECEIVERS
        ):
            found.add((node.func.end_lineno or node.lineno, f".{node.func.attr}("))
    return sorted(found)


def _is_schema_editor_alias(node: ast.AST) -> bool:
    """``<schema_editor>.connection.alias``: the alias a ``RunPython`` migration is running on."""
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "alias"
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "connection"
        and isinstance(node.value.value, ast.Name)
    )


def alias_touches(source: str, *, in_migration: bool = False) -> list[tuple[int, str]]:
    """``(line, what)`` for every alias chosen by hand, session lock or ``ATOMIC_REQUESTS`` in ``source``."""
    found: set[tuple[int, str]] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.keyword) and node.arg == "using":
            found.add((node.lineno, "using="))
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "using"
        ):
            allowed = (
                in_migration
                and len(node.args) == 1
                and not node.keywords
                and _is_schema_editor_alias(node.args[0])
            )
            if not allowed:
                found.add((node.func.end_lineno or node.lineno, ".using("))
        elif (
            isinstance(node, ast.Subscript)
            and _receiver_name(node.value) == "connections"
        ):
            found.add((node.lineno, "connections["))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if SESSION_LOCK_RE.search(node.value):
                found.add((node.lineno, "pg_advisory_lock("))
            if node.value == "ATOMIC_REQUESTS":
                found.add((node.lineno, "ATOMIC_REQUESTS"))
        elif (isinstance(node, ast.Name) and node.id == "ATOMIC_REQUESTS") or (
            isinstance(node, ast.Attribute) and node.attr == "ATOMIC_REQUESTS"
        ):
            found.add((node.lineno, "ATOMIC_REQUESTS"))
    return sorted(found)


def generic_fk_touches(source: str) -> list[tuple[int, str]]:
    """``(line, "GenericForeignKey")`` for every import of or reference to it in ``source``."""
    found: set[tuple[int, str]] = set()
    for node in ast.walk(ast.parse(source)):
        if (
            (
                isinstance(node, ast.alias)
                and node.name.rsplit(".", 1)[-1] == "GenericForeignKey"
            )
            or (isinstance(node, ast.Name) and node.id == "GenericForeignKey")
            or (isinstance(node, ast.Attribute) and node.attr == "GenericForeignKey")
        ):
            found.add((node.lineno, "GenericForeignKey"))
    return sorted(found)


def database_problems(databases: dict) -> list[str]:
    """What breaks PgBouncer or ``@operation``'s transaction in ``DATABASES``; empty when nothing does."""
    problems = []
    for alias, db in databases.items():
        if is_hub_alias(alias):
            options = db.get("OPTIONS") or {}
            if options.get("pool"):
                problems.append(f"{alias}: OPTIONS['pool']")
            max_age = db.get("CONN_MAX_AGE", 0)
            if max_age is None or max_age > 0:
                problems.append(f"{alias}: CONN_MAX_AGE={max_age}")
            if not db.get("DISABLE_SERVER_SIDE_CURSORS"):
                problems.append(f"{alias}: server-side cursors on")
            # Django leaves it unset and psycopg 3 then prepares on the fifth run, which PgBouncer in transaction mode
            # (max_prepared_statements=0) loses: it must be there, None. A __ddl alias is direct, to the writer.
            if not alias.endswith(DDL_ALIAS_SUFFIX) and (
                "prepare_threshold" not in options or options["prepare_threshold"] is not None
            ):
                problems.append(f"{alias}: prepare_threshold={options.get('prepare_threshold', 'unset (psycopg: 5)')}")
        if db.get("ATOMIC_REQUESTS"):
            problems.append(f"{alias}: ATOMIC_REQUESTS")
    return problems


# ── (f) The tests read the clock when they run ─────────────────────────────────────────────────

#: What reads the clock: ``timezone.localdate()``, ``localtime()`` and ``now()``, ``date.today()`` and
#: ``datetime.utcnow()``.
CLOCK_CALLS = frozenset({"localdate", "localtime", "now", "today", "utcnow"})
#: Folders the walk of the suite never enters, as ``pytest.ini``'s ``norecursedirs``: ``packages/`` holds the ``live``
#: and ``ui`` submodules, each with its own CI; ``node_modules`` and the hidden ones (``.venv``) are not the Hub's code.
SUITE_SKIPS = frozenset({"packages", "node_modules"})


class _ClockAtImport(ast.NodeVisitor):
    def __init__(self):
        self.found: set[tuple[int, str]] = set()

    def visit_Call(self, node: ast.Call):
        name = _receiver_name(node.func)
        if name in CLOCK_CALLS:
            self.found.add((node.lineno, f"{name}()"))
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
        # The body runs with the test; the decorators and the default values, at import.
        for expr in (*node.decorator_list, *node.args.defaults, *node.args.kw_defaults):
            if expr is not None:
                self.visit(expr)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node: ast.Lambda):
        for expr in (*node.args.defaults, *node.args.kw_defaults):
            if expr is not None:
                self.visit(expr)


def clock_at_import(source: str) -> list[tuple[int, str]]:
    """``(line, what)`` for every read of the clock that runs when ``source`` is imported.

    pytest imports every test module before it runs any, so a ``TODAY = timezone.localdate()`` at module level is the
    day of the collection: a run that crosses midnight (Madrid) compares it with the day the operations take
    (``timezone.localdate()`` when they run), and one that crosses New Year's Eve expects last year's numbers, and the
    suite falls. A test asks for the ``today`` fixture, or reads the clock inside its body. What runs at import: the
    bodies of modules and classes, decorators (``@pytest.mark.parametrize`` values included) and default values; the
    body of a function or of a lambda runs with the test.
    """
    visitor = _ClockAtImport()
    visitor.visit(ast.parse(source))
    return sorted(visitor.found)


def suite_files(root: Path) -> list[PurePosixPath]:
    """Every ``test_*.py`` and ``conftest.py`` under ``root`` (relative to it), and every ``.py`` of a ``tests`` folder
    (``factories.py``, ``fake_gateway.py``: the tests import them, so they run at the collection too), outside
    ``SUITE_SKIPS`` and hidden folders."""
    files = []
    for folder, folders, names in root.walk():
        folders[:] = [name for name in folders if name not in SUITE_SKIPS and not name.startswith(".")]
        in_tests = "tests" in folder.relative_to(root).parts
        files += [
            PurePosixPath((folder / name).relative_to(root).as_posix())
            for name in names
            if name.endswith(".py") and (in_tests or name == "conftest.py" or name.startswith("test_"))
        ]
    return sorted(files)


# ── Positive controls: each check sees what it must, and nothing else ──────────────────────────

ORM_OFFENDER = """\
import django.db
from django.db import connection, models, transaction
from django.db.models import Count, QuerySet
from django.shortcuts import get_object_or_404


async def view(request, pk):
    item = Item.objects.get(pk=pk)
    lines = item.lines.filter(qty__gt=1).select_for_update()
    item.save(update_fields=["name"])
    await item.adelete()
    get_object_or_404(Item, pk=pk)
    return django.db.connections
"""

ORM_LOOKALIKES = """\
import multiprocessing
from multiprocessing import Manager

from django.db import models
from django.db.models import Count, Q


def view(request, payload, names, data):
    Manager(), multiprocessing.Manager()
    payload.get("error")
    request.POST.get("next")
    request.session.save()
    request.session.delete()
    cache.delete("key")
    names.add("b")
    data.update(a=1)
    return all(x for x in names), filter(None, names), Count("id"), Q(a=1)
"""


def test_orm_scanner_sees_managers_queryset_methods_writes_and_database_handles():
    assert orm_touches(ORM_OFFENDER) == [
        (1, "django.db"),
        (2, "django.db.connection"),
        (2, "django.db.transaction"),
        (3, "QuerySet"),
        (4, "get_object_or_404"),
        (8, ".objects"),
        (9, ".filter("),
        (9, ".select_for_update("),
        (10, ".save("),
        (11, ".adelete("),
        (13, "django.db.connections"),
    ]


def test_orm_scanner_ignores_dicts_sets_sessions_caches_and_builtins():
    assert orm_touches(ORM_LOOKALIKES) == []


def test_orm_rule_skips_the_doors_the_owners_migrations_and_the_exceptions():
    applies = {
        path: orm_rule_applies(PurePosixPath(path))
        for path in [
            "apps/demo/services.py",
            "apps/demo/queries.py",
            "apps/demo/models.py",
            "base/models/access.py",
            "apps/demo/models/__init__.py",
            "apps/demo/models/kinds/tag.py",
            "apps/demo/admin.py",
            "control/admin_clusters.py",
            "apps/demo/migrations/0001_initial.py",
            "base/permissions.py",
            "apps/demo/api.py",
            "apps/demo/live.py",
            "apps/demo/schemas.py",
            "apps/demo/administration.py",
            "base/middleware.py",
            "base/management/commands/seed.py",
        ]
    }

    assert [path for path, scanned in applies.items() if scanned] == [
        "apps/demo/models/kinds/tag.py",
        "apps/demo/api.py",
        "apps/demo/live.py",
        "apps/demo/schemas.py",
        "apps/demo/administration.py",
        "base/middleware.py",
        "base/management/commands/seed.py",
    ]


ALIAS_OFFENDER = """\
from django.db import connections
Item.objects.using("hub_0190")
Item.objects.using(schema_editor.connection.alias)
item.save(using="default")
with connections["hub_0190"].cursor() as cursor:
    cursor.execute("SELECT pg_advisory_lock(42)")
    cursor.execute("SELECT pg_advisory_xact_lock(42)")
    cursor.execute("SELECT pg_try_advisory_lock(42)")
settings.DATABASES["default"]["ATOMIC_REQUESTS"] = True
"""


def test_alias_scanner_sees_using_connections_session_locks_and_atomic_requests():
    assert alias_touches(ALIAS_OFFENDER) == [
        (2, ".using("),
        (3, ".using("),
        (4, "using="),
        (5, "connections["),
        (6, "pg_advisory_lock("),
        (8, "pg_advisory_lock("),
        (9, "ATOMIC_REQUESTS"),
    ]


def test_alias_scanner_lets_a_migration_use_only_the_schema_editors_alias():
    assert alias_touches(ALIAS_OFFENDER, in_migration=True) == [
        (2, ".using("),
        (4, "using="),
        (5, "connections["),
        (6, "pg_advisory_lock("),
        (8, "pg_advisory_lock("),
        (9, "ATOMIC_REQUESTS"),
    ]


ALIAS_IN_A_VARIABLE = """\
alias = schema_editor.connection.alias
Item.objects.using(alias)
"""


def test_alias_scanner_rejects_the_schema_editors_alias_through_a_variable_in_a_migration():
    # The only exception is the inline form: a variable can be reassigned, so it is not proof.
    assert alias_touches(ALIAS_IN_A_VARIABLE, in_migration=True) == [(2, ".using(")]


GFK_OFFENDER = """\
from django.contrib.contenttypes import fields
from django.contrib.contenttypes.fields import GenericForeignKey as GFK


class Tag(models.Model):
    target = GFK("content_type", "object_id")
    other = fields.GenericForeignKey()
"""


def test_generic_fk_scanner_sees_imports_and_references():
    assert generic_fk_touches(GFK_OFFENDER) == [
        (2, "GenericForeignKey"),
        (7, "GenericForeignKey"),
    ]


def test_database_check_sees_pools_persistent_connections_and_server_cursors_on_hub_aliases():
    databases = {
        # The control database may pool: it is reached directly, not through PgBouncer.
        "default": {"NAME": "hub", "OPTIONS": {"pool": {"min_size": 1}}},
        "hub_0190a1b2c3d4": {
            "NAME": "hub_0190a1b2c3d4",
            "OPTIONS": {"pool": True},
            "CONN_MAX_AGE": 60,
        },
        "hub_0190a1b2c3d4__ddl": {
            "NAME": "hub_0190a1b2c3d4",
            "CONN_MAX_AGE": None,
            "DISABLE_SERVER_SIDE_CURSORS": True,
        },
        "hub_template": {
            "NAME": "hub_template",
            "CONN_MAX_AGE": 0,
            "DISABLE_SERVER_SIDE_CURSORS": True,
            "OPTIONS": {"prepare_threshold": None},
        },
        "hub_template_restaurant": {
            "NAME": "hub_template_restaurant",
            "CONN_MAX_AGE": 0,
            "DISABLE_SERVER_SIDE_CURSORS": True,
        },
        "demo_0190a1b2c3d4": {
            "NAME": "demo_0190a1b2c3d4",
            "CONN_MAX_AGE": 0,
            "DISABLE_SERVER_SIDE_CURSORS": True,
            "OPTIONS": {"prepare_threshold": 5},
        },
        "pre_hub_0190a1b2c3d4__ddl": {"NAME": "pre_hub_0190a1b2c3d4", "CONN_MAX_AGE": 0},
        "other": {"NAME": "other", "ATOMIC_REQUESTS": True},
    }

    assert database_problems(databases) == [
        "hub_0190a1b2c3d4: OPTIONS['pool']",
        "hub_0190a1b2c3d4: CONN_MAX_AGE=60",
        "hub_0190a1b2c3d4: server-side cursors on",
        "hub_0190a1b2c3d4: prepare_threshold=unset (psycopg: 5)",
        "hub_0190a1b2c3d4__ddl: CONN_MAX_AGE=None",
        "hub_template_restaurant: prepare_threshold=unset (psycopg: 5)",
        "demo_0190a1b2c3d4: prepare_threshold=5",
        "pre_hub_0190a1b2c3d4__ddl: server-side cursors on",
        "other: ATOMIC_REQUESTS",
    ]


def test_the_scan_reads_the_real_source_and_finds_the_orm_behind_the_doors():
    files = source_files(HUB_DIR)

    assert PurePosixPath("base/services/__init__.py") in files
    assert PurePosixPath("apps/demo/queries.py") in files
    assert not [path for path in files if "tests" in path.parts]
    # Real code, real ORM: a scanner that went blind would let every check below pass.
    assert orm_touches((HUB_DIR / "apps/demo/services.py").read_text())


# ── The real tree ──────────────────────────────────────────────────────────────────────────────


def _offenders(check, files) -> list[str]:
    return [f"{path}:{line} {what}" for path in files for line, what in check(path)]


def test_only_the_doors_touch_the_orm():
    files = [path for path in source_files(HUB_DIR) if orm_rule_applies(path)]

    offenders = _offenders(
        lambda path: orm_touches((HUB_DIR / path).read_text()), files
    )

    assert offenders == [], (
        "Only an app's services and queries touch the ORM: move these reads and "
        f"writes behind an @operation, or add a reasoned entry to ORM_EXCEPTIONS: {offenders}"
    )


def test_no_alias_is_chosen_by_hand():
    files = [
        path for path in source_files(HUB_DIR) if str(path) not in ALIAS_EXCEPTIONS
    ]

    offenders = _offenders(
        lambda path: alias_touches(
            (HUB_DIR / path).read_text(), in_migration=is_migration(path)
        ),
        files,
    )

    assert offenders == [], (
        f"The hub's database is chosen by use_hub and the TenantRouter, never by hand: {offenders}"
    )


def test_no_generic_foreign_key():
    offenders = _offenders(
        lambda path: generic_fk_touches((HUB_DIR / path).read_text()),
        source_files(HUB_DIR),
    )

    assert offenders == [], (
        f"No GenericForeignKey in a hub's models: {offenders}"
    )


def test_hub_aliases_go_through_pgbouncer_safely():
    assert database_problems(settings.DATABASES) == []


# ── (f) The tests read the clock when they run: positive and negative controls ─────────────────

CLOCK_OFFENDER = """\
TODAY = timezone.localdate()
DAY = dt.date.today().strftime('%Y%m%d')
class TestSeries:
    stamp = timezone.now()
@pytest.mark.parametrize('day', [pytest.param(timezone.localdate(), id='today')])
def test_a(day): ...
async def test_b(at=dt.datetime.utcnow()): ...
ASK = {'content': f'FACT-{timezone.localdate().year}'}
OPENING = timezone.localtime().replace(hour=9)
NUMBER = f'TSK-{timezone.localdate():%Y%m%d}'
TICKET = f'TICKET-{timezone.localdate().year}-000001'
def test_c(*, at=now()): ...
LATER = lambda day=date.today(): day
@pytest.mark.parametrize('at', [timezone.localtime()])
class TestTill:
    def test_d(self, at): ...
"""
CLOCK_LOOKALIKES = """\
\"\"\"TODAY = timezone.localdate() at import is the day of the collection.\"\"\"
def test_a():
    today = timezone.localdate()
async def test_b():
    now = timezone.now()
class TestSeries:
    def test_c(self):
        assert dt.date.today()
    factory = staticmethod(lambda: timezone.localtime())
later = lambda: timezone.localdate()
def test_d(clock=lambda: dt.datetime.utcnow()): ...
@pytest.fixture
def today():
    return timezone.localdate()
"""


def test_the_clock_scanner_sees_the_clock_read_at_import():
    assert clock_at_import(CLOCK_OFFENDER) == [
        (1, "localdate()"),
        (2, "today()"),
        (4, "now()"),
        (5, "localdate()"),
        (7, "utcnow()"),
        (8, "localdate()"),
        (9, "localtime()"),
        (10, "localdate()"),
        (11, "localdate()"),
        (12, "now()"),
        (13, "today()"),
        (14, "localtime()"),
    ]


def test_the_clock_scanner_lets_a_test_read_the_clock_when_it_runs():
    assert clock_at_import(CLOCK_LOOKALIKES) == []


def test_the_suite_walk_reads_every_test_module_and_conftest_but_the_submodules(tmp_path):
    reads_at_import = "TODAY = timezone.localdate()\n"
    planted = {
        "conftest.py": "import pytest\nNOW = timezone.now()\n",
        "apps/demo/tests/test_report.py": reads_at_import,
        "apps/demo/tests/conftest.py": "def today():\n    return timezone.localdate()\n",
        "apps/demo/services.py": reads_at_import,
        "apps/demo/tests/factories.py": reads_at_import,
        "packages/live/tests/test_broker.py": reads_at_import,
        ".venv/lib/site-packages/pkg/tests/test_pkg.py": reads_at_import,
        "frontend/node_modules/pkg/test_pkg.py": reads_at_import,
    }
    for name, source in planted.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(source)

    files = suite_files(tmp_path)

    # A helper of a tests folder (``factories.py``) is imported with the tests that import it, at the collection.
    assert files == [
        PurePosixPath("apps/demo/tests/conftest.py"),
        PurePosixPath("apps/demo/tests/factories.py"),
        PurePosixPath("apps/demo/tests/test_report.py"),
        PurePosixPath("conftest.py"),
    ]
    assert _offenders(lambda path: clock_at_import((tmp_path / path).read_text()), files) == [
        "apps/demo/tests/factories.py:1 localdate()",
        "apps/demo/tests/test_report.py:1 localdate()",
        "conftest.py:2 now()",
    ]


# ── (f) The tests read the clock when they run: the real tree ──────────────────────────────────


def test_no_test_reads_the_clock_at_import():
    files = suite_files(HUB_DIR)
    # A walk gone blind would let the check pass: it reaches the root conftest, a module's tests, a helper of a tests
    # folder and this very file, and never a submodule.
    assert {
        PurePosixPath("conftest.py"),
        PurePosixPath("apps/sale/tests/conftest.py"),
        PurePosixPath("base/tests/fake_gateway.py"),
        PurePosixPath("tests/test_guardrails.py"),
    } <= set(files)
    assert not [path for path in files if path.parts[0] == "packages"]

    offenders = _offenders(lambda path: clock_at_import((HUB_DIR / path).read_text()), files)

    assert offenders == [], (
        "pytest imports every test module before it runs any, so a date read at import is the day of the collection "
        "and a run that crosses midnight or New Year's Eve compares it with the next one: ask for the `today` fixture, "
        f"or read the clock inside the test: {offenders}"
    )


# ── (h) A hub's model never links to control's ────────────────────────────────────────────────────────────────────


def control_links(models, classify) -> list[str]:
    """``<model>.<field> -> <target>`` for every foreign key, one-to-one or many-to-many of a hub's model (``hub`` or
    ``contextual``) to a model of control's database: ``settings.AUTH_USER_MODEL`` and the rest of ``auth``,
    ``control``, ``base.Membership``… A key between two databases does not exist, so no hub's database could hold
    that model's table: a person of the business is a ``base.HubUser``. ``classify`` is
    ``base.tenancy.inventory.classify``."""
    from django.db.models import Field

    from base.tenancy import inventory

    found = []
    for model in models:
        if classify(model) not in (inventory.HUB, inventory.CONTEXTUAL):
            continue
        for field in model._meta.get_fields(include_hidden=True):
            # Forward fields only (a reverse relation is no Field): a key, a one-to-one or a many-to-many.
            if not (isinstance(field, Field) and field.is_relation) or field.related_model is None:
                continue
            if classify(field.related_model) == inventory.CONTROL:
                found.append(f"{model._meta.label_lower}.{field.name} -> {field.related_model._meta.label_lower}")
    return sorted(found)


def _made_up_hub_model(label: str, **fields):
    """A stand-in for a hub's model named ``label`` with ``fields`` (name: an unbound Django field)."""
    from types import SimpleNamespace

    for name, field in fields.items():
        field.set_attributes_from_name(name)
    return SimpleNamespace(
        _meta=SimpleNamespace(label_lower=label, get_fields=lambda include_hidden=False: list(fields.values()))
    )


def test_control_links_finds_every_kind_of_link_from_a_hub_model_to_a_control_one():
    from django.contrib.auth import get_user_model
    from django.db import models as django_models

    from base.models import Membership
    from base.models.profile import Profile
    from base.tenancy import inventory
    from control.models import Hub

    offender = _made_up_hub_model(
        "staff.offender",
        user=django_models.ForeignKey(get_user_model(), on_delete=django_models.CASCADE),
        hub=django_models.OneToOneField(Hub, on_delete=django_models.CASCADE),
        memberships=django_models.ManyToManyField(Membership),
        profile=django_models.ForeignKey(Profile, on_delete=django_models.CASCADE),
        name=django_models.CharField(max_length=10),
    )
    controls_own = _made_up_hub_model(
        "control.offender", user=django_models.ForeignKey(get_user_model(), on_delete=django_models.CASCADE)
    )
    hubs_classes = {id(offender): inventory.HUB, id(controls_own): inventory.CONTROL}

    def classify(model):
        return hubs_classes.get(id(model)) or inventory.classify(model)

    # The key to a hub's own model (Profile) and the plain column are not links to control; a control model's are not
    # a hub's.
    assert control_links([offender, controls_own], classify) == [
        "staff.offender.hub -> control.hub",
        "staff.offender.memberships -> base.membership",
        "staff.offender.user -> auth.user",
    ]


def test_no_hub_model_links_to_a_control_model():
    from django.apps import apps

    from base.tenancy import inventory

    models = apps.get_models(include_auto_created=True)
    # A walk gone blind would let the check pass: it reaches the modules and the platform's models.
    assert {"staff.member", "base.profile", "control.hub"} <= {model._meta.label_lower for model in models}

    offenders = control_links(models, inventory.classify)

    assert offenders == [], (
        "A hub's model lives in the hub's database, where control's tables are not: link a person of the business "
        f"to base.HubUser, never to settings.AUTH_USER_MODEL, auth, control or base.Membership: {offenders}"
    )
