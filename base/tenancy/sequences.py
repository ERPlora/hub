"""The counters (sequences) of a hub's database, written in its own WAL.

PostgreSQL writes a sequence to the WAL 32 values ahead and hands out the next ones from memory. ``CREATE DATABASE …
TEMPLATE`` copies that page with what is left of the template's 32, but only the template's WAL holds them: once the
clone's page is rebuilt from its own WAL (a crash; on Aurora, the page leaving the cache) its counter goes back to the
value it was cloned at and hands out again ids its rows already have.

- :func:`write_down`, right after every clone (``base.tenancy.ops.clone_database``): each counter set to the value it
  is at, which writes it in the clone's WAL, as ``pg_dump``'s ``SEQUENCE SET`` does on a restore.
- :func:`reset_migrations`, before the migrator records anything (``base.tenancy.migrator``): the counter of
  ``django_migrations`` set to its highest id, Django's ``sqlsequencereset``. It puts right a hub cloned before
  :func:`write_down` existed whose counter already went back, and writes it in that hub's WAL.
"""

from django.core.management.color import no_style
from django.db.migrations.recorder import MigrationRecorder

#: Every sequence that has handed out a value, set to the value it is at.
WRITE_DOWN = (
    "SELECT setval(format('%I.%I', schemaname, sequencename)::regclass, last_value) "
    "FROM pg_sequences WHERE last_value IS NOT NULL"
)


def write_down(conn) -> None:
    """Write every counter of the database behind the ``psycopg`` connection ``conn`` in its own WAL, as it is: only
    while nothing else hands out values from them (a clone nobody uses yet)."""
    conn.execute(WRITE_DOWN)


def reset_migrations(connection) -> None:
    """Set the counter of ``django_migrations`` behind the Django ``connection`` to its highest id; nothing without the
    table. Only for its one writer, the migrator, under the database's schema lock."""
    recorder = MigrationRecorder(connection)
    if not recorder.has_table():
        return
    with connection.cursor() as cursor:
        for statement in connection.ops.sequence_reset_sql(no_style(), [recorder.Migration]):
            cursor.execute(statement)
