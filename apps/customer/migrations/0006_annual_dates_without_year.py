# A birthday and an anniversary may go without their year (``--03-14``). The columns stay ``date`` and nothing is
# written to the database: a day without its year is kept in 1604 (apps.customer.annual_dates), so the code of before
# keeps reading and writing them while the deploy migrates.

import apps.customer.annual_dates
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('customer', '0005_actor_without_address'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customer',
            name='anniversary',
            field=apps.customer.annual_dates.AnnualDateField(blank=True, null=True, verbose_name='anniversary'),
        ),
        migrations.AlterField(
            model_name='customer',
            name='birthday',
            field=apps.customer.annual_dates.AnnualDateField(blank=True, null=True, verbose_name='birthday'),
        ),
    ]
