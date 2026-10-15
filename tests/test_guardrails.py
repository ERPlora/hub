"""Guardrails of the Hub's source (round 11 plan, H3; CLAUDE.md «Tenencia del Hub» and «Un solo
camino hacia el servidor»; PLAN-DB §14, items 5 and 10). Static and fast: each check is a pure
function over source text (or the ``DATABASES`` dict), proven by a made-up offender (the positive
control), then run over ``base/`` and ``apps/`` (outside ``tests/``).

(a) Only the doors touch the ORM: managers, QuerySet methods, model writes, ``transaction``,
    ``connection``, ``QuerySet``/``Manager`` and ``get_object_or_404`` appear only in
    ``services.py`` and ``queries.py`` (plus the owners and exceptions of ``ORM_OWNERS`` and
    ``ORM_EXCEPTIONS``, each with its reason). Known limit: it reads shape, not types, so methods
    shared with dicts, sets, strings or paths (``get``, ``update``, ``count``, ``exists``, ``add``…)
    are only caught when they hang from a manager (``Model.objects.get``).
(b) No alias chosen by hand: no ``using=``, ``.using(`` or ``connections[``; no session
    ``pg_advisory_lock(`` (PgBouncer) and no ``ATOMIC_REQUESTS`` (the transaction is
    ``@operation``'s). Single exceptions: ``.using(<schema_editor>.connection.alias)`` in a migration
    (``RunPython``), ``base/tenancy/migrator.py`` and ``base/catalog.py`` (the ``shared`` alias).
(c) No ``GenericForeignKey``: a hub's models only reference what lives in the same hub database.
(d) Hub aliases (``hub_<hex>``, ``hub_<hex>__ddl``, ``hub_template…``) go through PgBouncer in
    transaction mode: no ``pool``, ``CONN_MAX_AGE`` 0 and no server-side cursors; no alias has
    ``ATOMIC_REQUESTS``.

Every ninja route bound to an operation is ``config/tests/test_api.py`` (``ensure_api_parity``);
``/admin/`` on a tenant's host → 404 is ``base/tests/test_middleware.py``.
"""

import ast
import re
from pathlib import Path, PurePosixPath

from django.conf import settings

HUB_DIR = Path(__file__).resolve().parent.parent
SOURCE_ROOTS = ("base", "apps")

# ── (a) Who may touch the ORM ──────────────────────────────────────────────────────────────────

#: The doors (CLAUDE.md «Un solo camino hacia el servidor»): reads in ``queries.py``, writes in
#: ``services.py``; their ``@operation`` applies hub, active app, permission and transaction.
ORM_DOORS = frozenset({"services.py", "queries.py"})
#: Owners of the ORM that are no path to the data from the API: ``models.py`` declares the schema
#: (managers, QuerySets, constraints with ``Q``); ``admin.py`` is Django's admin, the second write
#: path the plan accepts (PLAN-DB §14.10, §16; PLAN §17–§18), whose actions call ``services.py``.
ORM_OWNERS = frozenset({"models.py", "admin.py"})
#: Files outside the doors that may touch the ORM, each with its reason. Not here on purpose:
#: ``live.py`` (it only names events), ``api.py`` (one operation per route), ``auth.py`` (reads
#: ``Membership.Role``, an enum), ``auth_views.py`` (opens the session through ``services``),
#: ``middleware.py`` (only ``request.user``, loaded by Django), ``management/commands/`` (all by
#: API, working rules §4: a command calls an operation).
#: ``/readyz`` (PLAN-AWS §5) is the deploy gate: it must reach the database without an operation.
READYZ_REASON = (
    "/readyz reads django_migrations on the control database (connections[DEFAULT_DB_ALIAS], "
    "MigrationExecutor): a platform probe that never reads a hub's data."
)
#: Round 16 (PLAN §21; spec §3.3): the registry of the Hub's modules in the SaaS's ``shared`` schema.
SHARED_CATALOG_REASON = (
    "register_apps writes shared.app and shared.app_doc on the `shared` alias for no hub and no user, "
    "so it is no @operation; it is the only module that imports shared.models and names that alias "
    "(base/tests/test_shared_lint.py), and the hub_shared role (SELECT, INSERT, UPDATE on those two "
    "tables) is the boundary."
)
ORM_EXCEPTIONS: dict[str, str] = {
    "base/permissions.py": (
        "The context builder reads Membership and a fresh copy of the user before any operation "
        "runs, so it cannot go through one; read only; phase 2 replaces it with the hub's staff."
    ),
    "base/health.py": READYZ_REASON,
    "base/tenancy/migrator.py": (
        "Phase 2: the only function that changes a hub's schema, through its direct __ddl "
        "connection and the schema lock (CLAUDE.md «Tenencia del Hub»)."
    ),
    "base/catalog.py": SHARED_CATALOG_REASON,
    "base/tenancy/bootstrap.py": "bootstrap runs once as the RDS master before any app database exists.",
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
    "base/tenancy/migrator.py": (
        "Phase 2: the schema migrator opens hub_<hex>__ddl itself and takes the session "
        "pg_advisory_lock of the schema (CLAUDE.md «Tenencia del Hub», PLAN-DB §14.5)."
    ),
    "base/catalog.py": SHARED_CATALOG_REASON,
    "base/tenancy/bootstrap.py": "bootstrap runs once as the RDS master before any app database exists.",
}
#: Session-level advisory locks (not the ``_xact_`` ones): PgBouncer in transaction mode loses them.
SESSION_LOCK_RE = re.compile(r"\bpg_(?:try_)?advisory_lock(?:_shared)?\s*\(")

# ── (d) Hub aliases ────────────────────────────────────────────────────────────────────────────

#: ``hub_<hex>`` (a hub), ``hub_<hex>__ddl`` (its migrator) and ``hub_template…`` (the templates);
#: the control database is ``default``.
HUB_ALIAS_PREFIX = "hub_"


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
        path.name in ORM_DOORS | ORM_OWNERS
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


def orm_touches(source: str) -> list[tuple[int, str]]:
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
        if alias.startswith(HUB_ALIAS_PREFIX):
            if (db.get("OPTIONS") or {}).get("pool"):
                problems.append(f"{alias}: OPTIONS['pool']")
            max_age = db.get("CONN_MAX_AGE", 0)
            if max_age is None or max_age > 0:
                problems.append(f"{alias}: CONN_MAX_AGE={max_age}")
            if not db.get("DISABLE_SERVER_SIDE_CURSORS"):
                problems.append(f"{alias}: server-side cursors on")
        if db.get("ATOMIC_REQUESTS"):
            problems.append(f"{alias}: ATOMIC_REQUESTS")
    return problems


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
            "apps/demo/admin.py",
            "apps/demo/migrations/0001_initial.py",
            "base/permissions.py",
            "apps/demo/api.py",
            "apps/demo/live.py",
            "apps/demo/schemas.py",
            "base/middleware.py",
            "base/management/commands/seed.py",
        ]
    }

    assert [path for path, scanned in applies.items() if scanned] == [
        "apps/demo/api.py",
        "apps/demo/live.py",
        "apps/demo/schemas.py",
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
        },
        "other": {"NAME": "other", "ATOMIC_REQUESTS": True},
    }

    assert database_problems(databases) == [
        "hub_0190a1b2c3d4: OPTIONS['pool']",
        "hub_0190a1b2c3d4: CONN_MAX_AGE=60",
        "hub_0190a1b2c3d4: server-side cursors on",
        "hub_0190a1b2c3d4__ddl: CONN_MAX_AGE=None",
        "other: ATOMIC_REQUESTS",
    ]


def test_the_scan_reads_the_real_source_and_finds_the_orm_behind_the_doors():
    files = source_files(HUB_DIR)

    assert PurePosixPath("base/services.py") in files
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
        "Only services.py and queries.py touch the ORM (CLAUDE.md, PLAN §14): move these reads and "
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
        "The hub's database is chosen by use_hub and the TenantRouter, never by hand (CLAUDE.md "
        f"«Tenencia del Hub», PLAN-DB §14.5): {offenders}"
    )


def test_no_generic_foreign_key():
    offenders = _offenders(
        lambda path: generic_fk_touches((HUB_DIR / path).read_text()),
        source_files(HUB_DIR),
    )

    assert offenders == [], (
        f"No GenericForeignKey in a hub's models (CLAUDE.md, PLAN-DB §14.5): {offenders}"
    )


def test_hub_aliases_go_through_pgbouncer_safely():
    assert database_problems(settings.DATABASES) == []
