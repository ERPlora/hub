# Generated manually for menu_items field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('plugins_admin', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='plugin',
            name='menu_items',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
