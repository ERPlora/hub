# - A correction says explicitly whether the system made it, and keeps the name of who made it: a user
#   deleted later empties `created_by` and must not turn their corrections into the system's.
# - The exact coordinates of a day clocked from the shared device are dropped: nobody asked for them.
#   Only a personal device keeps them, when the business requires the location; the distance,
#   inside/outside and the accuracy stay. Backwards, nothing to undo: the fields go with the AddFields.

from django.db import migrations, models


def forwards(apps, schema_editor):
    Record = apps.get_model("attendance", "Record")
    Record.objects.using(schema_editor.connection.alias).filter(source="shared").update(
        in_lat=None, in_lng=None, out_lat=None, out_lng=None
    )


def backwards(apps, schema_editor):
    """Nothing to restore: the new fields are removed by the AddFields' reverse; dropped coordinates stay
    dropped (they were never asked for)."""


class Migration(migrations.Migration):
    dependencies = [
        ("attendance", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="correction",
            name="created_by_name",
            field=models.CharField(
                blank=True, max_length=300, verbose_name="corrected by (name)"
            ),
        ),
        migrations.AddField(
            model_name="correction",
            name="is_system",
            field=models.BooleanField(default=False, verbose_name="made by the system"),
        ),
        migrations.RunPython(forwards, backwards),
    ]
