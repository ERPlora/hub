# It wrote every app on for the hubs that shared control's database, so none lost an app when new hubs started with
# every app off. A business's own database never holds one: it changes nothing and only keeps its place in the history.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0016_app_activation"),
        ("control", "0001_initial"),
    ]

    operations = []
