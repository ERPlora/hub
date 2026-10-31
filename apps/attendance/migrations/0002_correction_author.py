# Review of 2026-10-15, findings 4 and 7.
# - A correction says explicitly whether the system made it, and keeps the name of who made it: a user
#   deleted later empties `created_by` and must not turn their corrections into the system's.
# - The exact coordinates of a day clocked from the shared device are dropped: nobody asked for them.
#   Only a personal device keeps them, when the business requires the location; the distance,
#   inside/outside and the accuracy stay. Backwards, nothing to undo: the fields go with the AddFields.
# - Edited by tenancy W10 (a no-op where it ran): a hub's own database has no ``auth_user`` to join, and no corrections
#   of before to name, so the names are read only where control's users are (phase 1's shared database).

from django.conf import settings
from django.db import migrations, models, router


def forwards(apps, schema_editor):
    Correction = apps.get_model("attendance", "Correction")
    Record = apps.get_model("attendance", "Record")
    if router.allow_migrate_model(schema_editor.connection.alias, apps.get_model(settings.AUTH_USER_MODEL)):
        _name_the_corrections(Correction, schema_editor)
    Record.objects.using(schema_editor.connection.alias).filter(source="shared").update(
        in_lat=None, in_lng=None, out_lat=None, out_lng=None
    )


def _name_the_corrections(Correction, schema_editor):
    for trail in Correction.objects.using(schema_editor.connection.alias).select_related("created_by"):
        user = trail.created_by
        trail.is_system = user is None
        # Historical models have no methods: the name as `get_full_name()` writes it, else the username.
        trail.created_by_name = (
            ""
            if user is None
            else (f"{user.first_name} {user.last_name}".strip() or user.username)
        )
        trail.save(update_fields=["is_system", "created_by_name"])


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
