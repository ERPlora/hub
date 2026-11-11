from django.db import migrations, models
from django.db.models import Q, Value


class Migration(migrations.Migration):
    """The two unique guards of the inbox stop naming the business column phase 1 left (hub#1132, first step): each
    business keeps its rows in its own database, so it holds one channel row and one live template per name and
    language whatever ``host`` a row kept.

    A constraint added to a table in use, after its first step (hub#1053, ``0011`` and ``0012``): since then the code
    writes every row with an empty ``host``, so the old guards already held what it writes to one channel row and one
    live template per name and language, and no row it writes breaks the new ones (``base/tests/
    test_migration_safety.py``, ``ACCEPTED``). A database that still keeps two channel rows, or two live templates of
    one name and language under two businesses, fails here and is left as it was. The old guards name a column the
    state no longer has, so they leave the database and come back by hand. The columns stay: a later deploy drops
    them (hub#1132, second step)."""

    dependencies = [("whatsapp_inbox", "0012_no_business_hosts")]

    operations = [
        migrations.AddConstraint(
            model_name="channel",
            constraint=models.UniqueConstraint(Value(True), name="whatsapp_inbox_channel_one_row"),
        ),
        migrations.RunSQL(
            sql='ALTER TABLE "whatsapp_inbox_channel" DROP CONSTRAINT IF EXISTS "whatsapp_inbox_channel_one_per_host"',
            reverse_sql=(
                'ALTER TABLE "whatsapp_inbox_channel" '
                'ADD CONSTRAINT "whatsapp_inbox_channel_one_per_host" UNIQUE ("host")'
            ),
        ),
        migrations.AddConstraint(
            model_name="template",
            constraint=models.UniqueConstraint(
                fields=("name", "language"),
                condition=Q(deleted_at__isnull=True),
                name="whatsapp_inbox_template_live_name_language_unique",
            ),
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveConstraint(
                    model_name="template",
                    name="whatsapp_inbox_template_live_host_name_language_unique",
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql='DROP INDEX IF EXISTS "whatsapp_inbox_template_live_host_name_language_unique"',
                    reverse_sql=(
                        'CREATE UNIQUE INDEX "whatsapp_inbox_template_live_host_name_language_unique" '
                        'ON "whatsapp_inbox_template" ("host", "name", "language") WHERE "deleted_at" IS NULL'
                    ),
                ),
            ],
        ),
    ]
