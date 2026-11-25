# A check kept the address of a waiter whose account has no name (erplora.com names such an account by its address).
# A colleague's address only reaches whoever sees the team's contact details, so the check keeps what goes before the
# «@», as a waiter is named from now on (``base.queries.people.actor_name``; a migration never imports code that may
# change). Backwards, nothing changes: the address is kept nowhere to give it back.

from django.db import migrations
from django.db.models import F, Func, Value


def forwards(apps, schema_editor):
    sessions = apps.get_model("table", "TableSession").objects.using(schema_editor.connection.alias)
    sessions.filter(waiter_name__contains="@").update(
        waiter_name=Func(F("waiter_name"), Value("@"), Value(1), function="split_part")
    )


class Migration(migrations.Migration):

    dependencies = [
        ('table', '0002_session_table_by_status'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
