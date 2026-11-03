# The lease of a hub's hub_due row is its worker process's (review of hub#471, I2): only its holder renews it or gives it
# back. Expand: the column has its default in the database, so the code of before inserts and updates without it.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('control', '0002_hub_preparation_and_clusters'),
    ]

    operations = [
        migrations.AddField(
            model_name='hubdue',
            name='lease_owner',
            field=models.CharField(blank=True, db_default='', default='', max_length=128, verbose_name='leased by'),
        ),
    ]
