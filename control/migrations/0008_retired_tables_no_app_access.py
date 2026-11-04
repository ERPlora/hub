# The tables control/0007 retired keep their rows, and until now they kept the app's role too: ``ALTER TABLE … RENAME``
# moves the grants with the table, so ``hub_app`` could still read and write ``<table>_shared_20261101``. Nothing does,
# but nothing stopped a future bug from doing it either (hub#621).
#
# - A migration and not a step of ``bootstrap_databases``: this one reaches prod and pre with their next deploy, as
#   ``hub_migrator``, who owns the tables and made the grants, so it needs no master. ``db-bootstrap`` is a task run by
#   hand, on an image the deploy does not move. And it runs right after control/0007, so no database has one without
#   the other. A rerun of the bootstrap gives nothing back: it only sets the default privileges of future tables.
# - The role is the environment's (``hub_app``, ``pre_hub_app`` in pre), as ``base.tenancy.ops`` names it for a hub's
#   database. A server without that role (local development, the suite) has nobody to close them to: said, not failed.
# - ``hub_admin`` keeps its ``SELECT``: support's ``pg_dump`` of control (PLAN-DB §10) stops at the first table it
#   cannot read, these tables keep rows nobody deleted, and that role is never the application's.
# - The list goes by the name alone, not by the inventory: a retired table whose model is gone later is still one.
# - The sequences of the few that have one (the identity of a join table) stay as they are: they hold no business data
#   and a ``nextval`` writes in no table.
# - What ``hub_app`` still holds is read back, because PostgreSQL only warns when whoever revokes is not the owner: the
#   whole migration is one transaction, so a table it cannot close stops the deploy with all of them as they were.

import logging

from django.db import migrations

from base.tenancy.ops import environment_roles

logger = logging.getLogger("base.tenancy.migrator")

SUFFIX = "_shared_20261101"
#: What the default privileges gave the app's role on these tables (``base.tenancy.bootstrap``): what stepping back
#: returns.
APP_PRIVILEGES = "SELECT, INSERT, UPDATE, DELETE"
#: ``has_table_privilege`` answers true if the role holds any of them.
ANY_PRIVILEGE = "SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER"
STILL_OPEN = """
    SELECT c.relname, pg_get_userbyid(c.relowner) FROM pg_class c
    WHERE pg_table_is_visible(c.oid) AND c.relname = ANY(%s) AND has_table_privilege(%s, c.oid, %s)
    ORDER BY c.relname
"""


class RetiredTablesStillOpen(RuntimeError):
    """The app's role still holds something on ``tables`` after the ``REVOKE``; the deploy shows it."""

    code = "control.retired_table_still_open"

    def __init__(self, message: str, tables):
        super().__init__(message)
        self.tables = list(tables)


def _retired(connection) -> list[str]:
    with connection.cursor() as cursor:
        return sorted(table for table in connection.introspection.table_names(cursor) if table.endswith(SUFFIX))


def _app_role(connection) -> str | None:
    """The environment's app role, or ``None``, said, when this server does not have it."""
    role = environment_roles(connection.settings_dict["NAME"]).hub_app
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [role])
        if cursor.fetchone() is not None:
            return role
    logger.warning("control.retired_tables_role_missing role=%s: no such role on the server; nothing changed.", role)
    return None


def _quoted(connection, names) -> str:
    return ", ".join(connection.ops.quote_name(name) for name in names)


def forwards(apps, schema_editor) -> None:
    connection = schema_editor.connection
    tables = _retired(connection)
    role = _app_role(connection) if tables else None
    if role is None:
        return
    with connection.cursor() as cursor:
        cursor.execute(f"REVOKE ALL ON TABLE {_quoted(connection, tables)} FROM {connection.ops.quote_name(role)}")
        cursor.execute(STILL_OPEN, [tables, role, ANY_PRIVILEGE])
        still_open = cursor.fetchall()
    if still_open:
        listed = ", ".join(f"{table} ({owner})" for table, owner in still_open)
        raise RetiredTablesStillOpen(
            f"Nothing was closed: {role} still holds privileges on {listed}. Make the role running the migrations their "
            "owner (ALTER TABLE … OWNER TO, as the master user) and deploy again.",
            [table for table, _owner in still_open],
        )
    logger.info("control.retired_tables_closed role=%s count=%d", role, len(tables))


def backwards(apps, schema_editor) -> None:
    connection = schema_editor.connection
    tables = _retired(connection)
    role = _app_role(connection) if tables else None
    if role is None:
        return
    with connection.cursor() as cursor:
        cursor.execute(
            f"GRANT {APP_PRIVILEGES} ON TABLE {_quoted(connection, tables)} TO {connection.ops.quote_name(role)}"
        )
    logger.info("control.retired_tables_reopened role=%s count=%d", role, len(tables))


class Migration(migrations.Migration):
    dependencies = [
        ("control", "0007_hub_tables_renamed_shared"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
