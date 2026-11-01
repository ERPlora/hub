"""The cut of S5: every business phase 1 kept in control's database gets its own (plan 2026-10-22-fase-2-tenencia
§3 «S5»; round 2026-11-01 of PLAN-DB).

Phase 1 kept every business in control's database (``Hub.db_name`` empty), its apps' tables shared by all of them
with no column saying whose a row is. Since S5 nothing serves a business there (its host answers 503, the worker
skips it): ``manage.py cut_shared_hubs`` gives each one, by name, its own database, in one of three modes:

- :data:`RECREATE`: its database cloned from its vertical's template (as a sign-up's, ``base.tenancy.provision``),
  brought to the code's leaf and seeded with the SaaS's photo kept on its row (its people, the blocks of its apps on);
  nothing of control's is copied;
- :data:`COPY_ALL`: the same, and before the seeding every row control's tables of the hubs' apps hold is copied into
  it (:func:`copy_rows`), a table at a time in short transactions, the tables a table points to first; of the outbox,
  only its own events and their deliveries. In production those tables hold one business's data in practice, so this
  is done once, for one business (``services.copy_all_went_to``);
- :data:`SKIP`: a cancelled business is left without a database: ``base.hub.restore`` makes it one from nothing if it
  comes back.

Each cut holds the hub's ``hub_due`` lease (another cut, or the worker, never works on it at once), keeps it ``ready``
and its ``db_name`` empty until its last step (``base.hub.cut_finish``: ``db_name``, its schema and ``base.hub.cut``
in control's outbox, in one transaction), so its host answers 503 throughout. A cut that breaks drops what it made and
leaves the business as it was: the next run does it again from the start. A business that already has its own
database is left alone. Control's tables are never emptied nor dropped: a later contract migration renames them.

Control is read, and the new database written, by the migrator on direct connections to their writers
(``base.tenancy.connections.migrator_conninfo``), as ``pg_dump`` and the migrator do.
"""

import logging
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import psycopg
from django.apps import apps as django_apps
from django.utils import timezone
from live.context import system_context
from live.models import OutboxEvent
from live.operations import get as get_operation
from psycopg import sql

from base import registry, services
from base.models import EventDelivery, HubIdentity
from base.schemas import HubCutFinishIn
from base.tenancy import connections as tenancy_connections
from base.tenancy import identity, inventory, migrator, names, ops, provision
from base.tenancy.context import HUB_SCOPE_KIND, use_control, use_hub
from control.models import Hub

logger = logging.getLogger(__name__)

RECREATE = "recreate"
COPY_ALL = "copy_all"
SKIP = "skip"
#: How each mode is named on the command line and in what it says.
MODE_NAMES = {COPY_ALL: "copy-all", RECREATE: "recreate", SKIP: "skip"}
#: How long the lease of a hub being cut lasts; every step renews it.
LEASE = provision.LEASE
#: What a hub's database keeps of its template and never takes from control: its identity (and ``django_migrations``,
#: no model's).
KEPT_TABLES = frozenset({HubIdentity._meta.db_table})
_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")


class CutError(RuntimeError):
    """A cut that could not be done, with why in a line; the business is left as it was."""


@dataclass(frozen=True)
class Outcome:
    """What a cut did: the business, its mode, its new database, the rows copied by table and how long it took."""

    slug: str
    mode: str
    database: str
    copied: dict[str, int]
    seconds: float


# ── What is copied, and in which order ────────────────────────────────────────────────────────────────────────────


def tables_to_copy() -> list[str]:
    """Every table of a hub's database that control's may hold rows of: the hubs' apps' and the outbox's, its
    identity aside; sorted."""
    return sorted(
        {
            model._meta.db_table
            for model in django_apps.get_models(include_auto_created=True)
            if model._meta.managed and inventory.classify(model) in (inventory.HUB, inventory.CONTEXTUAL)
        }
        - KEPT_TABLES
    )


def outbox_tables() -> tuple[str, str]:
    """The outbox's events and their deliveries: of these, only the business's own are copied."""
    return OutboxEvent._meta.db_table, EventDelivery._meta.db_table


def _quoted(table: str) -> str:
    if not _IDENTIFIER.match(table):
        raise CutError(f"{table!r} is no table name of ours.")
    return f'"{table}"'


def rows_of(table: str, slug: str) -> tuple[str, list[str]]:
    """The ``WHERE`` that reads ``slug``'s rows of ``table`` in control, with its parameters: every row (``""``) but
    for the outbox, which says whose each event is (its scope) and keeps every business's and the platform's."""
    events, deliveries = outbox_tables()
    own = "scope_kind = %s AND scope_key = %s"
    if table == events:
        return f"WHERE {own}", [HUB_SCOPE_KIND, slug]
    if table == deliveries:
        return f"WHERE event_id IN (SELECT id FROM {_quoted(events)} WHERE {own})", [HUB_SCOPE_KIND, slug]
    return "", []


def copy_order(tables: Iterable[str], points_to: Iterable[tuple[str, str]]) -> list[list[str]]:
    """``tables`` in groups, each copied in one transaction: a table after the tables it points to (``points_to``:
    ``(table, the table one of its foreign keys points to)``), tables that point to each other in one group. The same
    order whatever order they come in."""
    tables = sorted(set(tables))
    known = set(tables)
    points_to = list(points_to)
    parents = {
        table: sorted({parent for child, parent in points_to if child == table and parent in known}) for table in tables
    }
    groups = _strongly_connected(tables, parents)
    group_of = {table: index for index, group in enumerate(groups) for table in group}
    needs = {
        index: {group_of[parent] for table in group for parent in parents[table]} - {index}
        for index, group in enumerate(groups)
    }
    ordered: list[list[str]] = []
    done: set[int] = set()
    while len(done) < len(groups):
        ready = [index for index in range(len(groups)) if index not in done and needs[index] <= done]
        first = min(ready, key=lambda index: groups[index][0])
        ordered.append(groups[first])
        done.add(first)
    return ordered


def _strongly_connected(tables: list[str], parents: dict[str, list[str]]) -> list[list[str]]:
    """Tarjan's strongly connected components of the graph ``table → its parents``, each sorted."""
    index_of: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    groups: list[list[str]] = []
    counter = 0
    for start in tables:
        if start in index_of:
            continue
        work = [(start, iter(parents[start]))]
        index_of[start] = low[start] = counter
        counter += 1
        stack.append(start)
        on_stack.add(start)
        while work:
            node, children = work[-1]
            child = next(children, None)
            if child is not None:
                if child not in index_of:
                    index_of[child] = low[child] = counter
                    counter += 1
                    stack.append(child)
                    on_stack.add(child)
                    work.append((child, iter(parents[child])))
                elif child in on_stack:
                    low[node] = min(low[node], index_of[child])
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[node])
            if low[node] == index_of[node]:
                group = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    group.append(member)
                    if member == node:
                        break
                groups.append(sorted(group))
    return groups


# ── Reading control, writing the new database ─────────────────────────────────────────────────────────────────────


def _connect(dbname: str, cluster=None, **options) -> psycopg.Connection:
    return psycopg.connect(**tenancy_connections.migrator_conninfo(dbname, cluster=cluster), **options)


def _control() -> psycopg.Connection:
    """Control, read by the migrator in one snapshot (repeatable read, read only)."""
    conn = _connect(tenancy_connections.control_name())
    conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
    conn.read_only = True
    return conn


def _tables(conn: psycopg.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}


def _columns(conn: psycopg.Connection, table: str) -> list[str]:
    """``table``'s columns a ``COPY`` may write, in their order (none generated)."""
    return [
        row[0]
        for row in conn.execute(
            "SELECT attname FROM pg_attribute WHERE attrelid = to_regclass(%s) AND attnum > 0 AND NOT attisdropped "
            "AND attgenerated = '' ORDER BY attnum",
            [f"public.{_quoted(table)}"],
        )
    ]


def _foreign_keys(conn: psycopg.Connection) -> list[tuple[str, str]]:
    return [
        (row[0], row[1])
        for row in conn.execute(
            "SELECT child.relname, parent.relname FROM pg_constraint c "
            "JOIN pg_class child ON child.oid = c.conrelid JOIN pg_class parent ON parent.oid = c.confrelid "
            "JOIN pg_namespace n ON n.oid = child.relnamespace WHERE c.contype = 'f' AND n.nspname = 'public'"
        )
    ]


def count_rows(slug: str) -> dict[str, int]:
    """The rows of control's tables a copy into ``slug`` would take, by table (the dry run)."""
    with _control() as source:
        present = _tables(source)
        counted = {table: _count(source, table, slug) for table in tables_to_copy() if table in present}
        source.rollback()
    return counted


def _count(source: psycopg.Connection, table: str, slug: str) -> int:
    """The rows of ``table`` in control that a copy into ``slug`` takes."""
    where, params = rows_of(table, slug)
    query = sql.SQL("SELECT count(*) FROM {} ").format(sql.Identifier(table)) + sql.SQL(where)
    return source.execute(query, params).fetchone()[0]


def copy_rows(hub, *, heartbeat: Callable[[], object] | None = None) -> dict[str, int]:
    """Copy into ``hub``'s new database every row control's tables of the hubs' apps hold (of the outbox, its own
    events and their deliveries); return the rows copied by table.

    Control is read in one snapshot. The tables both databases have are emptied first in the new one (its template's
    rows: a location, its apps off), then filled a group at a time (:func:`copy_order`), each in a short transaction
    of its own with the constraints checked at its COMMIT; only the columns both have. The serial keys go on after the
    rows copied."""
    slug = hub.slug
    with _control() as source, _connect(hub.db_name, hub.cluster, autocommit=True) as target:
        in_control = _tables(source) & set(tables_to_copy())
        present = in_control & _tables(target)
        left_behind = {table: _count(source, table, slug) for table in sorted(in_control - present)}
        left_behind = {table: rows for table, rows in left_behind.items() if rows}
        if left_behind:
            raise CutError(
                "its database lacks tables control holds rows of, nothing is left behind: "
                + ", ".join(f"{table} ({rows})" for table, rows in left_behind.items())
            )
        groups = copy_order(present, _foreign_keys(target))
        if present:
            target.execute(
                sql.SQL("TRUNCATE {} CASCADE").format(sql.SQL(", ").join(map(sql.Identifier, sorted(present))))
            )
        copied: dict[str, int] = {}
        for group in groups:
            with target.transaction():
                target.execute("SET CONSTRAINTS ALL DEFERRED")
                for table in group:
                    copied[table] = _copy_table(source, target, table, slug)
            if heartbeat is not None:
                heartbeat()
        _keys_go_on(target, present)
        source.rollback()
    return copied


def _copy_table(source: psycopg.Connection, target: psycopg.Connection, table: str, slug: str) -> int:
    reads = _columns(source, table)
    columns = [column for column in _columns(target, table) if column in reads]
    if not columns:
        return 0
    names_list = sql.SQL(", ").join(map(sql.Identifier, columns))
    where, params = rows_of(table, slug)
    read = sql.SQL("COPY (SELECT {} FROM {} {}) TO STDOUT").format(names_list, sql.Identifier(table), sql.SQL(where))
    write = sql.SQL("COPY {} ({}) FROM STDIN").format(sql.Identifier(table), names_list)
    with source.cursor() as reading, target.cursor() as writing:
        with reading.copy(read, params or None) as rows, writing.copy(write) as into:
            for block in rows:
                into.write(block)
        return max(writing.rowcount, 0)


def _keys_go_on(target: psycopg.Connection, tables: set[str]) -> None:
    """Every serial key of ``tables`` set past the largest value copied (an auto-created many-to-many table's)."""
    found = target.execute(
        "SELECT c.relname, a.attname, pg_get_serial_sequence(format('public.%%I', c.relname), a.attname) "
        "FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relname = ANY(%s) AND a.attnum > 0 AND NOT a.attisdropped",
        [sorted(tables)],
    ).fetchall()
    for table, column, sequence in found:
        if sequence is None:
            continue
        target.execute(
            sql.SQL("SELECT setval(%s, COALESCE((SELECT max({}) FROM {}), 0) + 1, false)").format(
                sql.Identifier(column), sql.Identifier(table)
            ),
            [sequence],
        )


# ── The cut of one business ────────────────────────────────────────────────────────────────────────────────────────


def cut_hub(hub_id, mode: str, *, dump: str = "") -> Outcome:
    """Give the business of phase 1 ``hub_id`` its own database in ``mode`` (:data:`RECREATE` or :data:`COPY_ALL`),
    under its lease; :class:`CutError` with why, the business left as it was, when it could not be done."""
    if mode not in (RECREATE, COPY_ALL):
        raise CutError(f"{mode!r} makes no database.")
    started = time.monotonic()
    with use_control():
        if services.claim_hub(hub_id, timezone.now(), LEASE) is None:
            raise CutError("another process is working on it (its lease is held).")
        try:
            return _cut(hub_id, mode, dump, started)
        finally:
            services.release_hub(hub_id, timezone.now())


def _cut(hub_id, mode: str, dump: str, started: float) -> Outcome:
    def renew() -> None:
        services.renew_hub_lease(hub_id, timezone.now(), LEASE)

    try:
        hub = services.place_hub(hub_id)
    except services.ProvisioningFailed as failed:
        raise CutError(str(failed)) from failed
    if hub.db_name or hub.status != Hub.Status.READY:
        raise CutError(
            f"it is {hub.status} with database {hub.db_name or '-'}: only a ready business on control's is cut."
        )
    # Named as every hub's; written in control only by the last step, so its host answers 503 until then.
    hub.db_name = names.hub_db_name(tenancy_connections.control_name(), hub.id)
    try:
        ops.drop_database(hub.db_name, cluster=hub.cluster)  # what a cut that broke left
        ops.clone_database(hub.db_name, template=provision.template_for(hub), cluster=hub.cluster)
        ddl = tenancy_connections.register_ddl_alias(hub.db_name, cluster=hub.cluster)
        identity.write(ddl, hub.id)
        migrator.ensure_schema(hub, add=["base", *provision.vertical_apps(hub.vertical)], heartbeat=renew)
        renew()
        copied = copy_rows(hub, heartbeat=renew) if mode == COPY_ALL else {}
        _seed_and_finish(hub, mode, copied, dump)
    except Exception as error:
        _undo(hub)
        if isinstance(error, CutError):
            raise
        raise CutError(f"{type(error).__name__}: {error}") from error
    finally:
        tenancy_connections.close_hub_aliases(hub)
    seconds = time.monotonic() - started
    logger.info(
        "base.tenancy.cut.done hub=%s mode=%s database=%s rows=%d seconds=%.2f",
        hub.slug,
        mode,
        hub.db_name,
        sum(copied.values()),
        seconds,
    )
    return Outcome(slug=hub.slug, mode=mode, database=hub.db_name, copied=copied, seconds=seconds)


def _seed_and_finish(hub, mode: str, copied: dict[str, int], dump: str) -> None:
    """The SaaS's photo kept on its row applied in its database, then the last step; again with a newer photo that came
    meanwhile, as a sign-up's seeding does (``provision.SEED_ROUNDS``)."""
    finish = get_operation("base.hub.cut_finish")
    for _ in range(provision.SEED_ROUNDS):
        with use_hub(hub):
            services.apply_kept_photo(hub)
        done = finish(
            system_context(registry.REGISTRY_SCOPE),
            HubCutFinishIn(
                id=hub.id,
                mode=mode,
                database=hub.db_name,
                schema_apps=hub.schema_apps,
                copied=copied,
                dump=dump,
                seeded_version=hub.state_version,
            ),
        )
        if done.done:
            return
        found = services.registry_row(hub.id)
        hub.state, hub.state_version = found.state, found.state_version
    raise CutError(f"the SaaS's photo kept changing while it was seeded ({provision.SEED_ROUNDS} times).")


def _undo(hub) -> None:
    """Drop what a cut that broke made, unless control already names it (its last step went through)."""
    found = services.registry_row(hub.id)
    if found is not None and found.db_name:
        return
    tenancy_connections.close_hub_aliases(hub)
    try:
        ops.drop_database(hub.db_name, cluster=hub.cluster)
    except ops.DatabaseOpsError:
        logger.exception("base.tenancy.cut.undo_failed hub=%s: %s stays; the next run drops it.", hub.slug, hub.db_name)
