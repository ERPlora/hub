# The app that records a line of a session as its own (Tips). Every line kept before is by hand or a sale's: empty.
# Backwards, the column goes and nothing else changes.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cash_register', '0004_actors_without_address'),
    ]

    operations = [
        migrations.AddField(
            model_name='movement',
            name='app',
            field=models.CharField(blank=True, db_default='', default='', max_length=32, verbose_name='recorded by app'),
        ),
    ]
