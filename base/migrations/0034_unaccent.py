# The searches of the hub ignore accents (base/text_search.py) with PostgreSQL's unaccent: a trusted extension, so the
# owner of a hub's database creates it without a superuser.

from django.contrib.postgres.operations import UnaccentExtension
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0033_apps_turned_on_by_a_load_are_chosen'),
    ]

    operations = [
        UnaccentExtension(),
    ]
