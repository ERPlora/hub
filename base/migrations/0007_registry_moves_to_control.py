# The registry moves to control (phase 2, S1; plan docs/plans/2026-10-22-fase-2-tenencia.md).
#
# ``Hub`` and ``DemoCode`` leave base's state only (control/migrations/0001 took them over, tables included): their
# tables stay as they are, now control's. ``HubIdentity`` is new: the one row of a hub's database that says which hub
# it is (PLAN-DB §3); control's database has the table and no row.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0006_event_delivery"),
        ("control", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name="DemoCode"),
                migrations.DeleteModel(name="Hub"),
            ],
            database_operations=[],
        ),
        migrations.CreateModel(
            name="HubIdentity",
            fields=[
                ("hub_id", models.UUIDField(primary_key=True, serialize=False, verbose_name="hub")),
            ],
            options={
                "verbose_name": "hub identity",
                "verbose_name_plural": "hub identities",
                "db_table": "base_hub_identity",
            },
        ),
    ]
