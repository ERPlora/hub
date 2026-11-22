# A colleague's address only reaches whoever sees the team's contact details, but whoever acted with an account
# without a name was kept here by their email. Each label keeps what goes before the «@», as
# ``base.queries.people.actor_name`` names whoever acts now (a migration never imports code that may change).
# Backwards nothing changes: the address is kept nowhere to give it back.

from django.db import migrations
from django.db.models import F, Func, Value

ACTORS = {
    "PaymentMethod": ("created_by", "updated_by"),
    "Payment": ("created_by", "updated_by", "approved_by", "cancelled_by"),
}


def forwards(apps, schema_editor):
    for model, fields in ACTORS.items():
        rows = apps.get_model("payment", model).objects.using(schema_editor.connection.alias)
        for field in fields:
            rows.filter(**{f"{field}__contains": "@"}).update(
                **{field: Func(F(field), Value("@"), Value(1), function="split_part")}
            )


class Migration(migrations.Migration):

    dependencies = [
        ('payment', '0004_payment_currency_without_default'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
