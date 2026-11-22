# The services, their categories, the vouchers and what was done with them, and the settings kept the address of
# whoever acted when their account has no name (erplora.com names such an account by its address). A colleague's
# address only reaches whoever sees the team's contact details, so each keeps what goes before the «@», as whoever
# acts is named from now on (``base.queries.people.actor_name``; a migration never imports code that may change). Only
# a bare address is cut: a person's name and an API key's («API · …») keep theirs. Backwards, nothing changes: the
# address is kept nowhere to give it back.

from django.db import migrations
from django.db.models import F, Func, Value

#: What was kept for an account without a name: its address, alone.
ADDRESS = r"^[^@\s]+@[^@\s]+$"
#: Where who acted is kept, by model.
WHO = {
    "ServiceSettings": ["updated_by"],
    "Category": ["created_by", "updated_by"],
    "Service": ["created_by", "updated_by"],
    "Package": ["created_by", "updated_by"],
    "Grant": ["created_by", "voided_by"],
    "GrantAdjustment": ["actor"],
    "Redemption": ["actor", "ended_by"],
}


def forwards(apps, schema_editor):
    for model, fields in WHO.items():
        rows = apps.get_model("service", model).objects.using(schema_editor.connection.alias)
        for field in fields:
            rows.filter(**{f"{field}__regex": ADDRESS}).update(
                **{field: Func(F(field), Value("@"), Value(1), function="split_part")}
            )


class Migration(migrations.Migration):

    dependencies = [
        ("service", "0007_service_stands_for"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
