# A birthday and an anniversary go from a date to text, so a day may go without its year (``--03-14``, as vCard writes
# it). Forward, each date becomes its ``YYYY-MM-DD`` and none becomes empty. Back, a full day is a date again; a day
# without its year cannot be one and is left empty, as none.

from django.db import migrations, models
from django.db.models import Q

DAYS = ("birthday", "anniversary")


def none_to_empty(apps, schema_editor):
    cards = apps.get_model("customer", "Customer").objects.using(schema_editor.connection.alias)
    for field in DAYS:
        cards.filter(**{f"{field}__isnull": True}).update(**{field: ""})


def no_date_back(apps, schema_editor):
    cards = apps.get_model("customer", "Customer").objects.using(schema_editor.connection.alias)
    for field in DAYS:
        cards.filter(Q(**{field: ""}) | Q(**{f"{field}__startswith": "--"})).update(**{field: None})


def _text(null: bool) -> list:
    return [
        migrations.AlterField(
            model_name="customer",
            name=field,
            field=models.CharField(blank=True, max_length=10, null=null, verbose_name=field),
        )
        for field in DAYS
    ]


class Migration(migrations.Migration):

    dependencies = [
        ("customer", "0005_actor_without_address"),
    ]

    operations = [
        *_text(null=True),
        migrations.RunPython(none_to_empty, no_date_back),
        *_text(null=False),
    ]
