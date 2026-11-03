# The contract of S5 (PLAN-DB, round 2026-11-01c): the tables of the hubs' apps that phase 1 left in control's database
# get ``<table>_shared_20261101``. No business has used them since the cut, yet nothing told their rows from live data.
# Never a DROP: the tables are not deleted, and stepping back returns every name.
#
# - Only control's: it lives in the ``control`` app, which ``TenantRouter`` migrates on ``default`` alone. A table is
#   left over when the routers refuse its model on this alias (:func:`left_behind`), so a hub's database has none, and
#   neither has the suite's control database, whose ``LegacyTablesRouter`` keeps those tables on purpose.
# - The list comes from ``base.tenancy.inventory``, the one place that says whose a table is, and from the installed
#   models: this migration's historical state knows only the apps it depends on. It is the exception to «a migration
#   never imports app code», so it holds as long as the inventory does; on a database made after S5 it finds nothing.
# - It stops, renaming nothing, while a ready business has no database of its own: ``cut_shared_hubs`` still has to
#   give it one, and ``--copy-all`` reads these tables. A cancelled business (``yfn`` in production) and a demo do not
#   stop it: neither is served, and neither is ever copied (``base.hub.restore`` makes a database from nothing).
# - It stops too, renaming nothing, when ``hub_migrator`` (who runs the migrations of control in ``hub-migrate``) does
#   not own a table: ``ALTER TABLE … RENAME`` asks for its owner. A half-done rename would be harmless, but a clear
#   word before the first one says what to fix.
# - ``atomic = False``: each table in a short transaction of its own, under a ``lock_timeout``, so it never holds more
#   than one lock on the way nor waits long behind whoever holds one. A run that breaks halfway leaves what it did,
#   nobody reads those tables, and the next run does the rest.

import logging

from django.apps import apps as installed_apps
from django.db import migrations, router

from base.tenancy import inventory

logger = logging.getLogger("base.tenancy.migrator")

SUFFIX = "_shared_20261101"
#: PostgreSQL's limit on a name, past which it cuts it with a mere notice: two long names could end up as one.
MAX_NAME_BYTES = 63
#: How long one table's rename waits for its lock.
LOCK_TIMEOUT = "10s"
OTHERS_TABLES = """
    SELECT c.relname, pg_get_userbyid(c.relowner) FROM pg_class c
    WHERE c.relkind IN ('r', 'p') AND pg_table_is_visible(c.oid) AND c.relname = ANY(%s)
    AND NOT pg_has_role(current_user, c.relowner, 'USAGE')
    ORDER BY c.relname
"""


class HubTablesNotRenamed(RuntimeError):
    """Why the migration stopped before its first rename (``code``); the deploy shows it, and the next one runs again."""

    def __init__(self, code: str, message: str, slugs=()):
        super().__init__(message)
        self.code = code
        self.slugs = list(slugs)


def shared_name(table: str) -> str:
    """``table``'s new name; :class:`HubTablesNotRenamed` if PostgreSQL would cut it."""
    name = f"{table}{SUFFIX}"
    if len(name.encode()) > MAX_NAME_BYTES:
        raise HubTablesNotRenamed(
            "control.shared_name_too_long",
            f"{name} is longer than {MAX_NAME_BYTES} bytes: PostgreSQL would cut it and two tables could share a name.",
        )
    return name


def left_behind(alias: str) -> list[str]:
    """The tables of the hubs' apps that the routers refuse on ``alias``: if they are there, nobody should use them."""
    return sorted(
        {
            model._meta.db_table
            for model in installed_apps.get_models(include_auto_created=True)
            if model._meta.managed
            and inventory.classify(model) == inventory.HUB
            and not router.allow_migrate_model(alias, model)
        }
    )


def _present(connection) -> set[str]:
    with connection.cursor() as cursor:
        return set(connection.introspection.table_names(cursor))


def rename(connection, pairs) -> int:
    """Rename every ``(old, new)`` that is there and whose new name is free, each in a transaction of its own; return
    how many. A name already taken is left as it is, and said."""
    present = _present(connection)
    quote = connection.ops.quote_name
    renamed = 0
    for old, new in pairs:
        if old not in present:
            continue
        if new in present:
            logger.warning(
                "control.hub_table_not_renamed table=%s: %s already exists; both are left as they are.", old, new
            )
            continue
        # A schema editor of its own is this table's transaction, on this alias.
        with connection.schema_editor() as editor:
            editor.execute(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")
            editor.execute(f"ALTER TABLE {quote(old)} RENAME TO {quote(new)}")
        renamed += 1
    return renamed


def _stop_unless_owned(connection, tables: list[str]) -> None:
    with connection.cursor() as cursor:
        cursor.execute(OTHERS_TABLES, [tables])
        others = cursor.fetchall()
    if others:
        listed = ", ".join(f"{table} ({owner})" for table, owner in others)
        raise HubTablesNotRenamed(
            "control.table_of_another_owner",
            f"Nothing was renamed: the role running the migrations does not own {listed}. Make it their owner "
            "(ALTER TABLE … OWNER TO, as the master user) and deploy again.",
        )


def _stop_if_not_cut(apps, schema_editor) -> None:
    Hub = apps.get_model("control", "Hub")
    waiting = sorted(
        Hub.objects.using(schema_editor.connection.alias)
        .filter(db_name="", is_demo=False, status="ready")
        .values_list("slug", flat=True)
    )
    if waiting:
        raise HubTablesNotRenamed(
            "control.hub_not_cut",
            f"Nothing was renamed: {', '.join(waiting)} still have no database of their own and these tables may be "
            "theirs. Run manage.py cut_shared_hubs (docs/runbooks/cut-shared-hubs.md) and deploy again.",
            slugs=waiting,
        )


def forwards(apps, schema_editor) -> None:
    connection = schema_editor.connection
    present = _present(connection)
    tables = [table for table in left_behind(connection.alias) if table in present]
    if not tables:
        return
    pairs = [(table, shared_name(table)) for table in tables]
    _stop_unless_owned(connection, tables)
    _stop_if_not_cut(apps, schema_editor)
    logger.info("control.hub_tables_renamed count=%d", rename(connection, pairs))


def backwards(apps, schema_editor) -> None:
    connection = schema_editor.connection
    pairs = [(f"{table}{SUFFIX}", table) for table in left_behind(connection.alias)]
    logger.info("control.hub_tables_renamed_back count=%d", rename(connection, pairs))


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("control", "0006_hub_activity"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
