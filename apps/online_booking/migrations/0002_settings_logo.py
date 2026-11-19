"""The booking page's logo is an image the business uploads (``logo``), no longer an address of somewhere else.

``logo_url`` leaves the state only: the code of before still reads and writes it while the deploy runs, so its column
stays, with an empty default in the database for the rows the new code inserts without it, and is dropped in a later
deploy. Nothing is copied from it: the page never showed those addresses (it loads images of its own address only).
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("online_booking", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="settings",
            name="logo_url",
            field=models.CharField(blank=True, db_default="", max_length=500, verbose_name="logo URL"),
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[migrations.RemoveField(model_name="settings", name="logo_url")],
        ),
        migrations.AddField(
            model_name="settings",
            name="logo",
            field=models.CharField(blank=True, db_default="", default="", max_length=32, verbose_name="logo"),
        ),
    ]
