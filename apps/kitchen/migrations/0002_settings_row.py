"""The kitchen's settings row, made with its tables: the factory values and the moment from which the
kitchen receives the rounds Sales fires (what was fired before the kitchen existed never shows up).
Planted once (a row already there is kept); the reverse removes it."""

from django.db import migrations
from django.utils import timezone


def plant_settings(apps, schema_editor):
    settings = apps.get_model("kitchen", "KitchenSettings")
    rows = settings.objects.using(schema_editor.connection.alias)
    if not rows.exists():
        rows.create(receiving_since=timezone.now())


def remove_settings(apps, schema_editor):
    settings = apps.get_model("kitchen", "KitchenSettings")
    settings.objects.using(schema_editor.connection.alias).all().delete()


class Migration(migrations.Migration):
    dependencies = [("kitchen", "0001_initial")]

    operations = [migrations.RunPython(plant_settings, remove_settings)]
