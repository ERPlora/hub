# ``base_outbox_pending`` wherever there is an outbox (hub#751). ``base/0006`` creates it with a ``RunSQL`` that names
# no model: since the routers gave up the shared database (hub#602), ``base`` counts as a hub's, so a control database
# made from scratch skips it and still records ``0006``, and its relay reads the whole outbox on every tick.
#
# - The hint names ``eventdelivery``, a contextual model of ``base``, so the routers let it through on control and on a
#   migrator's alias. ``outboxevent`` would not do: under ``base`` it counts as a hub's.
# - An index already valid (every hub's, and a control database migrated before hub#602) takes no statement: a hub's
#   outbox takes every sale, and only reading the catalog takes no lock on it.
# - ``atomic = False``: ``CONCURRENTLY`` lets every write go on while it builds, whatever the size of the outbox. A
#   build cut halfway leaves an invalid index under the name, which serves no query: the next run drops it and builds
#   it again.
# - Stepping back keeps the index: where ``0006`` made it, it is ``0006``'s to drop, and nothing here tells whose it is.
#   On control it only costs its own upkeep, and going forward again finds it.

from django.db import migrations

PENDING_INDEX = "base_outbox_pending"
DROP_INVALID_INDEX = f"DROP INDEX CONCURRENTLY {PENDING_INDEX}"
CREATE_INDEX = (
    f"CREATE INDEX CONCURRENTLY {PENDING_INDEX} ON live_outboxevent (created_at, id) WHERE delivered_at IS NULL"
)


def ensure_pending_index(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT indisvalid FROM pg_index WHERE indexrelid = to_regclass(%s)", [PENDING_INDEX])
        found = cursor.fetchone()
    if found and found[0]:
        return
    if found:
        schema_editor.execute(DROP_INVALID_INDEX, params=None)
    schema_editor.execute(CREATE_INDEX, params=None)


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('base', '0022_app_activation_creating'),
    ]

    operations = [
        migrations.RunPython(ensure_pending_index, migrations.RunPython.noop, hints={"model_name": "eventdelivery"}),
    ]
